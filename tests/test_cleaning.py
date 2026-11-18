from decimal import Decimal as D
from app.pipeline import run
from app.normalize import instant
from app.modules.m3_episodes.rules import episodes, cleaning, bed_board
from app.modules.m4_conflicts.rules import early_admissions

END = instant('2026-11-18T00:00:00+08:00')

def e(id, patient, bed, t, kind='admit', version=1):
    return dict(id=id, patient=patient, bed=bed, ward='一病区',
                time=instant('2026-11-16T' + t + ':00+08:00'),
                type=kind, version=version, _line=int(id) + 1)

def pipeline(text, **params):
    merged = {'clean_minutes': '30'}
    merged.update(params)
    return run(text, merged, persist=False)

DISCHARGE = ("id,patient,bed,ward,time,type,version\n"
             "1,P1,001,W1,2026-11-16T08:00:00+08:00,admit,1\n"
             "2,P1,001,W1,2026-11-16T10:00:00+08:00,discharge,1\n")

def test_provisional_cleaning_window_after_discharge():
    r = pipeline(DISCHARGE)
    w = [x for x in r['cleaning'] if x['bed'] == '001'][0]
    assert w['released_at'] == instant('2026-11-16T10:00:00+08:00').isoformat()
    assert w['cleaned_at'] == instant('2026-11-16T10:30:00+08:00').isoformat()
    assert w['confirmed'] is False and w['state'] == '清洁完成'
    assert '默认清洁 30 分钟' in w['basis']

def test_cleaning_not_counted_in_length_of_stay():
    # 患者临床结算仍到原出院时刻；清洁窗不进分段、不进日历、不进对账
    r = pipeline(DISCHARGE)
    seg = [x for x in r['intervals'] if x['patient'] == 'P1'][0]
    assert seg['end'] == instant('2026-11-16T10:00:00+08:00').isoformat()
    assert all(x['patient'] != 'P1' or x['end'] <= seg['end'] for x in r['intervals'])
    assert all(x['state'] == '通过' for x in r['reconciliation'])

def test_late_clean_report_corrects_window():
    # 晚到的清洁回报纠正临时窗：完成时刻以回报为准
    text = DISCHARGE + "7,C9,001,W1,2026-11-16T11:15:00+08:00,clean,1\n"
    r = pipeline(text)
    w = [x for x in r['cleaning'] if x['bed'] == '001'][0]
    assert w['confirmed'] is True
    assert w['cleaned_at'] == instant('2026-11-16T11:15:00+08:00').isoformat()
    assert w['minutes'] == '75.0' and w['clean_id'] == '7'
    # 临床结算仍停在原出院时刻
    seg = [x for x in r['intervals'] if x['patient'] == 'P1'][0]
    assert seg['end'] == instant('2026-11-16T10:00:00+08:00').isoformat()

def test_retry_same_clean_report_adds_no_window():
    text = (DISCHARGE
            + "7,C9,001,W1,2026-11-16T11:15:00+08:00,clean,1\n"
            + "7,C9,001,W1,2026-11-16T11:15:00+08:00,clean,1\n")
    r = pipeline(text)
    assert len([w for w in r['cleaning'] if w['bed'] == '001']) == 1
    assert sum(q['code'] == 'DUPLICATE' for q in r['quarantine']) == 1
    assert r['input_count'] == len(r['records']) + len(r['quarantine'])

def test_clean_report_version_conflict_quarantined():
    text = (DISCHARGE
            + "7,C9,001,W1,2026-11-16T11:15:00+08:00,clean,1\n"
            + "7,C9,001,W1,2026-11-16T11:30:00+08:00,clean,1\n")
    r = pipeline(text)
    assert all(q['code'] != 'CONFLICT' for q in r['quarantine']) is False
    assert len([w for w in r['cleaning'] if w['bed'] == '001']) == 1

def test_orphan_clean_report_quarantined():
    text = ("id,patient,bed,ward,time,type,version\n"
            "7,C9,003,W1,2026-11-16T11:15:00+08:00,clean,1\n")
    r = pipeline(text)
    assert r['cleaning'] == []
    assert r['quarantine'][0]['code'] == 'CLEAN'

def test_early_admission_keeps_both_segments_and_flags_review():
    text = (DISCHARGE
            + "3,P2,001,W1,2026-11-16T10:20:00+08:00,admit,1\n"
            + "4,P2,001,W1,2026-11-16T12:00:00+08:00,discharge,1\n")
    r = pipeline(text)
    # 双方占床段都保留，没有删除任何一段
    patients = sorted({i['patient'] for i in r['intervals'] if i['bed'] == '001'})
    assert patients == ['P1', 'P2']
    assert all(i['review'] for i in r['intervals'] if i['bed'] == '001')
    early = r['early_admissions']
    assert len(early) == 1 and early[0]['code'] == 'EARLY' and early[0]['state'] == '待复核'
    assert early[0]['minutes'] == '10.0'
    board = [b for b in r['bed_board'] if b['bed'] == '001'][0]
    assert board['state'] == '待复核' and board['review'] is True

def test_admission_after_cleaning_is_available_not_flagged():
    text = (DISCHARGE
            + "3,P2,001,W1,2026-11-16T10:31:00+08:00,admit,1\n"
            + "4,P2,001,W1,2026-11-16T12:00:00+08:00,discharge,1\n")
    r = pipeline(text)
    assert r['early_admissions'] == []
    assert not any(i['review'] for i in r['intervals'])
    board = [b for b in r['bed_board'] if b['bed'] == '001'][0]
    assert board['state'] == '可收治'

def test_transfer_out_releases_source_bed():
    retained, _, intervals = episodes([
        e('1', 'P1', '001', '08:00'), e('2', 'P1', '002', '10:00', 'transfer'),
        e('3', 'P1', '002', '12:00', 'discharge')], END)
    _, _, windows = cleaning([], retained, END, D('30'))
    source = [w for w in windows if w['bed'] == '001']
    target = [w for w in windows if w['bed'] == '002']
    assert len(source) == 1 and source[0]['released_at'] == instant('2026-11-16T10:00:00+08:00')
    assert len(target) == 1
    # 转床临床段先出后入、端点相接，结算不被清洁拉长
    assert [i['end'] for i in intervals if i['bed'] == '001'][0] == instant('2026-11-16T10:00:00+08:00')

def test_cleaning_in_progress_board_state():
    text = ("id,patient,bed,ward,time,type,version\n"
            "1,P1,001,W1,2026-11-17T23:40:00+08:00,admit,1\n"
            "2,P1,001,W1,2026-11-17T23:50:00+08:00,discharge,1\n")
    r = pipeline(text, observation_end='2026-11-18T00:00:00+08:00')
    board = [b for b in r['bed_board'] if b['bed'] == '001'][0]
    assert board['state'] == '清洁中' and board['basis']

def test_bed_board_covers_all_eight_beds_with_basis():
    r = pipeline(DISCHARGE)
    assert len(r['bed_board']) == 8
    assert all(b['basis'] for b in r['bed_board'])
    states = {b['bed']: b['state'] for b in r['bed_board']}
    assert states['001'] == '可收治'
    assert sum(1 for b in r['bed_board'] if b['state'] == '空床') == 7

def test_early_admissions_rule_unit():
    retained, _, intervals = episodes([
        e('1', 'P1', '001', '08:00'), e('2', 'P1', '001', '10:00', 'discharge'),
        e('3', 'P2', '001', '10:20', 'admit'), e('4', 'P2', '001', '12:00', 'discharge')], END)
    _, _, windows = cleaning([], retained, END, D('30'))
    rows = early_admissions(intervals, windows)
    assert len(rows) == 1 and rows[0]['state'] == '待复核'
    assert all(i['review'] for i in intervals)

def test_clean_event_passes_mapping_and_conservation(raw):
    r = run(raw, persist=False)
    assert r['input_count'] == len(r['records']) + len(r['quarantine'])
    assert all(x['state'] == '通过' for x in r['reconciliation'])
    assert len(r['bed_board']) == 8 and len(r['cleaning']) >= 1

def test_beds_export(client):
    reply = client.get('/api/beds.csv')
    assert reply.status_code == 200
    assert '释放依据' in reply.text and '当前状态' in reply.text
    assert reply.text.count('\n') == 9  # 表头 + 8 床

def test_evidence_export_contains_early_flag(client):
    text = (DISCHARGE
            + "3,P2,001,W1,2026-11-16T10:20:00+08:00,admit,1\n"
            + "4,P2,001,W1,2026-11-16T12:00:00+08:00,discharge,1\n")
    r = client.post('/api/runs', json={'text': text}).json
    ev = client.get('/api/evidence.csv?run=' + r['manifest']['run_id']).text
    assert 'EARLY' in ev and '待复核' in ev
