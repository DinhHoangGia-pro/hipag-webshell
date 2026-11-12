# Hồ sơ tái lập HiPaG

Sinh tự động bởi `scripts/repro/make_manifest.py` lúc 2026-11-12T12:35:27+00:00 (UTC). Bản máy đọc: `repro/manifest.json`. Dữ liệu chỉ ghi hash + số đếm, không kèm file.

## Số trích cho paper

| Mục | Giá trị |
|---|---|
| Python | 3.12.16 |
| PyTorch | 2.15.0 |
| PyTorch Geometric | 2.8.1 |
| Transformers | 4.57.6 |
| GPU | NVIDIA GeForce RTX 2080 Super with Max-Q Design (8192 MiB) |
| CUDA (torch build) | 13.2 |
| CUDA (driver max) | 13.0 |
| NVIDIA driver | 580.178.04 |
| cuDNN | 9.26.0 |
| PHP-Parser | v5.9.0 |
| PHP | 8.5.4 |
| CodeBERT revision | 3b0952feddeffad0063f274080e3c23d75e7eb39 |
| OS | Ubuntu 26.04 LTS |
| CPU | Intel(R) Core(TM) i7-10875H CPU @ 2.30GHz |
| RAM (GiB) | 30.6 |

## 1. Nền

- Python 3.12.16 (CPython); Ubuntu 26.04 LTS, kernel 7.0.0-42-generic (x86_64)
- CPU: Intel(R) Core(TM) i7-10875H CPU @ 2.30GHz — 1 socket × 8 nhân, 16 luồng
- RAM: 30.6 GiB

## 2. GPU

- NVIDIA GeForce RTX 2080 Super with Max-Q Design, 8192 MiB VRAM, compute capability 7.5
- Driver 580.178.04 (hỗ trợ tối đa CUDA 13.0); PyTorch build CUDA 13.2, cuDNN 9.26.0
- Thiết bị train theo run (từ ledger/summary): `experiments/runs/rq4_ablation` = cuda; `experiments/runs/rq4_ablation_nodeobf` = cuda; `experiments/runs/rq5_taint_hparams` = cuda; `experiments/runs/rq5_taint_hparams_synthetic` = cpu (synthetic); `experiments/runs/rq1_codebert` = cuda

## 3. Thư viện

| Gói | Phiên bản |
|---|---|
| torch | 2.15.0 |
| torch-geometric | 2.8.1 |
| torch-scatter | không cài |
| torch-sparse | không cài |
| pyg-lib | không cài |
| transformers | 4.57.6 |
| tokenizers | 0.22.2 |
| safetensors | 0.8.0 |
| huggingface-hub | 0.36.2 |
| numpy | 2.5.4 |
| scipy | 1.18.1 |
| scikit-learn | 1.9.1 |
| networkx | 3.7 |
| pandas | 3.1.1 |
| PyYAML | 6.0.3 |
| nvidia-cudnn-cu13 | 9.26.0.51 |
| nvidia-cublas | 13.4.1.3 |
| nvidia-cuda-runtime | 13.2.86 |
| nikic/php-parser (composer) | v5.9.0 (`9e33da9553fe`) |
| PHP | 8.5.4 |

## 4. Seed và determinism

- Seed: [0, 1, 2, 3, 4]
- HiPaG (`src/hipag/utils/seed.py:set_seed`): đặt random.seed, numpy.random.seed, torch.manual_seed, torch.cuda.manual_seed_all, cudnn.deterministic=True, cudnn.benchmark=False, PYTHONHASHSEED_set_at_runtime; KHÔNG đặt tường minh: —
- CodeBERT + baseline harness (`scripts/run_baselines.py:set_seed`): đặt random.seed, numpy.random.seed, torch.manual_seed, torch.cuda.manual_seed_all; KHÔNG đặt tường minh: cudnn.deterministic=True, cudnn.benchmark=False, PYTHONHASHSEED_set_at_runtime
- Mặc định PyTorch khi không đặt: cudnn.deterministic=False, cudnn.benchmark=False.
- `torch.use_deterministic_algorithms`: không; `CUBLAS_WORKSPACE_CONFIG`: không; torch-scatter: không cài; CodeBERT AMP fp16 trên CUDA: có
- PYTHONHASHSEED được gán TRONG tiến trình -> chỉ tác dụng với tiến trình con, không cố định hash của chính nó.
- Không bật torch.use_deterministic_algorithms; scatter của PyG trên CUDA (không có torch-scatter) có thể không tất định tuyệt đối -> kết quả báo mean±sd qua 5 seed.

## 5. CodeBERT

- Model `microsoft/codebert-base`, revision `3b0952feddeffad0063f274080e3c23d75e7eb39` (HF cache refs/main `3b0952feddeffad0063f274080e3c23d75e7eb39`; `from_pretrained` không ghim revision — revision thực tế được ghi vào danh tính run)
- Độ dài: sliding-window 512 stride 384 mean-pool cap8 — 512 tokens including special tokens; window starts advance by 384 content tokens; first 8 windows retained; mean of CodeBERT pooler_output vectors per file
- File chạm giới hạn 8 cửa sổ: train 1998/5312, val 447/1157, test 447/1152, holdout 534/2306
- adamw lr 2e-05, weight decay 0.0001, tối đa 25 epoch, patience 5, chọn theo val_pr_auc+earlystop; batch 8 file / 4 cửa sổ, grad-norm 1.0, gradient checkpointing True
- Loss: unweighted binary_cross_entropy_with_logits (same as harness neural baselines)
- Đầu vào `experiments/runs/rq1_codebert/canonical_inputs.jsonl` sha256 `49581f050c2fbbde6f68b94f363cbf1d5e8e588c87cee6b26066c604e6c30415` (khớp lúc chạy); config `configs/experiment/rq1_codebert.yaml` (khớp lúc chạy)

| Seed | run_fingerprint | best epoch | epoch chạy | val PR-AUC | giờ |
|---|---|---|---|---|---|
| 0 | `fcbc53201aaed2e8b78aef3656928497927049951b843a8f9629733b17103398` | 11 | 16 | 0.9988 | 3.02 |
| 1 | `fcbc53201aaed2e8b78aef3656928497927049951b843a8f9629733b17103398` | 4 | 9 | 0.9991 | 1.8 |
| 2 | `fcbc53201aaed2e8b78aef3656928497927049951b843a8f9629733b17103398` | 15 | 20 | 0.9989 | 3.86 |
| 3 | `fcbc53201aaed2e8b78aef3656928497927049951b843a8f9629733b17103398` | 6 | 11 | 0.9994 | 2.43 |
| 4 | `fcbc53201aaed2e8b78aef3656928497927049951b843a8f9629733b17103398` | 3 | 8 | 0.9993 | 1.54 |

Cả 5 seed cùng fingerprint: True.

## 6. HiPaG

- adamw lr 0.0002, weight decay 0.0001, tối đa 100 epoch, batch 32, early stop patience 15 theo val pr_auc; grad clip 1.0; λ_taint 0.5; ngưỡng 0.5
- Taint predictor: k (top_k) = 8, W (warmup_epochs) = 3, τ_min (tau_floor) = 0.3, pos_weight auto, MLP 128
- Sweep (RQ5, 3 seed): lưới {'model.taint_predictor.top_k': [4, 8, 16], 'model.taint_predictor.warmup_epochs': [3, 5, 8]}, cố định {'tau_floor': 0.3}, chọn theo val f1_macro -> `top_k8_warmup_epochs3` (0.9847 ± 0.0040)
- E_sem: {'esem_hop': 12, 'interproc_depth': 2, 'max_cand': 4096, 'cross_function': True}
- Kiến trúc: {'token_transformer': {'d_embed': 64, 'heads': 4, 'layers': 2}, 'intra_gatv2': {'hidden': 128, 'heads': 2, 'layers': 2}, 'inter_transformer': {'hidden': 128, 'heads': 2, 'layers': 2}, 'dropout': 0.1, 'pool': 'max'}
- Run chính `experiments/runs/rq4_ablation`: seed [0, 1, 2, 3, 4], thiết bị cuda, 8 biến thể

## 7. Dữ liệu (chỉ hash + số đếm)

| Split | n | webshell | benign | sha256(sample_id đã sắp) |
|---|---|---|---|---|
| train | 5312 | 1525 | 3787 | `7819866ed2b385f336a629d865fb10a6056a360f91088b12ca9434dcfb976851` |
| val | 1157 | 328 | 829 | `8698e3d20a1000da20737caa07fbb3d926682e8a72ea56be23e864809bc9f97c` |
| test | 1152 | 328 | 824 | `fe2e451fce310aaa33ca7ac44b8a2149da7e9ed0f39232de2d00fa5b93e80658` |
| holdout | 2306 | 339 | 1967 | `55f816421c662d2ea3f2c48f4218072c1aa912c3ef30b1c82d5a7e9b11a9f3d8` |
| obf | 6912 | 1968 | 4944 | `8c9d6e9fa3dff5718c60740501940c9010a576d8eb1fa2e1a38c87ee258f9eab` |

| File | sha256 |
|---|---|
| `experiments/dataset/splits.csv` | `00c9706de6bf420ec408a38e4b73046ad9ab56ce61fd50dbb7c0b09389c257c4` |
| `experiments/dataset/manifest.csv` | `b167ccb3d83aa3c1d9b160b561674c3956071a0c700c9f9dde2cc7bc80d3c987` |
| `experiments/dataset/split_summary.json` | `8eeba901435639468e66730f7059120c39fbfb87176e8ad948d086294b07c6c8` |
| `experiments/dataset/obfuscation_manifest.csv` | `2330fd993e41a098b84d51a073bd16e9f6f36883e7d3ce6c03028b46d7483e4b` |
| `experiments/dataset/obfuscation_manifest_nodeobf.csv` | `2330fd993e41a098b84d51a073bd16e9f6f36883e7d3ce6c03028b46d7483e4b` |
| `experiments/dataset/benign2_sources.tsv` | `fa482c17b93086ed24f873ea62ceac421ff0777dd9a18c0207cd98b97106078b` |
| `experiments/dataset/clusters.csv` | `aa97760abb7373fbb8eb78c13df274048bbb7cba36292ea8e3e2677094b93e77` |
| `experiments/runs/rq1_codebert/canonical_inputs.jsonl` | `49581f050c2fbbde6f68b94f363cbf1d5e8e588c87cee6b26066c604e6c30415` |

| Nguồn | webshell | benign | ghim phiên bản |
|---|---|---|---|
| adminer | 0 | 108 | commit `38cdecba2a41` (https://github.com/vrana/adminer) |
| c01dsnap | 573 | 0 | `c01dsnap_Webshell_Black.zip` sha256 `ccbf935e202523e6…`; `c01dsnap_Webshell_webshell.zip` sha256 `a7924da81bae4110…` |
| c01dsnap_benign | 0 | 1978 | `c01dsnap_Webshell_White.zip` sha256 `1cd91772f4e4d8a3…` |
| carbon_lang | 0 | 149 | commit `dde1e12f75b7` (https://github.com/briannesbitt/Carbon) |
| country_list | 0 | 40 | commit `bd490a163ae4` (https://github.com/umpirsky/country-list) |
| cycle183 | 1726 | 0 | `cycle183.zip` sha256 `ea9211fcd642b21e…`; repo commit `59ff14ffb05e` |
| dokuwiki | 0 | 431 | commit `ab1349690553` (https://github.com/dokuwiki/dokuwiki) |
| drupal | 0 | 150 | commit `3fb1c69d3692` (https://github.com/drupal/drupal) |
| e107 | 0 | 691 | commit `f0dc448d6501` (https://github.com/e107inc/e107) |
| elfinder | 0 | 15 | commit `6f1da224a5d9` (https://github.com/Studio-42/elFinder) |
| fluxbb | 0 | 48 | commit `5a2f95a34ef4` (https://github.com/fluxbb/fluxbb) |
| johntroony | 89 | 0 | commit `226a15d0684e` (https://github.com/JohnTroony/php-webshells) |
| kcfinder | 0 | 25 | commit `b645d2a81e64` (https://github.com/sunhater/kcfinder) |
| kint | 0 | 54 | commit `a05294926725` (https://github.com/kint-php/kint) |
| laravel | 0 | 150 | commit `3ee9f38b4b84` (https://github.com/laravel/framework) |
| libphonenumber_data | 0 | 200 | commit `75a801c3dbf9` (https://github.com/giggsey/libphonenumber-for-php) |
| mantisbt | 0 | 278 | commit `94a7edb90540` (https://github.com/MantisBT/mantisbt) |
| mpdf_data | 0 | 23 | commit `9928267eb9ff` (https://github.com/mpdf/mpdf) |
| mybb | 0 | 227 | commit `f621eef39c8b` (https://github.com/mybb/mybb) |
| oscommerce2 | 0 | 193 | commit `de0e97d15d43` (https://github.com/osCommerce/oscommerce2) |
| phpmailer_lang | 0 | 1 | commit `ddf8cfdeb968` (https://github.com/PHPMailer/PHPMailer) |
| phpsysinfo | 0 | 62 | commit `b53202030d5d` (https://github.com/phpsysinfo/phpsysinfo) |
| phpvirtualbox | 0 | 10 | commit `e5e4cc779140` (https://github.com/phpvirtualbox/phpvirtualbox) |
| piwigo | 0 | 292 | commit `7547b1bdb00a` (https://github.com/Piwigo/Piwigo) |
| pluck | 0 | 97 | commit `c61a801cf9dc` (https://github.com/pluck-cms/pluck) |
| polyfill_idn | 0 | 5 | commit `533d68cf99c8` (https://github.com/symfony/polyfill-intl-idn) |
| polyfill_normalizer | 0 | 3 | commit `ebd57ccc7edb` (https://github.com/symfony/polyfill-intl-normalizer) |
| serendipity | 0 | 618 | commit `15212b5f275f` (https://github.com/s9y/Serendipity) |
| smarty | 0 | 66 | commit `ed16847b9f0a` (https://github.com/smarty-php/smarty) |
| symfony_di | 0 | 150 | commit `91ff86a0e53c` (https://github.com/symfony/dependency-injection) |
| tennc | 366 | 0 | commit `6b17eae4a0bc` (https://github.com/tennc/webshell) |
| textpattern | 0 | 111 | commit `0105c6df3d00` (https://github.com/textpattern/textpattern) |
| tinyfilemanager | 0 | 1 | commit `41491439a6b2` (https://github.com/prasathmani/tinyfilemanager) |
| tracy_templates | 0 | 11 | commit `d46e9e972563` (https://github.com/nette/tracy) |
| vesta | 0 | 150 | commit `765509cae206` (https://github.com/serghey-rodin/vesta) |
| wordpress | 0 | 399 | commit `1f23e99c724e` (https://github.com/WordPress/WordPress) |
| zencart | 0 | 682 | commit `031b60dc47cd` (https://github.com/zencart/zencart) |

Có trên đĩa nhưng không dùng: data/_repos/mwf_repo (MWF; thay bằng c01dsnap làm holdout); data/dl/nbuser32_PHP-Webshell-Dataset_php_webshell_dataset.jsonl

## 8. Mã và config

- git HEAD `aa127500e0be18da1bdd948e0d99c91a496ea642`; 9 mục chưa commit; code_tree_sha256 `060a0e41ca1d2aa44928caa86502c88d7a56b2c86d2adb2e7e85154cdfd48037` (75 file)
- Các ledger ghi git_commit lúc chạy nhưng working tree khi đó có thay đổi CHƯA commit -> commit không ghim được mã đã chạy. code_tree_sha256 là trạng thái mã HIỆN TẠI (lúc sinh manifest).
- Commit ghi trong ledger: `experiments/runs/rq4_ablation` 3271422097, `experiments/runs/rq4_ablation_nodeobf` 3271422097, `experiments/runs/rq5_taint_hparams` 3271422097, `experiments/runs/rq5_taint_hparams_synthetic` 3271422097

| Config | sha256 |
|---|---|
| `configs/model/hipag_base.yaml` | `f6e83da39b26c1ee17b0f70bf60ed3cbfbb9461212bc389610f200b8b601f5a3` |
| `configs/experiment/rq1_baselines.yaml` | `387030da65de3ecab7a3f9d827090534c8383fb20f1a1dd36b9aed6e5eba7657` |
| `configs/experiment/rq1_codebert.yaml` | `3ffafb58887cc1a530e21c86412d3c607a250553c94c46ce54f959bd1eb3a32d` |
| `configs/experiment/rq1_detection.yaml` | `21b5ad1d512e736b6b00629b14cfeed9f9923d658a931dbef65e0ed2aaf0c522` |
| `configs/experiment/rq2_obfuscation.yaml` | `2dc745b1ac5b6f6635dfe1a2e50215bbfb3d1c6c2c77b87b9fee847e2144ef51` |
| `configs/experiment/rq2_obfuscation_nodeobf.yaml` | `531c8af11bf02033e19086276d5f5490a4dd43ac1f5fc36699d727b516b90e97` |
| `configs/experiment/rq3_crossdataset.yaml` | `2f33079825e949046903a9ec8f3c629aceff108816288a7db2e2ac4557450d66` |
| `configs/experiment/rq4_ablation.yaml` | `1a7e6414ad155de0e7b02da688c219c510ff76180a5e612048b5d70693af9d03` |
| `configs/experiment/rq4_ablation_nodeobf.yaml` | `5473d8f9aa6070b4b6a1df3bec5eeddc4c9a3308ba83aa17fff35dcbc0ff9bf0` |
| `configs/experiment/rq5_taint_hparams.yaml` | `460b1f0c18ba8ffa663bf18093d8c80df74f0fc982b2e88db0bd233f44364984` |
| `configs/experiment/probe_on.yaml` | `577f688b9eb76ccb1d78601aa70b77b8511a9a9cf8706f06dcdadd53d73c5a87` |
| `configs/experiment/probe_off.yaml` | `37c4a2c14f1ab2553a30819152fe8b14559ba330ed4842ee0cb88f2ec00fc424` |
| `configs/dataset/collect.yaml` | `91d3f07d21df1946bb7c1a4c7a1f11d40c5d905e688ca2862d32c5dac2d92179` |
| `configs/dataset/dedup.yaml` | `f4b0b49d802801d91a5d6afacda6e49cda09547a94ed940da95dcba81a1870cb` |
| `configs/dataset/split.yaml` | `89a76b0c8f5a23e21216b1f11477881a2f291220e73b9e060c2bdcc80576a90e` |
| `configs/dataset/build_graphs.yaml` | `2ae8a18ee1e624fe50e7838570167fc650c893662f27b6aa3a073ad219d75ee2` |
| `configs/dataset/build_graphs_nodeobf.yaml` | `a5e184c27f38640a10fdfc2f301f99063e1e65494298b275896f4819b574bc6a` |
| `configs/dataset/obfuscation.yaml` | `7885c8a4547f45ce02051201afaae752a0957edb050d19500161a37f3a46cbea` |
| `configs/dataset/obfuscation_nodeobf.yaml` | `e47ce8cf6a76dcb4d289de979805c88b34b20e8e9006857e245a75b90ea126bb` |
| `composer.lock` | `dacbd3388831cb3fc1d78394d9a535ad11a4801c05dff26770e9fcc9e1e2ace3` |
