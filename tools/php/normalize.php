<?php
// Chuẩn hoá mã nguồn cho dedup (RQF-05, configs/dataset/dedup.yaml):
// token_get_all -> bỏ comment + whitespace (+ tuỳ chọn lowercase) -> chuỗi token.
//   php -d short_open_tag=1 tools/php/normalize.php [--lower] < paths  -> 1 dòng JSON / path:
//   {"path", "ok", "norm_sha1", "n_tok", "tokens": [<= MAX_TOK token đầu, dùng cho MinHash]}
declare(strict_types=1);
const MAX_TOK = 20000;

$lower = in_array('--lower', $argv, true);
$J = JSON_INVALID_UTF8_SUBSTITUTE | JSON_UNESCAPED_SLASHES | JSON_PARTIAL_OUTPUT_ON_ERROR;
while (($line = fgets(STDIN)) !== false) {
    $p = rtrim($line, "\r\n");
    if ($p === '') continue;
    $src = @file_get_contents($p);
    if ($src === false) { echo json_encode(['path' => $p, 'ok' => false], $J), "\n"; continue; }
    $toks = [];
    foreach (@token_get_all($src) as $t) {
        if (is_array($t)) {
            if ($t[0] === T_WHITESPACE || $t[0] === T_COMMENT || $t[0] === T_DOC_COMMENT) continue;
            $s = $t[0] === T_INLINE_HTML ? preg_replace('/\s+/', ' ', trim($t[1])) : trim($t[1]);
            if ($s === '') continue;
        } else $s = $t;
        $toks[] = $lower ? strtolower($s) : $s;
    }
    echo json_encode(['path' => $p, 'ok' => true, 'norm_sha1' => sha1(implode("\x01", $toks)),
        'n_tok' => count($toks), 'tokens' => array_slice($toks, 0, MAX_TOK)], $J), "\n";
    flush();
}
