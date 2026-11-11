# Metadata / shortcut probe (RQF-04/05)

[đặc trưng trên mã CHUẨN HOÁ] Pool train+val+test n=7621 (pos=0.286); RF 300 cây, class_weight=balanced; 5 seed; StratifiedGroupKFold(5) theo cluster_id.

| feature set | eval | AUC | Acc | macro-F1 |
|---|---|---|---|---|
| required | group-CV | 0.967±0.001 | 0.933±0.001 | 0.917±0.002 |
| required | train→test | 0.946±0.002 | 0.925±0.001 | 0.905±0.002 |
| required | train→holdout | 0.912±0.003 | 0.932±0.001 | 0.851±0.002 |
| required | train→obf_L0 | — | 0.830±0.004 | 0.454±0.001 |
| required | train→obf_L0+testbenign | 0.946±0.002 | 0.925±0.001 | 0.905±0.002 |
| required | train→obf_L1 | — | 0.788±0.002 | 0.441±0.001 |
| required | train→obf_L1+testbenign | 0.935±0.002 | 0.913±0.000 | 0.889±0.001 |
| required | train→obf_L2 | — | 0.541±0.034 | 0.351±0.014 |
| required | train→obf_L2+testbenign | 0.962±0.002 | 0.843±0.010 | 0.779±0.018 |
| required | train→obf_L3 | — | 0.433±0.011 | 0.302±0.005 |
| required | train→obf_L3+testbenign | 0.751±0.010 | 0.812±0.004 | 0.723±0.007 |
| required | train→obf_L4 | — | 0.862±0.003 | 0.463±0.001 |
| required | train→obf_L4+testbenign | 0.965±0.001 | 0.934±0.001 | 0.918±0.001 |
| required | train→obf_L5 | — | 0.537±0.039 | 0.349±0.016 |
| required | train→obf_L5+testbenign | 0.964±0.002 | 0.841±0.012 | 0.777±0.020 |
| required_no_sem | group-CV | 0.947±0.002 | 0.908±0.001 | 0.884±0.002 |
| required_no_sem | train→test | 0.927±0.001 | 0.898±0.002 | 0.866±0.003 |
| required_no_sem | train→holdout | 0.891±0.001 | 0.911±0.001 | 0.793±0.004 |
| required_no_sem | train→obf_L0 | — | 0.725±0.007 | 0.420±0.002 |
| required_no_sem | train→obf_L0+testbenign | 0.927±0.001 | 0.898±0.002 | 0.866±0.003 |
| required_no_sem | train→obf_L1 | — | 0.662±0.009 | 0.398±0.003 |
| required_no_sem | train→obf_L1+testbenign | 0.909±0.001 | 0.880±0.003 | 0.839±0.004 |
| required_no_sem | train→obf_L2 | — | 0.526±0.014 | 0.344±0.006 |
| required_no_sem | train→obf_L2+testbenign | 0.958±0.001 | 0.841±0.004 | 0.775±0.007 |
| required_no_sem | train→obf_L3 | — | 0.450±0.009 | 0.310±0.004 |
| required_no_sem | train→obf_L3+testbenign | 0.697±0.004 | 0.819±0.003 | 0.736±0.005 |
| required_no_sem | train→obf_L4 | — | 0.714±0.007 | 0.417±0.002 |
| required_no_sem | train→obf_L4+testbenign | 0.934±0.001 | 0.895±0.002 | 0.862±0.003 |
| required_no_sem | train→obf_L5 | — | 0.529±0.015 | 0.346±0.006 |
| required_no_sem | train→obf_L5+testbenign | 0.960±0.001 | 0.842±0.005 | 0.776±0.008 |
| shallow | group-CV | 0.995±0.000 | 0.973±0.001 | 0.967±0.001 |
| shallow | train→test | 0.995±0.000 | 0.974±0.002 | 0.968±0.002 |
| shallow | train→holdout | 0.970±0.001 | 0.945±0.001 | 0.891±0.003 |
| shallow | train→obf_L0 | — | 0.946±0.006 | 0.486±0.002 |
| shallow | train→obf_L0+testbenign | 0.995±0.000 | 0.974±0.002 | 0.968±0.002 |
| shallow | train→obf_L1 | — | 0.931±0.003 | 0.482±0.001 |
| shallow | train→obf_L1+testbenign | 0.993±0.000 | 0.970±0.001 | 0.963±0.001 |
| shallow | train→obf_L2 | — | 0.878±0.021 | 0.467±0.006 |
| shallow | train→obf_L2+testbenign | 0.990±0.001 | 0.955±0.006 | 0.943±0.008 |
| shallow | train→obf_L3 | — | 0.433±0.003 | 0.302±0.001 |
| shallow | train→obf_L3+testbenign | 0.857±0.006 | 0.828±0.001 | 0.740±0.002 |
| shallow | train→obf_L4 | — | 0.965±0.003 | 0.491±0.001 |
| shallow | train→obf_L4+testbenign | 0.996±0.000 | 0.980±0.001 | 0.975±0.001 |
| shallow | train→obf_L5 | — | 0.859±0.020 | 0.462±0.006 |
| shallow | train→obf_L5+testbenign | 0.990±0.001 | 0.949±0.006 | 0.936±0.007 |
| graphmeta | group-CV | 0.984±0.001 | 0.947±0.002 | 0.936±0.002 |
| graphmeta | train→test | 0.991±0.001 | 0.951±0.000 | 0.940±0.000 |
| graphmeta | train→holdout | 0.926±0.002 | 0.945±0.001 | 0.881±0.001 |
| graphmeta | train→obf_L0 | — | 0.948±0.003 | 0.487±0.001 |
| graphmeta | train→obf_L0+testbenign | 0.991±0.001 | 0.951±0.000 | 0.940±0.000 |
| graphmeta | train→obf_L1 | — | 0.948±0.003 | 0.487±0.001 |
| graphmeta | train→obf_L1+testbenign | 0.991±0.001 | 0.951±0.000 | 0.940±0.000 |
| graphmeta | train→obf_L2 | — | 1.000±0.000 | 1.000±0.000 |
| graphmeta | train→obf_L2+testbenign | 0.973±0.000 | 0.965±0.001 | 0.959±0.001 |
| graphmeta | train→obf_L3 | — | 1.000±0.000 | 1.000±0.000 |
| graphmeta | train→obf_L3+testbenign | 0.973±0.000 | 0.965±0.001 | 0.959±0.001 |
| graphmeta | train→obf_L4 | — | 0.976±0.001 | 0.494±0.000 |
| graphmeta | train→obf_L4+testbenign | 0.993±0.000 | 0.959±0.001 | 0.951±0.001 |
| graphmeta | train→obf_L5 | — | 1.000±0.000 | 1.000±0.000 |
| graphmeta | train→obf_L5+testbenign | 0.973±0.000 | 0.965±0.001 | 0.959±0.001 |
| all | group-CV | 0.998±0.000 | 0.986±0.001 | 0.982±0.001 |
| all | train→test | 0.999±0.000 | 0.986±0.001 | 0.982±0.002 |
| all | train→holdout | 0.980±0.001 | 0.948±0.003 | 0.894±0.005 |
| all | train→obf_L0 | — | 0.971±0.003 | 0.493±0.001 |
| all | train→obf_L0+testbenign | 0.999±0.000 | 0.986±0.001 | 0.982±0.002 |
| all | train→obf_L1 | — | 0.968±0.004 | 0.492±0.001 |
| all | train→obf_L1+testbenign | 0.999±0.000 | 0.985±0.002 | 0.981±0.002 |
| all | train→obf_L2 | — | 0.699±0.068 | 0.411±0.023 |
| all | train→obf_L2+testbenign | 0.991±0.001 | 0.908±0.019 | 0.875±0.028 |
| all | train→obf_L3 | — | 0.438±0.009 | 0.304±0.005 |
| all | train→obf_L3+testbenign | 0.860±0.007 | 0.834±0.003 | 0.748±0.005 |
| all | train→obf_L4 | — | 0.991±0.001 | 0.498±0.000 |
| all | train→obf_L4+testbenign | 1.000±0.000 | 0.991±0.001 | 0.990±0.001 |
| all | train→obf_L5 | — | 0.705±0.069 | 0.413±0.023 |
| all | train→obf_L5+testbenign | 0.991±0.001 | 0.910±0.019 | 0.878±0.029 |

Top importance (fit trên train, trung bình seed):
- **required**: entropy 0.2401, log_size 0.2359, log_n_tokens 0.1662, has_typed_cand 0.1519, n_nodes 0.1168, has_sem_pair 0.0563, cand_capped 0.0158, status_ok 0.0109
- **required_no_sem**: log_size 0.2923, entropy 0.2729, log_n_tokens 0.2178, n_nodes 0.1599, cand_capped 0.0375, status_ok 0.0121, status_recovered 0.0048, status_fallback 0.0026
- **shallow**: frac_digit 0.2027, frac_punct 0.0995, frac_space 0.0731, entropy 0.0712, n_dollar_per_line 0.0698, log_size 0.0622, crlf 0.0573, max_line_len 0.0449
- **graphmeta**: n_role_sink 0.3531, n_role_src 0.112, has_typed_cand 0.0977, n_includes 0.0819, log_n_cand_full 0.0486, n_func 0.0422, n_dfg 0.0414, n_cfg 0.0371
- **all**: n_role_sink 0.1532, frac_digit 0.136, has_typed_cand 0.0589, frac_punct 0.0571, n_role_src 0.055, frac_space 0.0493, entropy 0.0389, n_dollar_per_line 0.0334

Alert theo bộ (group-CV AUC ≥ 0.9): {'required': True, 'required_no_sem': True, 'shallow': True, 'graphmeta': True, 'all': True}
**CỔNG (bộ required): ALERT = True**
