from pathlib import Path
TITLE = '医院床位事件重建与占用冲突'
SHORT = 'bed-chronicle'
STAGES = ['receive', 'mapping', 'episodes', 'conflicts', 'calendar', 'reconcile', 'replay']
MODULES = ['事件接收', '病区映射', '住院分段', '转床裁决', '占床日历', '病区对账', '补传重算']
COLUMNS = {'id': '事件号', 'patient': '患者号', 'bed': '床号', 'ward': '病区', 'time': '事件时刻 UTC', 'type': '事件', 'start': '开始 UTC', 'end': '结束 UTC', 'released_at': '释放时刻 UTC', 'cleaned_at': '清洁完成 UTC', 'minutes': '占床 min', 'date': '日期 +08', 'state': '状态', 'line': '行号', 'code': '原因码', 'reason': '原因', 'count': '数量', 'open': '开放段', 'version': '版本', 'source': '释放依据', 'review': '复核', 'basis': '释放依据'}
DEFAULTS = {'observation_end': '2026-11-18T00:00:00+08:00', 'day_offset': '8', 'late_minutes': '30', 'clean_minutes': '30'}
RULE_VERSION = "2026.11.18-v2"
SAMPLES = Path(__file__).resolve().parent.parent / "sample_data"
MAX_BYTES = 4 * 1024 * 1024
