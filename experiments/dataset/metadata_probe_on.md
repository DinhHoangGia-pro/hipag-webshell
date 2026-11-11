# Metadata / shortcut probe (RQF-04/05)

[đặc trưng trên mã CHUẨN HOÁ] Pool train+val+test n=7621 (pos=0.286); RF 300 cây, class_weight=balanced; 5 seed; StratifiedGroupKFold(5) theo cluster_id.

| feature set | eval | AUC | Acc | macro-F1 |
|---|---|---|---|---|
| required | group-CV | 0.967±0.001 | 0.933±0.001 | 0.917±0.001 |
| required | train→test | 0.944±0.002 | 0.921±0.003 | 0.900±0.004 |
| required | train→holdout | 0.915±0.002 | 0.933±0.002 | 0.852±0.003 |
| required | train→obf_L0 | 0.944±0.002 | 0.921±0.003 | 0.900±0.004 |
| required | train→obf_L1 | 0.911±0.002 | 0.876±0.001 | 0.845±0.001 |
| required | train→obf_L2 | 0.780±0.006 | 0.696±0.010 | 0.671±0.009 |
| required | train→obf_L3 | 0.853±0.002 | 0.824±0.004 | 0.783±0.006 |
| required | train→obf_L4 | 0.933±0.001 | 0.864±0.003 | 0.841±0.003 |
| required | train→obf_L5 | 0.758±0.004 | 0.646±0.008 | 0.630±0.007 |
| required_no_sem | group-CV | 0.946±0.002 | 0.908±0.002 | 0.883±0.002 |
| required_no_sem | train→test | 0.926±0.001 | 0.896±0.002 | 0.864±0.002 |
| required_no_sem | train→holdout | 0.894±0.003 | 0.914±0.001 | 0.800±0.003 |
| required_no_sem | train→obf_L0 | 0.926±0.001 | 0.896±0.002 | 0.864±0.002 |
| required_no_sem | train→obf_L1 | 0.868±0.001 | 0.828±0.003 | 0.785±0.003 |
| required_no_sem | train→obf_L2 | 0.658±0.003 | 0.541±0.012 | 0.527±0.011 |
| required_no_sem | train→obf_L3 | 0.768±0.003 | 0.801±0.004 | 0.733±0.005 |
| required_no_sem | train→obf_L4 | 0.917±0.001 | 0.870±0.001 | 0.834±0.002 |
| required_no_sem | train→obf_L5 | 0.655±0.004 | 0.542±0.010 | 0.529±0.008 |
| shallow | group-CV | 0.995±0.000 | 0.973±0.001 | 0.967±0.001 |
| shallow | train→test | 0.995±0.000 | 0.974±0.002 | 0.968±0.002 |
| shallow | train→holdout | 0.970±0.001 | 0.945±0.001 | 0.891±0.003 |
| shallow | train→obf_L0 | 0.995±0.000 | 0.974±0.002 | 0.968±0.002 |
| shallow | train→obf_L1 | 0.968±0.001 | 0.782±0.005 | 0.771±0.005 |
| shallow | train→obf_L2 | 0.652±0.002 | 0.361±0.020 | 0.348±0.027 |
| shallow | train→obf_L3 | 0.743±0.002 | 0.804±0.001 | 0.716±0.002 |
| shallow | train→obf_L4 | 0.994±0.000 | 0.972±0.001 | 0.966±0.001 |
| shallow | train→obf_L5 | 0.649±0.002 | 0.355±0.022 | 0.342±0.029 |
| graphmeta | group-CV | 0.987±0.000 | 0.962±0.001 | 0.954±0.001 |
| graphmeta | train→test | 0.994±0.000 | 0.973±0.001 | 0.967±0.002 |
| graphmeta | train→holdout | 0.929±0.003 | 0.947±0.001 | 0.884±0.003 |
| graphmeta | train→obf_L0 | 0.994±0.000 | 0.973±0.001 | 0.967±0.002 |
| graphmeta | train→obf_L1 | 0.990±0.000 | 0.962±0.001 | 0.953±0.002 |
| graphmeta | train→obf_L2 | 0.912±0.002 | 0.749±0.004 | 0.738±0.004 |
| graphmeta | train→obf_L3 | 0.912±0.002 | 0.749±0.004 | 0.738±0.004 |
| graphmeta | train→obf_L4 | 0.917±0.001 | 0.858±0.002 | 0.843±0.002 |
| graphmeta | train→obf_L5 | 0.847±0.004 | 0.667±0.005 | 0.663±0.005 |
| all | group-CV | 0.998±0.000 | 0.986±0.001 | 0.983±0.001 |
| all | train→test | 0.999±0.000 | 0.986±0.001 | 0.982±0.001 |
| all | train→holdout | 0.979±0.001 | 0.950±0.004 | 0.899±0.006 |
| all | train→obf_L0 | 0.999±0.000 | 0.986±0.001 | 0.982±0.001 |
| all | train→obf_L1 | 0.996±0.000 | 0.927±0.002 | 0.916±0.002 |
| all | train→obf_L2 | 0.871±0.010 | 0.744±0.031 | 0.726±0.026 |
| all | train→obf_L3 | 0.934±0.004 | 0.863±0.007 | 0.814±0.012 |
| all | train→obf_L4 | 0.997±0.000 | 0.952±0.002 | 0.944±0.002 |
| all | train→obf_L5 | 0.863±0.006 | 0.611±0.033 | 0.608±0.030 |

Top importance (fit trên train, trung bình seed):
- **required**: log_size 0.2271, entropy 0.227, has_typed_cand 0.1648, log_n_tokens 0.161, n_nodes 0.1152, has_sem_pair 0.067, cand_capped 0.0201, status_ok 0.0111
- **required_no_sem**: log_size 0.2891, entropy 0.2699, log_n_tokens 0.212, n_nodes 0.1641, cand_capped 0.045, status_ok 0.0125, status_recovered 0.0047, status_fallback 0.0028
- **shallow**: frac_digit 0.2027, frac_punct 0.0995, frac_space 0.0731, entropy 0.0712, n_dollar_per_line 0.0698, log_size 0.0622, crlf 0.0573, max_line_len 0.0449
- **graphmeta**: n_role_sink 0.3386, n_role_src 0.1161, has_typed_cand 0.1051, n_includes 0.0811, log_n_cand_full 0.0502, n_dfg 0.0437, n_func 0.0404, n_cfg 0.037
- **all**: n_role_sink 0.1562, frac_digit 0.1316, has_typed_cand 0.0637, n_role_src 0.062, frac_punct 0.0561, frac_space 0.0466, n_dollar_per_line 0.0368, entropy 0.0363

Alert theo bộ (group-CV AUC ≥ 0.9): {'required': True, 'required_no_sem': True, 'shallow': True, 'graphmeta': True, 'all': True}
**CỔNG (bộ required): ALERT = True**
