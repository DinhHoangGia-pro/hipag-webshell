<?php
// UPG-02 — giải vỏ TĨNH (static deobfuscation) cho dump_ast.php. KHÔNG eval / execute / include bất cứ thứ gì.
//
// deobf_fold($expr)  : constant-fold biểu thức gồm literal chuỗi, phép nối '.' giữa các literal, và hàm decoder
//                      (DEOBF_DECODERS) lồng nhau — fold từ TRONG ra. Đối số không phải hằng -> 'not_literal'
//                      (luồng source->decoder->sink vốn đã thấy trong đồ thị). Hàm decoder được gọi qua bảng
//                      match CỐ ĐỊNH (deobf_decode) — không bao giờ gọi hàm theo tên động.
// deobf_parse($code) : parse chuỗi đã giải như mã PHP; chỉ chấp nhận khi parse KHÔNG lỗi và có ≥1 statement thật.
//                      Blob nhị phân (ảnh/font) / text thường -> null -> caller coi là literal dữ liệu.
// deobf_const_env($stmts): const-propagation HẸP cho MỘT scope — biến gán ĐÚNG MỘT LẦN từ literal (gồm nối
//                      literal), không gán lại / ghi theo cách khác, không superglobal / tham số -> được thế bằng
//                      literal khi làm đối số decoder (sau vị trí gán). Không phải dataflow đầy đủ.
// Giới hạn an toàn: ≤ DEOBF_MAX_DEPTH lớp decoder; mọi chuỗi trung gian ≤ DEOBF_MAX_BYTES; họ gz* giải nén
// TĂNG DẦN (inflate_add, 1KB/lần) và dừng ngay khi vượt ngưỡng -> không cấp phát cả quả decompression bomb.
declare(strict_types=1);

use PhpParser\ErrorHandler;
use PhpParser\Node;
use PhpParser\Node\Expr;
use PhpParser\Node\Scalar;
use PhpParser\Node\Stmt;
use PhpParser\ParserFactory;
use PhpParser\PhpVersion;

const DEOBF_DECODERS = ['base64_decode', 'gzinflate', 'gzuncompress', 'gzdecode', 'str_rot13', 'hex2bin',
                        'convert_uudecode', 'urldecode', 'strrev'];
const DEOBF_MAX_DEPTH = 5;            // số lớp decoder lồng tối đa trong MỘT biểu thức
const DEOBF_MAX_BYTES = 5242880;      // 5MB: chuỗi vào/ra vượt ngưỡng -> bỏ (too_big)
const DEOBF_MAX_GRAFT_DEPTH = 5;      // eval(decode(..)) lồng trong mã đã giải -> tối đa 5 tầng ghép
const DEOBF_MAX_GRAFTS = 64;          // số lần ghép tối đa / file
const DEOBF_INFLATE_CHUNK = 1024;     // 1KB nén/lần -> mỗi bước ra ≤ ~1MB (tỉ lệ deflate tối đa ~1032:1)

/** Giải nén tăng dần; dừng ngay khi đầu ra vượt DEOBF_MAX_BYTES. Trả [string|null, lý do|null]. */
function deobf_inflate(string $data, int $encoding): array
{
    $ctx = @inflate_init($encoding);
    if ($ctx === false) return [null, 'decode_fail'];
    $out = '';
    for ($o = 0, $n = strlen($data); $o < $n; $o += DEOBF_INFLATE_CHUNK) {
        $part = @inflate_add($ctx, substr($data, $o, DEOBF_INFLATE_CHUNK), ZLIB_SYNC_FLUSH);
        if ($part === false) return [null, 'decode_fail'];
        $out .= $part;
        if (strlen($out) > DEOBF_MAX_BYTES) return [null, 'too_big'];
    }
    $part = @inflate_add($ctx, '', ZLIB_FINISH);
    if ($part === false) return [null, 'decode_fail'];
    $out .= $part;
    return strlen($out) > DEOBF_MAX_BYTES ? [null, 'too_big'] : [$out, null];
}

/** Một decoder (whitelist, hàm chuỗi thuần) trên một chuỗi. Trả [string|null, lý do|null]. */
function deobf_decode(string $name, string $s): array
{
    $r = match ($name) {
        'base64_decode' => base64_decode($s),
        'str_rot13' => str_rot13($s),
        'hex2bin' => (strlen($s) % 2 === 0 && ctype_xdigit($s)) ? hex2bin($s) : false,
        'convert_uudecode' => $s === '' ? false : @convert_uudecode($s),
        'urldecode' => urldecode($s),
        'strrev' => strrev($s),
        'gzinflate' => deobf_inflate($s, ZLIB_ENCODING_RAW),
        'gzuncompress' => deobf_inflate($s, ZLIB_ENCODING_DEFLATE),
        'gzdecode' => deobf_inflate($s, ZLIB_ENCODING_GZIP),
        default => false,
    };
    if (is_array($r)) return $r;
    if ($r === false || $r === null) return [null, 'decode_fail'];
    return strlen($r) > DEOBF_MAX_BYTES ? [null, 'too_big'] : [$r, null];
}

const DEOBF_SUPERGLOBALS = ['GLOBALS', '_GET', '_POST', '_REQUEST', '_COOKIE', '_SERVER', '_FILES', '_SESSION', '_ENV',
                            'HTTP_RAW_POST_DATA', 'HTTP_POST_VARS', 'HTTP_GET_VARS', 'HTTP_COOKIE_VARS',
                            'HTTP_REQUEST_VARS', 'HTTP_SERVER_VARS', 'HTTP_POST_FILES', 'argv', 'argc', 'this'];
// Hàm ghi đè biến trong scope theo cách không thấy tĩnh -> TẮT const-prop cả scope.
const DEOBF_SCOPE_KILLERS = ['extract', 'parse_str', 'mb_parse_str', 'import_request_variables'];

/** Literal hằng: chuỗi, hoặc nối '.' giữa các literal. Không phải -> null. */
function deobf_literal(Node $e): ?string
{
    if ($e instanceof Scalar\String_) return $e->value;
    if ($e instanceof Expr\BinaryOp\Concat) {
        $l = deobf_literal($e->left);
        $r = $l === null ? null : deobf_literal($e->right);
        if ($r === null || strlen($l) + strlen($r) > DEOBF_MAX_BYTES) return null;
        return $l . $r;
    }
    return null;
}

/** Đánh dấu mọi biến xuất hiện trong một đích ghi (vd $k[0], list($a,$b), $o->p) là KHÔNG hằng. */
function deobf_mark_vars($n, array &$bad): void
{
    if (!$n instanceof Node) return;
    foreach ((new \PhpParser\NodeFinder())->findInstanceOf($n, Expr\Variable::class) as $v)
        if (is_string($v->name)) $bad[$v->name] = true;
    if ($n instanceof Expr\Variable && is_string($n->name)) $bad[$n->name] = true;
}

/** Duyệt MỘT scope (không vào hàm/class/closure lồng) để thu phép gán. Hàm có tên — không gọi closure qua biến. */
function deobf_const_walk($n, array &$st): void
{
    if (is_array($n)) { foreach ($n as $x) deobf_const_walk($x, $st); return; }
    if (!$n instanceof Node) return;
    if ($n instanceof Stmt\Function_ || $n instanceof Stmt\ClassLike || $n instanceof Expr\ArrowFunction) return;
    if ($n instanceof Expr\Closure) {
        foreach ($n->uses as $u) if ($u->byRef) deobf_mark_vars($u->var, $st['bad']);   // use (&$k) ghi được
        return;
    }
    if ($n instanceof Expr\Variable && !is_string($n->name)) $st['kill'] = true;        // $$x
    if ($n instanceof Expr\Assign) {
        if ($n->var instanceof Expr\Variable && is_string($n->var->name)) {
            $nm = $n->var->name;
            $st['count'][$nm] = ($st['count'][$nm] ?? 0) + 1;
            $lit = deobf_literal($n->expr);
            if ($lit === null) $st['bad'][$nm] = true;
            else $st['val'][$nm] = ['val' => $lit, 'pos' => $n->getEndFilePos()];
        } else deobf_mark_vars($n->var, $st['bad']);                                   // $k[0]=, list(..)=, $o->p=
    } elseif ($n instanceof Expr\AssignOp || $n instanceof Expr\AssignRef || $n instanceof Expr\PreInc
              || $n instanceof Expr\PostInc || $n instanceof Expr\PreDec || $n instanceof Expr\PostDec) {
        deobf_mark_vars($n->var, $st['bad']);
    } elseif ($n instanceof Stmt\Foreach_) {
        deobf_mark_vars($n->keyVar, $st['bad']); deobf_mark_vars($n->valueVar, $st['bad']);
    } elseif ($n instanceof Stmt\Global_ || $n instanceof Stmt\Unset_) {
        foreach ($n->vars as $v) deobf_mark_vars($v, $st['bad']);
    } elseif ($n instanceof Stmt\Static_) {
        foreach ($n->vars as $v) deobf_mark_vars($v->var, $st['bad']);
    } elseif ($n instanceof Stmt\Catch_) {
        deobf_mark_vars($n->var, $st['bad']);
    } elseif ($n instanceof Expr\FuncCall || $n instanceof Expr\MethodCall || $n instanceof Expr\StaticCall
              || $n instanceof Expr\NullsafeMethodCall || $n instanceof Expr\New_) {
        $fn = ($n instanceof Expr\FuncCall && $n->name instanceof Node\Name) ? strtolower($n->name->getLast()) : null;
        if ($n instanceof Expr\FuncCall && $fn === null) $st['kill'] = true;           // gọi động: có thể là extract
        if ($fn !== null && in_array($fn, DEOBF_SCOPE_KILLERS, true)) $st['kill'] = true;
        if ($fn === null || !in_array($fn, DEOBF_DECODERS, true))                      // có thể truyền tham chiếu
            foreach ($n->args ?? [] as $a)
                if ($a instanceof Node\Arg && $a->value instanceof Expr\Variable) deobf_mark_vars($a->value, $st['bad']);
    }
    foreach ($n->getSubNodeNames() as $sn) deobf_const_walk($n->$sn, $st);
}

/** Const-propagation HẸP cho một scope. Trả [tên biến => ['val' => literal, 'pos' => vị trí kết thúc phép gán]]. */
function deobf_const_env(array $stmts, array $params = []): array
{
    $st = ['count' => [], 'val' => [], 'kill' => false,
           'bad' => array_fill_keys(array_filter($params, 'is_string'), true)];   // tham số: gán lúc vào hàm
    deobf_const_walk($stmts, $st);
    if ($st['kill']) return [];
    $env = [];
    foreach ($st['val'] as $nm => $v)
        if (($st['count'][$nm] ?? 0) === 1 && empty($st['bad'][$nm]) && !in_array($nm, DEOBF_SUPERGLOBALS, true))
            $env[$nm] = $v;
    return $env;
}

/** Constant-fold. $env: hằng của scope (deobf_const_env; 'pos' < 0 = bỏ kiểm vị trí, dùng trong mã ghép).
 *  Trả ['ok'=>true,'val'=>string,'layers'=>int,'consts'=>int] hoặc ['ok'=>false,'reason'=>string]. */
function deobf_fold(Node $e, int $depth = 0, array $env = []): array
{
    if ($e instanceof Expr\ErrorSuppress) return deobf_fold($e->expr, $depth, $env);
    if ($e instanceof Expr\Variable && $depth > 0 && is_string($e->name) && isset($env[$e->name])) {
        $c = $env[$e->name];                                   // chỉ trong đối số decoder, sau phép gán duy nhất
        if ($c['pos'] < 0 || $c['pos'] < $e->getStartFilePos())
            return ['ok' => true, 'val' => $c['val'], 'layers' => 0, 'consts' => 1];
    }
    if ($e instanceof Scalar\String_) {
        return strlen($e->value) > DEOBF_MAX_BYTES ? ['ok' => false, 'reason' => 'too_big']
                                                  : ['ok' => true, 'val' => $e->value, 'layers' => 0, 'consts' => 0];
    }
    if ($e instanceof Expr\BinaryOp\Concat) {
        $l = deobf_fold($e->left, $depth, $env);
        if (!$l['ok']) return $l;
        $r = deobf_fold($e->right, $depth, $env);
        if (!$r['ok']) return $r;
        if (strlen($l['val']) + strlen($r['val']) > DEOBF_MAX_BYTES) return ['ok' => false, 'reason' => 'too_big'];
        return ['ok' => true, 'val' => $l['val'] . $r['val'], 'layers' => max($l['layers'], $r['layers']),
                'consts' => $l['consts'] + $r['consts']];
    }
    if ($e instanceof Expr\FuncCall && $e->name instanceof Node\Name) {
        $nm = strtolower($e->name->getLast());
        $a0 = $e->args[0] ?? null;
        if (in_array($nm, DEOBF_DECODERS, true) && $a0 instanceof Node\Arg && !$a0->unpack) {
            if ($depth >= DEOBF_MAX_DEPTH) return ['ok' => false, 'reason' => 'too_deep'];
            $in = deobf_fold($a0->value, $depth + 1, $env);
            if (!$in['ok']) return $in;
            [$v, $why] = deobf_decode($nm, $in['val']);
            if ($v === null) return ['ok' => false, 'reason' => $why];
            return ['ok' => true, 'val' => $v, 'layers' => $in['layers'] + 1, 'consts' => $in['consts']];
        }
    }
    return ['ok' => false, 'reason' => 'not_literal'];
}

/** Parse chuỗi đã giải như mã PHP (thân eval: không có thẻ mở -> thêm '<?php '). Trả [src, ast] hoặc null. */
function deobf_parse(string $code): ?array
{
    $src = preg_match('/^\s*<\?/', $code) ? $code : "<?php " . $code;
    foreach (['8.4', '7.0'] as $ver) {
        $h = new ErrorHandler\Collecting();
        try {
            $ast = (new ParserFactory())->createForVersion(PhpVersion::fromString($ver))->parse($src, $h);
        } catch (\Throwable $e) {
            continue;
        }
        if ($ast === null || $h->hasErrors()) continue;
        foreach ($ast as $s) {
            if (!$s instanceof Stmt\InlineHTML && !$s instanceof Stmt\Nop) return [$src, $ast];
        }
    }
    return null;
}
