"""Bảy loại cạnh của đồ thị phân cấp đa quan hệ + tên edge-type trong PyG HeteroData.

E_seq/E_skip : tầng statement (kế thừa LOGWAT)
E_cfg/E_dfg/E_sem : tầng function (E_sem = source->sink HỌC ĐƯỢC, sinh lúc forward)
E_call/E_include  : tầng file
"""
EDGE_TYPES = ["E_seq", "E_skip", "E_cfg", "E_dfg", "E_sem", "E_call", "E_include"]

STMT, FUNC = "stmt", "func"

# Ánh xạ tên trong paper -> edge type (src, rel, dst) của HeteroData
PYG_EDGE = {
    "E_seq": (STMT, "seq", STMT),
    "E_skip": (STMT, "skip", STMT),
    "E_cfg": (STMT, "cfg", STMT),
    "E_dfg": (STMT, "dfg", STMT),
    "E_sem": (STMT, "sem", STMT),        # KHÔNG lưu trên đĩa: model sinh từ CAND
    "E_call": (FUNC, "call", FUNC),
    "E_include": (FUNC, "include", FUNC),
}

# Cạnh phụ trợ lưu trên đĩa
CAND = (STMT, "cand", STMT)         # cặp ứng viên E_sem (cửa sổ CFG/DFG) — predictor chấm điểm
SEM_POS = (STMT, "sem_pos", STMT)   # giám sát yếu: source->sink tới được
SEM_NEG = (STMT, "sem_neg", STMT)   # mẫu âm
IN_FUNC = (STMT, "in", FUNC)        # statement thuộc function (pool tier2 -> tier3)

# Cạnh trong-hàm đưa vào tier-2 (thứ tự = vị trí one-hot trong edge_attr)
INTRA_TYPES = ["E_seq", "E_skip", "E_cfg", "E_dfg", "E_sem"]
INTER_TYPES = ["E_call", "E_include"]
STORED_EDGE_TYPES = [PYG_EDGE[k] for k in EDGE_TYPES if k != "E_sem"] + [CAND, SEM_POS, SEM_NEG, IN_FUNC]
