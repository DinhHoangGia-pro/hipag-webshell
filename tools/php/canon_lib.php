<?php
// Chuẩn hoá đầu vào (chốt PHIÊN DATA 2026-11-07): model + probe KHÔNG thấy phong cách.
// Mức token (token_get_all) — không đụng nội dung chuỗi/heredoc/inline HTML:
//   * bỏ T_COMMENT / T_DOC_COMMENT; dòng chỉ chứa comment bị xoá hẳn (cả thụt lề); comment sau code -> ' ' hoặc "\n"
//   * bỏ thẻ đóng PHP ở CUỐI file (khi sau nó chỉ còn khoảng trắng)
//   * CRLF -> LF chỉ trong token khoảng trắng
// Dùng chung: tools/php/dump_ast.php (parse + text node) và tools/php/canonicalize.php (probe).
declare(strict_types=1);

function canonicalize(string $src): string
{
    $toks = @token_get_all($src);
    $n = count($toks);
    // thẻ đóng cuối file: T_CLOSE_TAG theo sau chỉ bởi khoảng trắng / inline HTML toàn khoảng trắng
    $cut = $n;
    for ($i = $n - 1; $i >= 0; $i--) {
        $t = $toks[$i];
        if (is_array($t) && ($t[0] === T_WHITESPACE || ($t[0] === T_INLINE_HTML && trim($t[1]) === ''))) continue;
        if (is_array($t) && $t[0] === T_CLOSE_TAG) $cut = $i;
        break;
    }
    $o = '';
    $dropNl = false;   // sau block comment đứng riêng một dòng: bỏ newline đầu của khoảng trắng kế tiếp
    for ($i = 0; $i < $cut; $i++) {
        $t = $toks[$i];
        if (!is_array($t)) { $o .= $t; $dropNl = false; continue; }
        [$id, $s] = [$t[0], $t[1]];
        if ($id === T_COMMENT || $id === T_DOC_COMMENT) {
            $p = strrpos($o, "\n");
            $lineHead = $p === false ? $o : substr($o, $p + 1);
            $ownLine = trim($lineHead) === '' && $o !== '' && ($p !== false || trim($o) === '');
            $endsNl = str_ends_with($s, "\n");
            if ($ownLine && $p !== false) {
                $o = substr($o, 0, $p + 1);           // xoá thụt lề trước comment
                $dropNl = !$endsNl;                    // block comment: nuốt newline kế tiếp
            } else {
                $o .= $endsNl ? "\n" : ' ';
                $dropNl = false;
            }
            continue;
        }
        if ($id === T_OPEN_TAG) { $o .= str_replace("\r\n", "\n", $s); $dropNl = false; continue; }
        if ($id === T_WHITESPACE) {
            $s = str_replace("\r\n", "\n", $s);
            if ($dropNl && str_starts_with($s, "\n")) $s = substr($s, 1);
            $dropNl = false;
            $o .= $s;
            continue;
        }
        $dropNl = false;
        $o .= $s;
    }
    if ($cut < $n) {
        // Thẻ đóng PHP là dấu ';' NGẦM: `@eval($a)` + thẻ đóng hợp lệ, bỏ thẻ đi thì phải thêm ';'.
        $prev = null;
        for ($i = $cut - 1; $i >= 0; $i--) {
            $t = $toks[$i];
            if (is_array($t) && in_array($t[0], [T_WHITESPACE, T_COMMENT, T_DOC_COMMENT], true)) continue;
            $prev = is_array($t) ? $t[0] : $t;
            break;
        }
        $o = rtrim($o);
        if ($prev !== ';' && $prev !== '}' && $prev !== T_OPEN_TAG && $prev !== null) $o .= ';';
        $o .= "\n";
    }
    return $o;
}
