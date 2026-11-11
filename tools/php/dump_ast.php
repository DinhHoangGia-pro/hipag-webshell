<?php
// nikic/PHP-Parser -> IR thô mức statement (Bước 13). Python (parsing/php_ast.py) dựng DFG + IR cuối.
//
//   php -d short_open_tag=1 tools/php/dump_ast.php <file.php>        -> 1 dòng JSON
//   php -d short_open_tag=1 tools/php/dump_ast.php --batch < paths   -> 1 dòng JSON / path (cùng thứ tự)
//   thêm --no-deobf (bất kỳ vị trí nào) -> TẮT giải vỏ tĩnh UPG-02 (ablation no_deobf; build_graphs.yaml parser.deobf)
//
// Mỗi dòng: {"path", "status": ok|recovered|fallback_tokens|unreadable, "parser": "8.4"|"7.0"|null,
//            "n_errors", "error", "functions": [{"name", "params", "stmts": [{kind,text,tokens,defs,uses,calls,callargs,line}],
//            "cfg": [[i,j]]}],
// params   : tên tham số theo thứ tự (null nếu không phải biến đơn); <main> = [].
// calls      : callee của FuncCall/MethodCall/StaticCall (lower; method '->m'; gọi động -> '<dyncall>').
// deobfuscated: statement ghép từ mã đã giải vỏ tĩnh (UPG-02, deobf_lib.php); "deobf" (mức file) = log
//            {folded, grafted, not_literal, skipped: {lý do: số}, events: [...]}.
// constructs : construct ngôn ngữ trong statement: eval | include | include_once | require | require_once |
//              shell_exec (backtick). calls ∪ constructs = CALL NODE thật -> taint_seeds phân loại sink theo đó
//              (literal chuỗi trùng tên sink KHÔNG là sink). fallback_tokens: lấy từ token của tokenizer PHP.
// callargs : [{"name": tên hàm (lower) | "->method" | "<dyncall>", "args": [[biến trong đối số 0], [..1], ...]}]
//            — dùng để bridge taint arg->param liên thủ tục (graph/hierarchical_graph.py).
//            "n_includes", "n_stmt_total"}
// functions[0] = phạm vi file (<main>). CFG là xấp xỉ cấu trúc (if/loop/switch/try/break/continue/return),
// không xử lý goto/exception-edge. File parse lỗi: thử 8.4 rồi 7.0 (cú pháp PHP5 như $a{0}); vẫn lỗi nặng
// -> fallback tách statement theo token (status=fallback_tokens) — KHÔNG loại âm thầm (RQF-05).
declare(strict_types=1);
require __DIR__ . '/../../vendor/autoload.php';
require __DIR__ . '/canon_lib.php';
require __DIR__ . '/deobf_lib.php';    // UPG-02: giải vỏ TĨNH (constant-fold decoder trên literal; KHÔNG execute)   // chuẩn hoá đầu vào: model không thấy comment/docblock/thẻ đóng cuối

use PhpParser\ErrorHandler;
use PhpParser\Node;
use PhpParser\Node\Expr;
use PhpParser\Node\Stmt;
use PhpParser\ParserFactory;
use PhpParser\PhpVersion;

const MAX_TEXT = 1024;       // ký tự text/statement
const MAX_TOK = 64;          // token/statement
const MAX_STMT_FN = 2000;    // statement/hàm (builder Python còn cắt tiếp max_stmt_per_block)
const MAX_FUNCS = 400;
const MAX_LIT = 32;          // literal chuỗi dài hơn -> token <str>/<longstr>
const MAX_CALLARGS = 32;     // call site/statement

final class Fn_
{
    public array $stmts = [];
    public array $cfg = [];
    public array $loops = [];   // stack: ['head'=>?int,'breaks'=>[],'conts'=>[]]
    /** Hằng của scope cho const-propagation hẹp (deobf_const_env). */
    public array $constEnv = [];
    public function __construct(public string $name, public array $params = []) {}
}

final class Flattener
{
    /** @var Fn_[] */
    public array $fns = [];
    public int $nIncludes = 0;
    public int $nTotal = 0;
    /** Log giải vỏ tĩnh (UPG-02). */
    public array $deobf = ['enabled' => true, 'folded' => 0, 'const_folds' => 0, 'grafted' => 0, 'not_literal' => 0,
                           'skipped' => [], 'events' => []];
    /** Exit CFG của mã đã ghép sau add() gần nhất (null nếu không ghép). */
    public ?array $lastExits = null;
    private int $graftDepth = 0;
    private int $noFold = 0;
    private ?Fn_ $curFn = null;

    public function __construct(private string $src, private bool $deobfOn = true)
    {
        $this->deobf['enabled'] = $deobfOn;
    }

    private function deobfLog(string $what, ?Node $n, array $extra = []): void
    {
        if (count($this->deobf['events']) < 20)
            $this->deobf['events'][] = ['what' => $what, 'line' => $n ? $n->getStartLine() : 0, 'depth' => $this->graftDepth] + $extra;
    }

    private function deobfSkip(string $why, ?Node $n): void
    {
        $this->deobf['skipped'][$why] = ($this->deobf['skipped'][$why] ?? 0) + 1;
        $this->deobfLog('skip', $n, ['reason' => $why]);
    }

    /** Thử constant-fold một lời gọi decoder (chỉ ở lời gọi NGOÀI CÙNG của chuỗi lồng).
     *  Trả true nếu các lớp decoder BÊN TRONG không được fold riêng nữa: fold thành công (đã nằm trong kết quả),
     *  hoặc bị CHẶN vì an toàn (too_deep/too_big/decode_fail) — không fold lại từng phần của quả bom.
     *  Đối số động (not_literal) -> false: lớp bên trong có thể vẫn là literal, fold riêng được. */
    private function tryFold(Expr\FuncCall $node, array &$acc): bool
    {
        if (!$this->deobfOn || $this->noFold > 0 || !$node->name instanceof Node\Name
            || !in_array(strtolower($node->name->getLast()), DEOBF_DECODERS, true)) return false;
        $env = $this->curFn?->constEnv ?? [];
        if ($this->graftDepth > 0)                       // mã ghép: vị trí node tính trên chuỗi khác -> bỏ kiểm vị trí
            $env = array_map(fn($c) => ['val' => $c['val'], 'pos' => -1], $env);
        $r = deobf_fold($node, 0, $env);
        if (!$r['ok']) {
            if ($r['reason'] === 'not_literal') { $this->deobf['not_literal']++; return false; }
            $this->deobfSkip($r['reason'], $node);
            return true;
        }
        $this->deobf['folded']++;
        if ($r['consts'] > 0) { $this->deobf['const_folds']++; $this->deobfLog('const_fold', $node, ['consts' => $r['consts']]); }
        $acc['folds'][] = ['val' => $r['val'], 'layers' => $r['layers'], 'node' => $node];
        return true;
    }

    /** Ghép mã đã giải (nếu là PHP hợp lệ) vào hàm hiện tại sau $preds. Trả exit CFG hoặc null nếu không ghép. */
    private function graft(Fn_ $f, array $fd, array $preds): ?array
    {
        $n = $fd['node'];
        if ($this->graftDepth >= DEOBF_MAX_GRAFT_DEPTH) { $this->deobfSkip('graft_too_deep', $n); return null; }
        if ($this->deobf['grafted'] >= DEOBF_MAX_GRAFTS) { $this->deobfSkip('too_many_grafts', $n); return null; }
        $p = deobf_parse($fd['val']);
        if ($p === null) { $this->deobfSkip('not_php', $n); return null; }   // blob/text -> literal dữ liệu
        [$src, $ast] = $p;
        $this->deobf['grafted']++;
        $this->deobfLog('graft', $n, ['layers' => $fd['layers'], 'bytes' => strlen($fd['val'])]);
        $saved = $this->src;
        $this->src = $src;                 // vị trí node của AST ghép tính trên chuỗi đã giải
        $this->graftDepth++;
        try { $ex = $this->seq($f, $ast, $preds); }
        finally { $this->graftDepth--; $this->src = $saved; }
        return $ex ?: $preds;
    }

    private function txt(?Node $n, string $prefix = ''): string
    {
        if ($n === null) return $prefix;
        $s = $n->getStartFilePos(); $e = $n->getEndFilePos();
        $t = ($s >= 0 && $e >= $s) ? substr($this->src, $s, min($e - $s + 1, MAX_TEXT)) : '';
        return substr($prefix . $t, 0, MAX_TEXT);
    }

    private static function kindOf(Node $n): string
    {
        if ($n instanceof Stmt\Expression) $n = $n->expr;
        $t = preg_replace('/^(Stmt|Expr|Scalar)_/', '', $n->getType());
        if (str_starts_with($t, 'AssignOp_') || $t === 'AssignRef') return 'Assign';
        if ($t === 'NullsafeMethodCall') return 'MethodCall';
        if ($t === 'Include') return 'Include';
        return $t;
    }

    /** Tên biến (không '$') xuất hiện trong một biểu thức đối số. */
    private static function argVars($e): array
    {
        if (!$e instanceof Node) return [];
        $out = [];
        foreach ((new \PhpParser\NodeFinder())->findInstanceOf($e, Expr\Variable::class) as $v)
            if (is_string($v->name)) $out[$v->name] = 1;
        return array_keys($out);
    }

    private static function callArgs(string $name, array $args, array &$acc): void
    {
        if (count($acc['callargs']) >= MAX_CALLARGS) return;
        $a = [];
        foreach ($args as $arg) $a[] = ($arg instanceof Node\Arg) ? self::argVars($arg->value) : [];
        $acc['callargs'][] = ['name' => $name, 'args' => $a];
    }

    private static function paramNames(array $params): array
    {
        return array_map(fn($p) => ($p->var instanceof Expr\Variable && is_string($p->var->name)) ? $p->var->name : null, $params);
    }

    // ---- token / def / use / call trên các biểu thức "riêng" của một statement ----
    private function scan($node, array &$acc, bool $defPos = false): void
    {
        if (is_array($node)) { foreach ($node as $x) $this->scan($x, $acc, $defPos); return; }
        if (!$node instanceof Node) return;
        $tok = function (string $t) use (&$acc) { if (count($acc['tokens']) < MAX_TOK) $acc['tokens'][] = $t; };

        if ($node instanceof Expr\Variable) {
            if (is_string($node->name)) {
                $tok('$' . $node->name);
                if ($defPos) $acc['defs'][$node->name] = 1; else $acc['uses'][$node->name] = 1;
            } else { $tok('<varvar>'); $this->scan($node->name, $acc); }
            return;
        }
        if ($node instanceof Expr\Assign || $node instanceof Expr\AssignRef || $node instanceof Expr\AssignOp) {
            $this->scan($node->var, $acc, true);
            if ($node instanceof Expr\AssignOp) $this->scan($node->var, $acc, false);
            $tok('=');
            $this->scan($node->expr, $acc);
            return;
        }
        if ($defPos && ($node instanceof Expr\ArrayDimFetch || $node instanceof Expr\PropertyFetch)) {
            $this->scan($node->var, $acc, true);              // $a[k] = ... -> định nghĩa (yếu) $a
            $this->scan($node->var, $acc, false);
            if ($node instanceof Expr\ArrayDimFetch) $this->scan($node->dim, $acc);
            return;
        }
        if ($node instanceof Expr\List_ || $node instanceof Expr\Array_ && $defPos) {
            foreach ($node->items as $it) if ($it !== null) $this->scan($it->value, $acc, $defPos);
            return;
        }
        if ($node instanceof Expr\FuncCall) {
            $folded = $this->tryFold($node, $acc);
            if ($folded) $this->noFold++;              // lớp bên trong: đã fold trong kết quả, hoặc bị chặn an toàn
            if ($node->name instanceof Node\Name) {
                $nm = strtolower($node->name->getLast());
                $tok($nm); $acc['calls'][$nm] = 1;
                self::callArgs($nm, $node->args, $acc);
            } else { $tok('<dyncall>'); $acc['calls']['<dyncall>'] = 1; $this->scan($node->name, $acc); self::callArgs('<dyncall>', $node->args, $acc); }
            $tok('(');
            $this->scan($node->args, $acc);
            if ($folded) $this->noFold--;
            return;
        }
        if ($node instanceof Expr\MethodCall || $node instanceof Expr\NullsafeMethodCall || $node instanceof Expr\StaticCall) {
            $this->scan($node instanceof Expr\StaticCall ? $node->class : $node->var, $acc);
            if ($node->name instanceof Node\Identifier) {
                $nm = $node->name->toLowerString(); $tok('->' . $nm); $acc['calls']['->' . $nm] = 1;
                self::callArgs('->' . $nm, $node->args, $acc);
            } else { $tok('<dyncall>'); $acc['calls']['<dyncall>'] = 1; $this->scan($node->name, $acc); self::callArgs('<dyncall>', $node->args, $acc); }
            $this->scan($node->args, $acc);
            return;
        }
        if ($node instanceof Expr\Eval_) { $tok('eval'); $acc['constructs']['eval'] = 1; $this->scan($node->expr, $acc); return; }
        if ($node instanceof Expr\Include_) {
            $this->nIncludes++;
            $inc = [1 => 'include', 2 => 'include_once', 3 => 'require', 4 => 'require_once'][$node->type] ?? 'include';
            $tok($inc); $acc['constructs'][$inc] = 1;
            $this->scan($node->expr, $acc); return;
        }
        if ($node instanceof Expr\ShellExec) { $tok('shell_exec'); $acc['constructs']['shell_exec'] = 1; $this->scan($node->parts, $acc); return; }
        if ($node instanceof Expr\Exit_) { $tok('exit'); $this->scan($node->expr, $acc); return; }
        if ($node instanceof Expr\Print_) { $tok('print'); $this->scan($node->expr, $acc); return; }
        if ($node instanceof Expr\New_) {
            $tok('new');
            if ($node->class instanceof Node\Name) $tok(strtolower($node->class->getLast())); else $this->scan($node->class, $acc);
            $this->scan($node->args, $acc); return;
        }
        if ($node instanceof Node\Scalar\String_) {
            $v = $node->value; $l = strlen($v);
            $tok($l <= MAX_LIT ? $v : ($l > 256 ? '<longstr>' : '<str>'));
            return;
        }
        if ($node instanceof Node\Scalar\InterpolatedString) { $tok('<istr>'); $this->scan($node->parts, $acc); return; }
        if ($node instanceof Node\Scalar\Int_ || $node instanceof Node\Scalar\Float_) { $tok('<num>'); return; }
        if ($node instanceof Expr\BinaryOp\Concat) { $this->scan($node->left, $acc); $tok('.'); $this->scan($node->right, $acc); return; }
        if ($node instanceof Expr\Closure || $node instanceof Expr\ArrowFunction) { $tok('<closure>'); }
        if ($node instanceof Stmt) {                      // thân closure: gom token, không tách statement
            foreach ($node->getSubNodeNames() as $sn) $this->scan($node->$sn, $acc);
            return;
        }
        foreach ($node->getSubNodeNames() as $sn) $this->scan($node->$sn, $acc, false);
    }

    private function add(Fn_ $f, Node $n, array $preds, ?string $kind = null, ?string $text = null, array $own = [], array $defs = []): int
    {
        $acc = ['tokens' => [], 'defs' => [], 'uses' => [], 'calls' => [], 'callargs' => [], 'constructs' => [], 'folds' => []];
        $this->curFn = $f;
        $this->scan($own, $acc);
        foreach ($defs as $d) $this->scan($d, $acc, true);
        $i = count($f->stmts);
        $this->nTotal++;
        $this->lastExits = null;
        if ($i >= MAX_STMT_FN) return -1;
        $f->stmts[] = [
            'kind' => $kind ?? self::kindOf($n), 'text' => $text ?? $this->txt($n),
            'tokens' => $acc['tokens'], 'defs' => array_keys($acc['defs']), 'uses' => array_keys($acc['uses']),
            'calls' => array_keys($acc['calls']), 'callargs' => $acc['callargs'],
            'constructs' => array_keys($acc['constructs']), 'line' => $n->getStartLine(),
            'deobfuscated' => $this->graftDepth > 0,
        ];
        foreach ($preds as $p) if ($p >= 0 && $p !== $i) $f->cfg[] = [$p, $i];
        // UPG-02: mã giải được từ literal của statement này -> ghép ngay sau nó (eval chạy trong cùng scope)
        $exits = null;
        foreach ($acc['folds'] as $fd) {
            $g = $this->graft($f, $fd, $exits ?? [$i]);
            if ($g !== null) $exits = $g;
        }
        $this->lastExits = $exits;
        return $i;
    }

    public function newFn(string $name, array $stmts, array $params = []): void
    {
        if (count($this->fns) >= MAX_FUNCS) return;
        $f = new Fn_($name, $params);
        if ($this->deobfOn) $f->constEnv = deobf_const_env($stmts, $params);
        $this->fns[] = $f;
        $this->seq($f, $stmts, []);
    }

    private function seq(Fn_ $f, ?array $stmts, array $preds): array
    {
        foreach ($stmts ?? [] as $s) $preds = $this->stmt($f, $s, $preds);
        return $preds;
    }

    private function stmt(Fn_ $f, Node $s, array $preds): array
    {
        if ($s instanceof Stmt\Nop) return $preds;
        if ($s instanceof Stmt\Namespace_ || $s instanceof Stmt\Block) return $this->seq($f, $s->stmts, $preds);
        if ($s instanceof Stmt\Declare_) {
            $i = $this->add($f, $s, $preds, 'Other', 'declare');
            return $s->stmts !== null ? $this->seq($f, $s->stmts, [$i]) : [$i];
        }
        if ($s instanceof Stmt\Function_) {
            $this->newFn($s->name->toString(), $s->stmts, self::paramNames($s->params));
            return [$this->add($f, $s, $preds, 'Function', 'function ' . $s->name->toString())];
        }
        if ($s instanceof Stmt\ClassLike) {
            $cn = $s->name ? $s->name->toString() : '<anon>';
            foreach ($s->getMethods() as $m) if ($m->stmts !== null) $this->newFn($cn . '::' . $m->name->toString(), $m->stmts, self::paramNames($m->params));
            return [$this->add($f, $s, $preds, 'Other', 'class ' . $cn)];
        }
        if ($s instanceof Stmt\If_) {
            $c = $this->add($f, $s, $preds, 'If', $this->txt($s->cond, 'if '), [$s->cond]);
            $exits = $this->seq($f, $s->stmts, [$c]);
            $prev = $c;
            foreach ($s->elseifs as $ei) {
                $e = $this->add($f, $ei, [$prev], 'ElseIf', $this->txt($ei->cond, 'elseif '), [$ei->cond]);
                $exits = array_merge($exits, $this->seq($f, $ei->stmts, [$e]));
                $prev = $e;
            }
            if ($s->else) {
                $el = $this->add($f, $s->else, [$prev], 'Else', 'else');
                $exits = array_merge($exits, $this->seq($f, $s->else->stmts, [$el]));
            } else $exits[] = $prev;
            return $exits;
        }
        if ($s instanceof Stmt\While_ || $s instanceof Stmt\For_ || $s instanceof Stmt\Foreach_) {
            if ($s instanceof Stmt\While_) $h = $this->add($f, $s, $preds, 'While', $this->txt($s->cond, 'while '), [$s->cond]);
            elseif ($s instanceof Stmt\For_) $h = $this->add($f, $s, $preds, 'For', 'for', [$s->cond, $s->loop], [$s->init]);
            else $h = $this->add($f, $s, $preds, 'Foreach', $this->txt($s->expr, 'foreach '), [$s->expr], [$s->keyVar, $s->valueVar]);
            $f->loops[] = ['head' => $h, 'breaks' => [], 'conts' => []];
            $ex = $this->seq($f, $s->stmts, [$h]);
            $L = array_pop($f->loops);
            foreach (array_merge($ex, $L['conts']) as $e) if ($e >= 0 && $h >= 0) $f->cfg[] = [$e, $h];
            return array_merge([$h], $L['breaks']);
        }
        if ($s instanceof Stmt\Do_) {
            $first = count($f->stmts);
            $f->loops[] = ['head' => null, 'breaks' => [], 'conts' => []];
            $ex = $this->seq($f, $s->stmts, $preds);
            $L = array_pop($f->loops);
            $c = $this->add($f, $s, array_merge($ex, $L['conts']), 'Do', $this->txt($s->cond, 'do-while '), [$s->cond]);
            if ($c > $first) $f->cfg[] = [$c, $first];
            return array_merge([$c], $L['breaks']);
        }
        if ($s instanceof Stmt\Switch_) {
            $h = $this->add($f, $s, $preds, 'Switch', $this->txt($s->cond, 'switch '), [$s->cond]);
            $f->loops[] = ['head' => null, 'breaks' => [], 'conts' => []];
            $fall = []; $hasDefault = false;
            foreach ($s->cases as $case) {
                $hasDefault = $hasDefault || $case->cond === null;
                $k = $this->add($f, $case, array_merge([$h], $fall), 'Other', $case->cond ? $this->txt($case->cond, 'case ') : 'default', [$case->cond]);
                $fall = $this->seq($f, $case->stmts, [$k]);
            }
            $L = array_pop($f->loops);
            return array_merge($fall, $L['breaks'], $L['conts'], $hasDefault ? [] : [$h]);
        }
        if ($s instanceof Stmt\TryCatch) {
            $t = $this->add($f, $s, $preds, 'Try', 'try');
            $ex = $this->seq($f, $s->stmts, [$t]);
            foreach ($s->catches as $ca) {
                $c = $this->add($f, $ca, [$t], 'Other', 'catch', [], [$ca->var]);
                $ex = array_merge($ex, $this->seq($f, $ca->stmts, [$c]));
            }
            if ($s->finally) {
                $fi = $this->add($f, $s->finally, $ex, 'Other', 'finally');
                $ex = $this->seq($f, $s->finally->stmts, [$fi]);
            }
            return $ex;
        }
        if ($s instanceof Stmt\Break_ || $s instanceof Stmt\Continue_) {
            $i = $this->add($f, $s, $preds, 'Other');
            $lvl = ($s->num instanceof Node\Scalar\Int_) ? max(1, $s->num->value) : 1;
            $idx = count($f->loops) - $lvl;
            if ($idx >= 0) {
                if ($s instanceof Stmt\Break_ || $f->loops[$idx]['head'] === null) $f->loops[$idx][$s instanceof Stmt\Break_ ? 'breaks' : 'conts'][] = $i;
                else $f->loops[$idx]['conts'][] = $i;
            }
            return [];
        }
        if ($s instanceof Stmt\Return_) { $this->add($f, $s, $preds, 'Return', null, [$s->expr]); return []; }
        if ($s instanceof Stmt\HaltCompiler) { $this->add($f, $s, $preds, 'Other', '__halt_compiler'); return []; }
        if ($s instanceof Stmt\InlineHTML) return [$this->add($f, $s, $preds, 'InlineHTML', substr($s->value, 0, MAX_TEXT), [])];
        if ($s instanceof Stmt\Global_) return [$this->add($f, $s, $preds, 'Global', null, [], [$s->vars])];
        if ($s instanceof Stmt\Static_) return [$this->add($f, $s, $preds, 'Other', null, array_map(fn($v) => $v->default, $s->vars), array_map(fn($v) => $v->var, $s->vars))];
        if ($s instanceof Stmt\Expression) {
            $i = $this->add($f, $s, $preds, null, null, [$s->expr]);
            if ($s->expr instanceof Expr\Throw_ || $s->expr instanceof Expr\Exit_) return [];
            return $this->lastExits ?? [$i];              // có mã ghép -> luồng đi tiếp qua nó
        }
        // Echo, Unset, Const, Use, Label, Goto, Property... -> nút đơn
        $own = [];
        foreach ($s->getSubNodeNames() as $sn) if ($sn !== 'stmts') $own[] = $s->$sn;
        $i = $this->add($f, $s, $preds, null, null, $own);
        return $this->lastExits ?? [$i];
    }
}

function fallback_tokens(string $src): array
{
    // Tách statement theo ; { } trên token_get_all; CFG tuần tự; def = "$x =".
    // Không có AST: call node = T_STRING / T_VARIABLE đứng ngay trước '(' theo cú pháp tokenizer PHP (gọi động
    // -> '<dyncall>'); construct = T_EVAL/T_INCLUDE*/T_REQUIRE* và backtick (-> shell_exec). Literal chuỗi là
    // T_CONSTANT_ENCAPSED_STRING nên không bao giờ thành call node.
    $f = ['name' => '<main>', 'stmts' => [], 'cfg' => []];
    $cur = ['tokens' => [], 'text' => '', 'defs' => [], 'uses' => [], 'calls' => [], 'constructs' => []];
    $inTick = false;
    $prevVar = null; $prevTok = null;
    $flush = function () use (&$f, &$cur) {
        if ($cur['tokens'] || trim($cur['text']) !== '') {
            $i = count($f['stmts']);
            if ($i >= MAX_STMT_FN) return;
            $f['stmts'][] = ['kind' => 'Other', 'text' => substr($cur['text'], 0, MAX_TEXT), 'tokens' => array_slice($cur['tokens'], 0, MAX_TOK),
                'defs' => array_keys($cur['defs']), 'uses' => array_keys($cur['uses']), 'calls' => array_keys($cur['calls']),
                'constructs' => array_keys($cur['constructs']), 'line' => 0];
            if ($i > 0) $f['cfg'][] = [$i - 1, $i];
        }
        $cur = ['tokens' => [], 'text' => '', 'defs' => [], 'uses' => [], 'calls' => [], 'constructs' => []];
    };
    $toks = @token_get_all($src);
    $skip = [T_WHITESPACE, T_COMMENT, T_DOC_COMMENT];
    $nextIsParen = function (int $k) use ($toks, $skip): bool {
        for ($j = $k + 1, $n = count($toks); $j < $n; $j++) {
            if (is_array($toks[$j]) && in_array($toks[$j][0], $skip, true)) continue;
            return $toks[$j] === '(';
        }
        return false;
    };
    foreach ($toks as $k => $t) {
        [$id, $s] = is_array($t) ? [$t[0], $t[1]] : [null, $t];
        if ($id === T_WHITESPACE || $id === T_COMMENT || $id === T_DOC_COMMENT || $id === T_OPEN_TAG || $id === T_CLOSE_TAG) continue;
        if (strlen($cur['text']) < MAX_TEXT) $cur['text'] .= $s . ' ';
        if ($id === T_VARIABLE) {
            if ($nextIsParen($k)) { $cur['tokens'][] = '<dyncall>'; $cur['calls']['<dyncall>'] = 1; }
            $cur['tokens'][] = $s; $prevVar = substr($s, 1); $cur['uses'][$prevVar] = 1;
        }
        elseif ($id === T_STRING) { $cur['tokens'][] = strtolower($s); if ($nextIsParen($k)) $cur['calls'][strtolower($s)] = 1; }
        elseif (in_array($id, [T_EVAL, T_INCLUDE, T_INCLUDE_ONCE, T_REQUIRE, T_REQUIRE_ONCE], true)) { $cur['tokens'][] = strtolower($s); $cur['constructs'][strtolower($s)] = 1; }
        elseif (in_array($id, [T_EXIT, T_PRINT, T_ECHO], true)) $cur['tokens'][] = strtolower($s);
        elseif ($id === null && $s === '`') { if (!$inTick) { $cur['tokens'][] = 'shell_exec'; $cur['constructs']['shell_exec'] = 1; } $inTick = !$inTick; }
        elseif ($id === T_CONSTANT_ENCAPSED_STRING) { $v = substr($s, 1, -1); $cur['tokens'][] = strlen($v) <= MAX_LIT ? $v : (strlen($v) > 256 ? '<longstr>' : '<str>'); }
        elseif ($id === null && $s === '=' && $prevTok === T_VARIABLE) { $cur['defs'][$prevVar] = 1; unset($cur['uses'][$prevVar]); $cur['tokens'][] = '='; }
        elseif ($id === null && $s === '(') $cur['tokens'][] = '(';
        elseif ($id === T_INLINE_HTML) $cur['tokens'][] = '<html>';
        $prevTok = $id;
        if ($id === null && ($s === ';' || $s === '{' || $s === '}')) $flush();
    }
    $flush();
    return [$f];
}

function process(string $path, bool $deobf = true): array
{
    $out = ['path' => $path, 'status' => 'ok', 'parser' => null, 'n_errors' => 0, 'error' => null,
            'functions' => [], 'n_includes' => 0, 'n_stmt_total' => 0, 'deobf' => ['enabled' => $deobf]];
    $src = @file_get_contents($path);
    if ($src === false) { $out['status'] = 'unreadable'; return $out; }
    $src = canonicalize($src);                 // parse + text node đều trên bản chuẩn hoá
    $out['canon_b64'] = base64_encode($src);   // Python dùng làm source_text (cùng một bản)
    $best = null;
    foreach (['8.4', '7.0'] as $ver) {
        $h = new ErrorHandler\Collecting();
        try {
            $ast = (new ParserFactory())->createForVersion(PhpVersion::fromString($ver))->parse($src, $h);
            $cand = ['ver' => $ver, 'ast' => $ast ?? [], 'errs' => $h->getErrors()];
        } catch (\Throwable $e) {
            $cand = ['ver' => $ver, 'ast' => null, 'errs' => [$e]];
        }
        if ($best === null || ($cand['ast'] !== null && ($best['ast'] === null || count($cand['errs']) < count($best['errs'])))) $best = $cand;
        if ($cand['ast'] !== null && !$cand['errs']) break;
    }
    $out['n_errors'] = count($best['errs']);
    if ($best['errs']) $out['error'] = substr($best['errs'][0]->getMessage(), 0, 300);
    if ($best['ast'] !== null && ($best['ast'] || !$best['errs'])) {
        try {
            $fl = new Flattener($src, $deobf);
            $fl->newFn('<main>', $best['ast']);
            $out['parser'] = $best['ver'];
            $out['status'] = $best['errs'] ? 'recovered' : 'ok';
            // <main> phải là functions[0]: newFn đệ quy thêm hàm con trước khi <main> xong, nhưng <main> được push trước.
            $out['functions'] = array_map(fn(Fn_ $f) => ['name' => $f->name, 'params' => $f->params, 'stmts' => $f->stmts, 'cfg' => $f->cfg], $fl->fns);
            $out['n_includes'] = $fl->nIncludes;
            $out['n_stmt_total'] = $fl->nTotal;
            $out['deobf'] = $fl->deobf;
            return $out;
        } catch (\Throwable $e) {
            $out['error'] = 'flatten: ' . substr($e->getMessage(), 0, 300);
        }
    }
    $out['status'] = 'fallback_tokens';
    $out['functions'] = fallback_tokens($src);
    $out['n_stmt_total'] = count($out['functions'][0]['stmts']);
    return $out;
}

$J = JSON_INVALID_UTF8_SUBSTITUTE | JSON_UNESCAPED_SLASHES | JSON_PARTIAL_OUTPUT_ON_ERROR;
$args = array_slice($argv, 1);
$DEOBF = !in_array('--no-deobf', $args, true);
$args = array_values(array_filter($args, fn($a) => $a !== '--no-deobf'));
if (($args[0] ?? '') === '--batch') {
    while (($line = fgets(STDIN)) !== false) {
        $p = rtrim($line, "\r\n");
        if ($p === '') continue;
        echo json_encode(process($p, $DEOBF), $J), "\n";
        flush();
    }
} elseif (isset($args[0])) {
    echo json_encode(process($args[0], $DEOBF), $J), "\n";
} else {
    fwrite(STDERR, "usage: dump_ast.php [--no-deobf] <file.php> | [--no-deobf] --batch < paths\n");
    exit(2);
}
