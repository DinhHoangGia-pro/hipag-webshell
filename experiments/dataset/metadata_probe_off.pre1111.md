# Metadata / shortcut probe (RQF-04/05)

[đặc trưng trên mã CHUẨN HOÁ] Pool train+val+test n=7621 (pos=0.286); RF 300 cây, class_weight=balanced; 5 seed; StratifiedGroupKFold(5) theo cluster_id.

| feature set | eval | AUC | Acc | macro-F1 |
|---|---|---|---|---|
| required | group-CV | 0.967±0.001 | 0.933±0.001 | 0.917±0.002 |
| required | train→test | 0.946±0.002 | 0.925±0.001 | 0.905±0.002 |
| required | train→holdout | 0.912±0.003 | 0.932±0.001 | 0.851±0.002 |
| required | train→obf_L0 | 0.946±0.002 | 0.925±0.001 | 0.905±0.002 |
| required | train→obf_L1 | 0.906±0.001 | 0.863±0.002 | 0.832±0.002 |
| required | train→obf_L2 | 0.647±0.005 | 0.660±0.034 | 0.612±0.024 |
| required | train→obf_L3 | 0.734±0.003 | 0.776±0.004 | 0.689±0.006 |
| required | train→obf_L4 | 0.938±0.001 | 0.870±0.003 | 0.848±0.002 |
| required | train→obf_L5 | 0.651±0.004 | 0.654±0.029 | 0.606±0.020 |
| required_no_sem | group-CV | 0.947±0.002 | 0.908±0.001 | 0.884±0.002 |
| required_no_sem | train→test | 0.927±0.001 | 0.898±0.002 | 0.866±0.003 |
| required_no_sem | train→holdout | 0.891±0.001 | 0.911±0.001 | 0.793±0.004 |
| required_no_sem | train→obf_L0 | 0.927±0.001 | 0.898±0.002 | 0.866±0.003 |
| required_no_sem | train→obf_L1 | 0.860±0.003 | 0.816±0.004 | 0.774±0.005 |
| required_no_sem | train→obf_L2 | 0.652±0.003 | 0.671±0.015 | 0.619±0.011 |
| required_no_sem | train→obf_L3 | 0.733±0.003 | 0.777±0.002 | 0.694±0.004 |
| required_no_sem | train→obf_L4 | 0.922±0.001 | 0.882±0.003 | 0.847±0.004 |
| required_no_sem | train→obf_L5 | 0.656±0.004 | 0.668±0.012 | 0.617±0.009 |
| shallow | group-CV | 0.995±0.000 | 0.973±0.001 | 0.967±0.001 |
| shallow | train→test | 0.995±0.000 | 0.974±0.002 | 0.968±0.002 |
| shallow | train→holdout | 0.970±0.001 | 0.945±0.001 | 0.891±0.003 |
| shallow | train→obf_L0 | 0.995±0.000 | 0.974±0.002 | 0.968±0.002 |
| shallow | train→obf_L1 | 0.968±0.001 | 0.782±0.005 | 0.771±0.005 |
| shallow | train→obf_L2 | 0.652±0.002 | 0.361±0.020 | 0.348±0.027 |
| shallow | train→obf_L3 | 0.743±0.002 | 0.804±0.001 | 0.716±0.002 |
| shallow | train→obf_L4 | 0.994±0.000 | 0.972±0.001 | 0.966±0.001 |
| shallow | train→obf_L5 | 0.649±0.002 | 0.355±0.022 | 0.342±0.029 |
| graphmeta | group-CV | 0.984±0.001 | 0.947±0.002 | 0.936±0.002 |
| graphmeta | train→test | 0.991±0.001 | 0.951±0.000 | 0.940±0.000 |
| graphmeta | train→holdout | 0.926±0.002 | 0.945±0.001 | 0.881±0.001 |
| graphmeta | train→obf_L0 | 0.991±0.001 | 0.951±0.000 | 0.940±0.000 |
| graphmeta | train→obf_L1 | 0.962±0.000 | 0.950±0.001 | 0.940±0.002 |
| graphmeta | train→obf_L2 | 0.500±0.000 | 0.285±0.000 | 0.222±0.000 |
| graphmeta | train→obf_L3 | 0.500±0.000 | 0.285±0.000 | 0.222±0.000 |
| graphmeta | train→obf_L4 | 0.941±0.001 | 0.859±0.002 | 0.844±0.002 |
| graphmeta | train→obf_L5 | 0.500±0.000 | 0.285±0.000 | 0.222±0.000 |
| all | group-CV | 0.998±0.000 | 0.986±0.001 | 0.982±0.001 |
| all | train→test | 0.999±0.000 | 0.986±0.001 | 0.982±0.002 |
| all | train→holdout | 0.980±0.001 | 0.948±0.003 | 0.894±0.005 |
| all | train→obf_L0 | 0.999±0.000 | 0.986±0.001 | 0.982±0.002 |
| all | train→obf_L1 | 0.975±0.001 | 0.917±0.002 | 0.905±0.002 |
| all | train→obf_L2 | 0.667±0.003 | 0.522±0.064 | 0.512±0.055 |
| all | train→obf_L3 | 0.738±0.004 | 0.806±0.002 | 0.719±0.004 |
| all | train→obf_L4 | 0.997±0.000 | 0.961±0.002 | 0.953±0.003 |
| all | train→obf_L5 | 0.667±0.003 | 0.523±0.059 | 0.513±0.050 |

Top importance (fit trên train, trung bình seed):
- **required**: entropy 0.2401, log_size 0.2359, log_n_tokens 0.1662, has_typed_cand 0.1519, n_nodes 0.1168, has_sem_pair 0.0563, cand_capped 0.0158, status_ok 0.0109
- **required_no_sem**: log_size 0.2923, entropy 0.2729, log_n_tokens 0.2178, n_nodes 0.1599, cand_capped 0.0375, status_ok 0.0121, status_recovered 0.0048, status_fallback 0.0026
- **shallow**: frac_digit 0.2027, frac_punct 0.0995, frac_space 0.0731, entropy 0.0712, n_dollar_per_line 0.0698, log_size 0.0622, crlf 0.0573, max_line_len 0.0449
- **graphmeta**: n_role_sink 0.3531, n_role_src 0.112, has_typed_cand 0.0977, n_includes 0.0819, log_n_cand_full 0.0486, n_func 0.0422, n_dfg 0.0414, n_cfg 0.0371
- **all**: n_role_sink 0.1532, frac_digit 0.136, has_typed_cand 0.0589, frac_punct 0.0571, n_role_src 0.055, frac_space 0.0493, entropy 0.0389, n_dollar_per_line 0.0334

Alert theo bộ (group-CV AUC ≥ 0.9): {'required': True, 'required_no_sem': True, 'shallow': True, 'graphmeta': True, 'all': True}
**CỔNG (bộ required): ALERT = True**
