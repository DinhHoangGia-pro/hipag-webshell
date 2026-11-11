<?php
// Ma trận obfuscation (RQ2/K2, configs/dataset/obfuscation.yaml). Biến đổi trên token_get_all, không regex nguồn.
//   php -d short_open_tag=1 tools/php/obfuscate.php --batch < "LEVEL\tIN\tOUT" lines  -> JSON/dòng {in,level,ok,error}
// L0 none | L1 rename+deadcode (GIỮ-CẤU-TRÚC) | L2 base64_wrap | L3 gzinflate_wrap | L4 var_function | L5 multi_layer = L2∘L4
// Giữ ngữ nghĩa ở mức "chạy giống nhau" với các giới hạn đã biết (ghi trong báo cáo):
//  * L2/L3/L5: mã chạy trong eval -> __FILE__/__DIR__/__LINE__ đổi giá trị.
//  * L4: lời gọi không định danh `foo(` -> `('f'.'oo')(`: luôn gọi hàm TOÀN CỤC (mất fallback namespace);
//        bỏ qua các hàm cấm gọi động (compact, extract, func_get_args, ...), khai báo, method, new, attribute.
declare(strict_types=1);

const NO_DYN = ['compact', 'extract', 'func_get_args', 'func_get_arg', 'func_num_args', 'get_defined_vars',
    'parse_str', 'mb_parse_str', 'array_key_exists', 'define', 'defined', 'constant', 'assert'];

// L1 (GIỮ-CẤU-TRÚC): đổi tên biến cục bộ + chèn code chết (statement thật -> SỐNG SÓT chuẩn hoá canon_lib.php,
// khác comment-insertion cũ bị nuốt sạch). Giữ đồ thị chương trình gần như nguyên: cùng số statement gốc + vài
// statement chết, cùng CFG/DFG/call. Đổi tên BỊ TẮT nếu file có tên biến động ($$x, ${...}) hoặc hàm tra tên biến
// theo chuỗi (compact/extract/get_defined_vars/parse_str/...): khi đó chỉ chèn code chết.
const RESERVED_VARS = ['this', 'GLOBALS', '_GET', '_POST', '_REQUEST', '_COOKIE', '_FILES', '_SERVER', '_ENV',
    '_SESSION', 'HTTP_RAW_POST_DATA', 'http_response_header', 'argv', 'argc', 'php_errormsg'];
const NAME_FROM_VAR = ['compact', 'extract', 'get_defined_vars', 'parse_str', 'mb_parse_str'];

function lvl1(string $src, int $seed): string
{
    mt_srand($seed);
    $toks = token_get_all($src);
    // 1) có an toàn để đổi tên biến không?
    $canRename = !preg_match('/\$\s*[\$\{]/', $src);   // $$x, ${...}, $ {x}
    $existing = [];
    foreach ($toks as $t) {
        if (is_array($t)) {
            if ($t[0] === T_VARIABLE) $existing[substr($t[1], 1)] = 1;
            elseif ($t[0] === T_STRING && in_array(strtolower($t[1]), NAME_FROM_VAR, true)) $canRename = false;
        }
    }
    $n = count($toks);
    // chỉ số '{' mở THÂN HÀM (sau đây cũng là nơi chèn code chết) và '{' mở THÂN CLASS
    $bodyOpen = [];
    $classOpen = [];
    $sig = function ($i, $dir) use ($toks, $n) {
        for ($j = $i + $dir; $j >= 0 && $j < $n; $j += $dir) {
            $t = $toks[$j];
            if (is_array($t) && in_array($t[0], [T_WHITESPACE, T_COMMENT, T_DOC_COMMENT], true)) continue;
            return $j;
        }
        return -1;
    };
    for ($i = 0; $i < $n; $i++) {
        $t = $toks[$i];
        if (is_array($t) && $t[0] === T_FUNCTION) {
            $j = $i + 1;
            while ($j < $n && $toks[$j] !== '(') $j++;
            for ($depth = 0; $j < $n; $j++) {
                if ($toks[$j] === '(') $depth++;
                elseif ($toks[$j] === ')' && --$depth === 0) { $j++; break; }
            }
            for (; $j < $n; $j++) {
                if ($toks[$j] === '{') { $bodyOpen[$j] = 1; break; }
                if ($toks[$j] === ';') break;
            }
        } elseif (is_array($t) && in_array($t[0], [T_CLASS, T_INTERFACE, T_TRAIT, T_ENUM], true)) {
            $pv = $sig($i, -1);
            if ($pv >= 0 && is_array($toks[$pv]) && $toks[$pv][0] === T_DOUBLE_COLON) continue;   // ::class
            for ($j = $i + 1; $j < $n; $j++) if ($toks[$j] === '{') { $classOpen[$j] = 1; break; }
        }
    }
    // tên dùng như THUỘC TÍNH/hằng lớp (->name, ?->name, ::name, ::$name): biến trùng tên -> KHÔNG đổi (an toàn)
    $propNames = [];
    for ($i = 0; $i < $n; $i++) {
        $t = $toks[$i];
        if (is_array($t) && in_array($t[0], [T_OBJECT_OPERATOR, T_NULLSAFE_OBJECT_OPERATOR, T_DOUBLE_COLON], true)) {
            $j = $sig($i, 1);
            if ($j >= 0 && is_array($toks[$j]) && in_array($toks[$j][0], [T_STRING, T_VARIABLE], true))
                $propNames[ltrim($toks[$j][1], '$')] = 1;
        }
    }
    // tên BỊ CHẶN (không đổi ở MỌI nơi): reserved, tên-thuộc-tính, và tên khai báo trực tiếp trong thân class
    // (property / promoted-ctor / static property). Tính TRƯỚC để một tên bị chặn thì chặn toàn cục.
    $blocked = array_flip(RESERVED_VARS) + $propNames;
    $stack = [];   // nhãn ngữ cảnh '{': 'fn' | 'class' | 'block'
    for ($i = 0; $i < $n; $i++) {
        $t = $toks[$i];
        if ($t === '{') { $stack[] = isset($bodyOpen[$i]) ? 'fn' : (isset($classOpen[$i]) ? 'class' : 'block'); continue; }
        if ($t === '}') { array_pop($stack); continue; }
        if (is_array($t) && $t[0] === T_VARIABLE && $stack && end($stack) === 'class')
            $blocked[substr($t[1], 1)] = 1;
    }
    // 2) map đổi tên (thứ tự xuất hiện), gồm biến TRONG chuỗi nội suy -> giữ ngữ nghĩa
    $map = [];
    if ($canRename) {
        $k = 0;
        foreach ($toks as $t) {
            if (is_array($t) && $t[0] === T_VARIABLE) {
                $nm = substr($t[1], 1);
                if (!isset($map[$nm]) && !isset($blocked[$nm])) $map[$nm] = 'v' . $k++;
            }
        }
    }
    // 3) tên biến chết KHÔNG trùng tên đang có / tên đã đổi (tránh đổi ngữ nghĩa âm thầm)
    $used = $existing + array_flip($map);
    $dead = [];
    for ($i = 0; count($dead) < 64; $i++) {
        $cand = 'd' . dechex($seed & 0xffff) . 'x' . $i;
        if (!isset($used[$cand])) $dead[] = $cand;
    }
    $di = 0;
    $deadStmt = function () use (&$di, $dead) {
        $a = '$' . $dead[$di++ % count($dead)];
        $b = '$' . $dead[$di++ % count($dead)];
        return "$a = " . mt_rand(2, 9999) . "; $b = $a + " . mt_rand(1, 99) . "; unset($a, $b); ";
    };
    // top-level: chỉ chèn nếu lệnh ĐẦU TIÊN không phải namespace/declare (phải đứng trước mọi statement)
    $skipTop = true;
    for ($i = 0; $i < $n; $i++) {
        if (is_array($toks[$i]) && $toks[$i][0] === T_OPEN_TAG) {
            $j = $sig($i, 1);
            $skipTop = $j >= 0 && is_array($toks[$j]) && in_array($toks[$j][0], [T_NAMESPACE, T_DECLARE], true);
            break;
        }
    }
    // 4) xuất (chèn code chết ở top-level sau thẻ mở + đầu mỗi thân hàm — đều là statement-context)
    $o = '';
    $openTagDone = false;
    for ($i = 0; $i < $n; $i++) {
        $t = $toks[$i];
        if (is_array($t) && $t[0] === T_VARIABLE) {
            $nm = substr($t[1], 1);
            $o .= isset($map[$nm]) ? '$' . $map[$nm] : $t[1];
        } else {
            $o .= is_array($t) ? $t[1] : $t;
        }
        if (is_array($t) && $t[0] === T_OPEN_TAG && !$openTagDone) {
            $openTagDone = true;
            if (!$skipTop) $o .= $deadStmt();                   // top-level: statement-context
        } elseif (!is_array($t) && $t === '{' && isset($bodyOpen[$i])) {
            $o .= ' ' . $deadStmt();                            // đầu thân hàm
        }
    }
    return $o;
}

function random_bytes_seeded(int $n): string
{
    $b = '';
    for ($i = 0; $i < $n; $i++) $b .= chr(mt_rand(0, 255));
    return $b;
}

function sig(array $toks, int $i, int $dir): int
{   // chỉ số token có nghĩa kế tiếp theo hướng $dir (bỏ whitespace/comment); -1 nếu hết
    for ($j = $i + $dir; $j >= 0 && $j < count($toks); $j += $dir) {
        $t = $toks[$j];
        if (is_array($t) && in_array($t[0], [T_WHITESPACE, T_COMMENT, T_DOC_COMMENT], true)) continue;
        return $j;
    }
    return -1;
}

function lvl4(string $src): array
{
    $toks = token_get_all($src);
    $o = ''; $n = 0; $attrDepth = 0;
    // File có namespace: gọi qua chuỗi luôn tra hàm TOÀN CỤC -> hàm tự định nghĩa trong file (thuộc namespace)
    // sẽ không tìm thấy. Bỏ qua các tên đó để giữ ngữ nghĩa.
    $localFns = [];
    $hasNs = false;
    foreach ($toks as $i => $t) {
        if (is_array($t) && $t[0] === T_NAMESPACE) $hasNs = true;
        if (is_array($t) && $t[0] === T_FUNCTION) {
            $j = sig($toks, $i, 1);
            if ($j >= 0 && !is_array($toks[$j]) && $toks[$j] === '&') $j = sig($toks, $j, 1);
            if ($j >= 0 && is_array($toks[$j]) && $toks[$j][1] === '&') $j = sig($toks, $j, 1);
            if ($j >= 0 && is_array($toks[$j]) && $toks[$j][0] === T_STRING) $localFns[strtolower($toks[$j][1])] = 1;
        }
    }
    if (!$hasNs) $localFns = [];
    $skipPrev = [T_FUNCTION, T_OBJECT_OPERATOR, T_NULLSAFE_OBJECT_OPERATOR, T_DOUBLE_COLON, T_NEW, T_CONST,
                 T_NS_SEPARATOR, T_USE, T_INSTANCEOF, T_CLASS, T_INTERFACE, T_TRAIT, T_EXTENDS, T_IMPLEMENTS, T_GOTO];
    foreach ($toks as $i => $t) {
        if (is_array($t) && $t[0] === T_ATTRIBUTE) { $attrDepth = 1; $o .= $t[1]; continue; }
        if ($attrDepth > 0 && !is_array($t)) {
            if ($t === '[') $attrDepth++;
            elseif ($t === ']') $attrDepth--;
        }
        if ($attrDepth === 0 && is_array($t) && $t[0] === T_STRING) {
            $nx = sig($toks, $i, 1); $pv = sig($toks, $i, -1);
            $isCall = $nx >= 0 && $toks[$nx] === '(';
            $pvTok = $pv >= 0 ? $toks[$pv] : null;
            $pvId = is_array($pvTok) ? ($pvTok[1] === '&' ? '&' : $pvTok[0]) : $pvTok;   // PHP8: '&' là T_AMPERSAND_*
            if ($pvId === '&') { $pp = sig($toks, $pv, -1); if ($pp >= 0 && is_array($toks[$pp]) && $toks[$pp][0] === T_FUNCTION) $pvId = T_FUNCTION; }
            $name = $t[1];
            if ($isCall && !in_array($pvId, $skipPrev, true) && !in_array(strtolower($name), NO_DYN, true)
                && !isset($localFns[strtolower($name)]) && strlen($name) >= 2) {
                $k = intdiv(strlen($name), 2);
                $o .= "('" . substr($name, 0, $k) . "'.'" . substr($name, $k) . "')";
                $n++;
                continue;
            }
        }
        $o .= is_array($t) ? $t[1] : $t;
    }
    return [$o, $n];
}

function payload(string $src): string
{   /* file bắt đầu bằng thẻ mở PHP: eval phần sau thẻ mở; ngược lại eval bắt đầu ở chế độ HTML (tiền tố thẻ đóng) */
    if (preg_match('/^(\xEF\xBB\xBF)?<\?php\s/i', $src)) {
        return preg_replace('/^(\xEF\xBB\xBF)?<\?php\s/i', '', $src, 1);
    }
    return '?>' . $src;
}

function lvl2(string $src): string { return "<?php eval(base64_decode('" . base64_encode(payload($src)) . "'));\n"; }
function lvl3(string $src): string { return "<?php eval(gzinflate(base64_decode('" . base64_encode(gzdeflate(payload($src), 9)) . "')));\n"; }

function apply(string $level, string $src, int $seed): array
{
    switch ($level) {
        case 'L0': return [$src, 0];
        case 'L1': return [lvl1($src, $seed), 0];
        case 'L2': return [lvl2($src), 0];
        case 'L3': return [lvl3($src), 0];
        case 'L4': return lvl4($src);
        case 'L5': [$s, $n] = lvl4($src); return [lvl2($s), $n];
    }
    throw new InvalidArgumentException("level? $level");
}

$J = JSON_INVALID_UTF8_SUBSTITUTE | JSON_UNESCAPED_SLASHES;
while (($line = fgets(STDIN)) !== false) {
    $line = rtrim($line, "\r\n");
    if ($line === '') continue;
    [$level, $in, $out] = explode("\t", $line);
    $r = ['in' => $in, 'level' => $level, 'ok' => false, 'error' => null, 'n_dyncall' => 0];
    try {
        $src = file_get_contents($in);
        [$o, $n] = apply($level, $src, crc32($in));
        @mkdir(dirname($out), 0777, true);
        file_put_contents($out, $o);
        $r['ok'] = true; $r['n_dyncall'] = $n;
    } catch (\Throwable $e) { $r['error'] = substr($e->getMessage(), 0, 200); }
    echo json_encode($r, $J), "\n";
    flush();
}
