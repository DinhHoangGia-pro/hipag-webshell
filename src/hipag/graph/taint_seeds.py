"""Seed source/sink/decode cho PHP — dùng làm weak-supervision cho Taint-Dependency Predictor (RQF-06)."""

SOURCES = ["$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_FILES", "$_SERVER", "php://input"]

SINKS = [
    "eval", "assert", "system", "exec", "shell_exec", "passthru", "popen", "proc_open",
    "preg_replace",          # /e modifier
    "create_function", "call_user_func", "call_user_func_array",
    "include", "require", "include_once", "require_once",
]

DECODERS = ["base64_decode", "gzinflate", "gzuncompress", "str_rot13", "hex2bin", "convert_uudecode"]
