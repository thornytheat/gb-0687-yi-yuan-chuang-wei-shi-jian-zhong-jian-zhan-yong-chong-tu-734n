from .rules import episodes, cleaning, bed_board, dedup_by_id
from app.normalize import number
def execute(ctx):
    clean_minutes=number(ctx['params']['clean_minutes'])
    # 事件号全局去重（含clean与临床事件撞号），保证行数守恒
    deduped,dedup_bad=dedup_by_id(ctx['records'])
    cleans=[r for r in deduped if r['type']=='clean']
    clinical=[r for r in deduped if r['type']!='clean']
    rows,bad,intervals=episodes(clinical,ctx['observation_end'])
    valid_reports,clean_bad,windows=cleaning(cleans,rows,ctx['observation_end'],clean_minutes)
    bad.extend(dedup_bad);bad.extend(clean_bad);rows.extend(valid_reports)
    rows.sort(key=lambda x:x['_line'])
    ctx['records']=rows;ctx['quarantine'].extend(bad)
    ctx['intervals']=intervals;ctx['cleaning']=windows
    ctx['bed_board']=bed_board(intervals,windows,ctx['observation_end'])
    board=ctx['bed_board']
    ctx['stages'].append({'title':'占床分段','rows':intervals,'metrics':{
        '住院段':len(intervals),'开放段':sum(x['open'] for x in intervals),
        '采信事件':len(rows),'清洁窗':len(windows),
        '可收治床位':sum(x['state']=='可收治' for x in board),
        '清洁中床位':sum(x['state']=='清洁中' for x in board),
        '待复核床位':sum(x['state']=='待复核' for x in board)}})
    return ctx
