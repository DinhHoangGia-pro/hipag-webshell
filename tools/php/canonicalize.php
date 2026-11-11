<?php
// Batch chuẩn hoá cho probe: paths trên stdin -> JSON/dòng {"path", "ok", "canon_b64"} (base64 = giữ nguyên byte).
//   php -d short_open_tag=1 tools/php/canonicalize.php < paths
declare(strict_types=1);
require __DIR__ . '/canon_lib.php';

while (($line = fgets(STDIN)) !== false) {
    $p = rtrim($line, "\r\n");
    if ($p === '') continue;
    $src = @file_get_contents($p);
    echo json_encode($src === false ? ['path' => $p, 'ok' => false]
        : ['path' => $p, 'ok' => true, 'canon_b64' => base64_encode(canonicalize($src))], JSON_UNESCAPED_SLASHES), "\n";
    flush();
}
