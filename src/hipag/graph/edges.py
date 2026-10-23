"""Bảy loại cạnh của đồ thị phân cấp đa quan hệ."""
EDGE_TYPES = ["E_seq", "E_skip", "E_cfg", "E_dfg", "E_sem", "E_call", "E_include"]
# E_seq/E_skip: tầng statement (kế thừa LOGWAT)
# E_cfg/E_dfg/E_sem: tầng function (E_sem = source->sink HỌC ĐƯỢC)
# E_call/E_include: tầng file
