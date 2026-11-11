# Metadata / shortcut probe (RQF-04/05)

Pool train+val+test n=7452 (pos=0.293); RF 300 cây, class_weight=balanced; 5 seed; StratifiedGroupKFold(5) theo cluster_id.

| feature set | eval | AUC | Acc | macro-F1 |
|---|---|---|---|---|
| required | group-CV | 0.993±0.000 | 0.978±0.001 | 0.973±0.001 |
| required | train→test | 0.992±0.000 | 0.984±0.001 | 0.980±0.001 |
| required | train→holdout | 0.928±0.001 | 0.864±0.002 | 0.784±0.003 |
| required | train→obf_L0 | — | 0.961±0.001 | 0.490±0.000 |
| required | train→obf_L1 | — | 0.956±0.003 | 0.489±0.001 |
| required | train→obf_L2 | — | 0.962±0.002 | 0.490±0.000 |
| required | train→obf_L3 | — | 1.000±0.000 | 1.000±0.000 |
| required | train→obf_L4 | — | 0.980±0.002 | 0.495±0.000 |
| required | train→obf_L5 | — | 0.965±0.002 | 0.491±0.000 |
| required_no_sem | group-CV | 0.989±0.000 | 0.961±0.002 | 0.952±0.002 |
| required_no_sem | train→test | 0.987±0.001 | 0.966±0.001 | 0.959±0.001 |
| required_no_sem | train→holdout | 0.908±0.001 | 0.848±0.002 | 0.762±0.002 |
| required_no_sem | train→obf_L0 | — | 0.927±0.002 | 0.481±0.001 |
| required_no_sem | train→obf_L1 | — | 0.935±0.001 | 0.483±0.000 |
| required_no_sem | train→obf_L2 | — | 0.966±0.001 | 0.491±0.000 |
| required_no_sem | train→obf_L3 | — | 1.000±0.000 | 1.000±0.000 |
| required_no_sem | train→obf_L4 | — | 0.936±0.004 | 0.483±0.001 |
| required_no_sem | train→obf_L5 | — | 0.969±0.003 | 0.492±0.001 |
| shallow | group-CV | 1.000±0.000 | 0.997±0.000 | 0.996±0.000 |
| shallow | train→test | 1.000±0.000 | 0.996±0.000 | 0.996±0.000 |
| shallow | train→holdout | 0.980±0.001 | 0.873±0.002 | 0.807±0.002 |
| shallow | train→obf_L0 | — | 0.994±0.000 | 0.498±0.000 |
| shallow | train→obf_L1 | — | 0.998±0.002 | 0.700±0.274 |
| shallow | train→obf_L2 | — | 0.997±0.005 | 0.799±0.275 |
| shallow | train→obf_L3 | — | 1.000±0.000 | 1.000±0.000 |
| shallow | train→obf_L4 | — | 0.996±0.002 | 0.499±0.000 |
| shallow | train→obf_L5 | — | 0.997±0.005 | 0.799±0.275 |
| graphmeta | group-CV | 0.995±0.000 | 0.983±0.001 | 0.980±0.002 |
| graphmeta | train→test | 0.996±0.001 | 0.985±0.001 | 0.982±0.001 |
| graphmeta | train→holdout | 0.946±0.001 | 0.924±0.001 | 0.857±0.002 |
| graphmeta | train→obf_L0 | — | 0.968±0.002 | 0.492±0.000 |
| graphmeta | train→obf_L1 | — | 0.968±0.002 | 0.492±0.000 |
| graphmeta | train→obf_L2 | — | 1.000±0.000 | 1.000±0.000 |
| graphmeta | train→obf_L3 | — | 1.000±0.000 | 1.000±0.000 |
| graphmeta | train→obf_L4 | — | 0.980±0.004 | 0.495±0.001 |
| graphmeta | train→obf_L5 | — | 1.000±0.000 | 1.000±0.000 |
| all | group-CV | 1.000±0.000 | 0.998±0.000 | 0.998±0.000 |
| all | train→test | 1.000±0.000 | 0.999±0.000 | 0.999±0.000 |
| all | train→holdout | 0.982±0.000 | 0.913±0.003 | 0.858±0.003 |
| all | train→obf_L0 | — | 1.000±0.000 | 1.000±0.000 |
| all | train→obf_L1 | — | 1.000±0.000 | 1.000±0.000 |
| all | train→obf_L2 | — | 1.000±0.000 | 1.000±0.000 |
| all | train→obf_L3 | — | 1.000±0.000 | 1.000±0.000 |
| all | train→obf_L4 | — | 1.000±0.000 | 1.000±0.000 |
| all | train→obf_L5 | — | 1.000±0.000 | 1.000±0.000 |

Top importance (fit trên train, trung bình seed):
- **required**: entropy 0.42, log_size 0.1918, has_typed_cand 0.1424, log_n_tokens 0.1027, has_sem_pair 0.0673, n_nodes 0.0502, cand_capped 0.0133, status_ok 0.0079
- **required_no_sem**: entropy 0.4491, log_size 0.249, log_n_tokens 0.1542, n_nodes 0.0897, cand_capped 0.0422, status_ok 0.0098, status_recovered 0.0049, status_fallback 0.0012
- **shallow**: has_close_tag 0.1875, has_namespace 0.1341, entropy 0.1202, frac_comment_lines 0.0949, frac_digit 0.083, has_docblock 0.0687, n_dollar_per_line 0.0506, frac_punct 0.0445
- **graphmeta**: n_role_sink 0.358, n_role_src 0.1593, n_func 0.0978, has_typed_cand 0.0912, log_n_cand_full 0.0465, n_dfg 0.0425, has_sem_pair 0.0362, log_n_stmt_total 0.0277
- **all**: has_close_tag 0.1283, n_role_sink 0.1083, has_namespace 0.094, entropy 0.0919, frac_digit 0.0709, frac_comment_lines 0.0701, has_docblock 0.0576, frac_punct 0.0429

Alert theo bộ (group-CV AUC ≥ 0.9): {'required': True, 'required_no_sem': True, 'shallow': True, 'graphmeta': True, 'all': True}
**CỔNG (bộ required): ALERT = True**
