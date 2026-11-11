# Metadata / shortcut probe (RQF-04/05)

Pool train+val+test n=7627 (pos=0.286); RF 300 cây, class_weight=balanced; 5 seed; StratifiedGroupKFold(5) theo cluster_id.

| feature set | eval | AUC | Acc | macro-F1 |
|---|---|---|---|---|
| required | group-CV | 0.969±0.001 | 0.931±0.001 | 0.915±0.001 |
| required | train→test | 0.975±0.001 | 0.928±0.002 | 0.910±0.003 |
| required | train→holdout | 0.935±0.002 | 0.937±0.001 | 0.864±0.002 |
| required | train→obf_L0 | — | 0.855±0.006 | 0.461±0.002 |
| required | train→obf_L1 | — | 0.780±0.005 | 0.438±0.001 |
| required | train→obf_L2 | — | 0.622±0.032 | 0.383±0.012 |
| required | train→obf_L3 | — | 0.357±0.006 | 0.263±0.003 |
| required | train→obf_L4 | — | 0.898±0.003 | 0.473±0.001 |
| required | train→obf_L5 | — | 0.626±0.030 | 0.385±0.011 |
| required_no_sem | group-CV | 0.947±0.002 | 0.906±0.001 | 0.881±0.002 |
| required_no_sem | train→test | 0.956±0.000 | 0.918±0.003 | 0.897±0.004 |
| required_no_sem | train→holdout | 0.918±0.002 | 0.918±0.001 | 0.814±0.001 |
| required_no_sem | train→obf_L0 | — | 0.819±0.006 | 0.450±0.002 |
| required_no_sem | train→obf_L1 | — | 0.713±0.006 | 0.416±0.002 |
| required_no_sem | train→obf_L2 | — | 0.614±0.038 | 0.380±0.015 |
| required_no_sem | train→obf_L3 | — | 0.386±0.015 | 0.278±0.008 |
| required_no_sem | train→obf_L4 | — | 0.827±0.005 | 0.453±0.002 |
| required_no_sem | train→obf_L5 | — | 0.610±0.029 | 0.379±0.011 |
| shallow | group-CV | 0.997±0.000 | 0.979±0.001 | 0.975±0.001 |
| shallow | train→test | 0.997±0.000 | 0.981±0.001 | 0.977±0.001 |
| shallow | train→holdout | 0.990±0.001 | 0.974±0.001 | 0.948±0.002 |
| shallow | train→obf_L0 | — | 0.960±0.004 | 0.490±0.001 |
| shallow | train→obf_L1 | — | 0.996±0.002 | 0.499±0.000 |
| shallow | train→obf_L2 | — | 0.306±0.072 | 0.233±0.041 |
| shallow | train→obf_L3 | — | 0.105±0.010 | 0.095±0.008 |
| shallow | train→obf_L4 | — | 0.965±0.005 | 0.491±0.001 |
| shallow | train→obf_L5 | — | 0.341±0.045 | 0.254±0.025 |
| graphmeta | group-CV | 0.985±0.000 | 0.948±0.001 | 0.937±0.002 |
| graphmeta | train→test | 0.986±0.000 | 0.950±0.001 | 0.940±0.001 |
| graphmeta | train→holdout | 0.939±0.002 | 0.945±0.002 | 0.882±0.003 |
| graphmeta | train→obf_L0 | — | 0.946±0.002 | 0.486±0.000 |
| graphmeta | train→obf_L1 | — | 0.946±0.002 | 0.486±0.000 |
| graphmeta | train→obf_L2 | — | 1.000±0.000 | 1.000±0.000 |
| graphmeta | train→obf_L3 | — | 1.000±0.000 | 1.000±0.000 |
| graphmeta | train→obf_L4 | — | 0.973±0.000 | 0.493±0.000 |
| graphmeta | train→obf_L5 | — | 1.000±0.000 | 1.000±0.000 |
| all | group-CV | 0.999±0.000 | 0.990±0.001 | 0.987±0.001 |
| all | train→test | 1.000±0.000 | 0.994±0.001 | 0.993±0.001 |
| all | train→holdout | 0.993±0.001 | 0.968±0.000 | 0.933±0.001 |
| all | train→obf_L0 | — | 0.994±0.000 | 0.498±0.000 |
| all | train→obf_L1 | — | 0.997±0.000 | 0.499±0.000 |
| all | train→obf_L2 | — | 0.001±0.001 | 0.001±0.001 |
| all | train→obf_L3 | — | 0.005±0.011 | 0.005±0.011 |
| all | train→obf_L4 | — | 0.997±0.000 | 0.499±0.000 |
| all | train→obf_L5 | — | 0.001±0.001 | 0.001±0.001 |

Top importance (fit trên train, trung bình seed):
- **required**: log_size 0.2394, entropy 0.2363, log_n_tokens 0.1638, has_typed_cand 0.1513, n_nodes 0.1153, has_sem_pair 0.0644, cand_capped 0.0158, status_ok 0.0084
- **required_no_sem**: log_size 0.2956, entropy 0.2811, log_n_tokens 0.2106, n_nodes 0.159, cand_capped 0.0377, status_ok 0.01, status_recovered 0.004, status_fallback 0.002
- **shallow**: has_close_tag 0.2108, frac_digit 0.1359, frac_comment_lines 0.0935, has_docblock 0.0637, frac_punct 0.0577, n_dollar_per_line 0.0564, frac_upper 0.0375, crlf 0.0364
- **graphmeta**: n_role_sink 0.3313, n_role_src 0.1174, has_typed_cand 0.1006, n_includes 0.0757, n_func 0.0509, log_n_cand_full 0.0489, n_dfg 0.0471, log_n_stmt_total 0.0459
- **all**: has_close_tag 0.1425, n_role_sink 0.116, frac_digit 0.0964, frac_comment_lines 0.0645, has_docblock 0.0474, has_typed_cand 0.0451, n_role_src 0.0411, frac_punct 0.04

Alert theo bộ (group-CV AUC ≥ 0.9): {'required': True, 'required_no_sem': True, 'shallow': True, 'graphmeta': True, 'all': True}
**CỔNG (bộ required): ALERT = True**
