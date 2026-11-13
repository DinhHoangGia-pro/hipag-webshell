# Installing the PHP parser (nikic/PHP-Parser)

*Tiếng Việt: [SETUP_PHP_vi.md](SETUP_PHP_vi.md)*

```bash
sudo apt-get install -y php-cli composer
composer require nikic/php-parser
# check:
php tools/php/dump_ast.php path/to/sample.php | head
```

Note: heavily obfuscated files (deeply nested `eval` layers) may fail to parse. Record them in
`experiments/dataset/parse_fail.csv` rather than silently dropping them (this affects external validity, RQF-05).
