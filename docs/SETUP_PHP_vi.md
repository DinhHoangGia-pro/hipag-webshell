# Cài PHP parser (nikic/PHP-Parser)

```bash
sudo apt-get install -y php-cli composer
composer require nikic/php-parser
# kiểm tra:
php tools/php/dump_ast.php path/to/sample.php | head
```
Lưu ý: file obfuscation nặng (eval lồng nhiều lớp) có thể parse-fail — ghi vào experiments/dataset/parse_fail.csv,
đừng loại âm thầm (ảnh hưởng external validity, RQF-05).
