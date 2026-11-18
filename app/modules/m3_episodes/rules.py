from collections import defaultdict
from datetime import timedelta
from decimal import Decimal as D
from app.reasons import rejected
from app.modules.m2_mapping.rules import BEDS

def dedup_by_id(rows, conflict_detail='同版事件矛盾', duplicate_detail='重复或旧版事件'):
    # 全局按事件号去重：最高version采信，同版相互矛盾全部隔离，重复/旧版单列
    keys=defaultdict(list)
    for row in rows: keys[row['id']].append(row)
    chosen=[];bad=[]
    for key,group in sorted(keys.items()):
        version=max(x['version'] for x in group);latest=[x for x in group if x['version']==version]
        sig=lambda x:(x['patient'],x['bed'],x['ward'],x['time'],x['type'])
        if len({sig(x) for x in latest})>1:
            bad.extend(rejected(x,'CONFLICT',conflict_detail) for x in group);continue
        pick=min(latest,key=lambda x:x['_line']);chosen.append(pick)
        bad.extend(rejected(x,'DUPLICATE',duplicate_detail) for x in group if x is not pick)
    return chosen,bad

def episodes(rows,end):
    groups=defaultdict(list);bad=[];retained=[];intervals=[]
    chosen,dedup_bad=dedup_by_id(rows);bad.extend(dedup_bad)
    for row in chosen: groups[row['patient']].append(row)
    for patient,events in sorted(groups.items()):
        active=None
        for row in sorted(events,key=lambda x:(x['time'],{'discharge':0,'transfer':1,'admit':2}[x['type']],x['id'])):
            action=row['type']
            if action=='admit':
                if active is not None:bad.append(rejected(row,'STATE','已有占床段'));continue
                active=row
            else:
                if active is None:bad.append(rejected(row,'ORPHAN','没有入院事件'));continue
                if action=='discharge' and row['bed']!=active['bed']:bad.append(rejected(row,'STATE','出院床号不符'));continue
                if action=='transfer': row={**row,'from_bed':active['bed'],'from_ward':active['ward']}
                if row['time']>active['time']:
                    intervals.append({'patient':patient,'bed':active['bed'],'ward':active['ward'],'start':active['time'],'end':row['time'],'open':False,'source':active['id'],'review':False})
                active=row if action=='transfer' else None
            retained.append(row)
        if active and end>active['time']:intervals.append({'patient':patient,'bed':active['bed'],'ward':active['ward'],'start':active['time'],'end':end,'open':True,'source':active['id'],'review':False})
    return retained,bad,intervals

def _dedup_reports(cleans):
    return dedup_by_id(cleans,'同版清洁回报矛盾','重复或旧版清洁回报')

def cleaning(cleans,retained,end,clean_minutes):
    """构造床位清洁窗。出院/转出即释放进入清洁；clean回报确认完成，
    迟到的回报可纠正临时清洁窗；无回报时按clean_minutes给临时窗。"""
    reports,bad=_dedup_reports(cleans)
    releases=[]
    for row in retained:
        if row['type']=='discharge':
            releases.append({'bed':row['bed'],'ward':row['ward'],'patient':row['patient'],
                             'released_at':row['time'],'release_id':row['id']})
        elif row['type']=='transfer':
            # 转床事件床号为目标床，释放的是来源床
            releases.append({'bed':row.get('from_bed',row['bed']),'ward':row.get('from_ward',row['ward']),
                             'patient':row['patient'],'released_at':row['time'],'release_id':row['id']})
    by_bed=defaultdict(list)
    for rel in releases: by_bed[rel['bed']].append(rel)
    for items in by_bed.values(): items.sort(key=lambda r:r['released_at'])
    matched=set()
    confirmed={}
    valid=[]
    for row in sorted(reports,key=lambda x:(x['time'],x['_line'])):
        candidates=[r for r in by_bed.get(row['bed'],())
                    if r['released_at']<=row['time'] and id(r) not in matched]
        if not candidates:
            bad.append(rejected(row,'CLEAN','清洁回报缺少对应的出院或转出，或该释放已回报过'));continue
        rel=candidates[-1];matched.add(id(rel))
        confirmed[id(rel)]=row;valid.append(row)
    windows=[]
    provisional_basis=f"默认清洁 {clean_minutes} 分钟（无清洁回报）"
    for rel in sorted(releases,key=lambda r:(r['released_at'],r['bed'])):
        report=confirmed.get(id(rel))
        if report is not None:
            cleaned_at=report['time']
            window={'bed':rel['bed'],'ward':rel['ward'],'patient':rel['patient'],
                    'released_at':rel['released_at'],'release_id':rel['release_id'],
                    'cleaned_at':cleaned_at,'clean_id':report['id'],'confirmed':True,
                    'basis':f"清洁回报 {report['id']} @ 行{report['_line']}"}
            window['minutes']=D(str((cleaned_at-rel['released_at']).total_seconds()))/60
        else:
            cleaned_at=rel['released_at']+timedelta(minutes=float(clean_minutes))
            window={'bed':rel['bed'],'ward':rel['ward'],'patient':rel['patient'],
                    'released_at':rel['released_at'],'release_id':rel['release_id'],
                    'cleaned_at':cleaned_at,'clean_id':'','confirmed':False,'basis':provisional_basis,
                    'minutes':clean_minutes}
        window['state']='清洁完成' if window['cleaned_at']<=end else '清洁中'
        windows.append(window)
    return valid,bad,windows

def bed_board(intervals,windows,end):
    """观测终点时刻的床位看板：可收治/清洁中/占用中/待复核/空床，附释放依据。"""
    board=[]
    for bed in sorted(BEDS):
        bw=sorted((w for w in windows if w['bed']==bed),key=lambda w:w['released_at'])
        bi=sorted((i for i in intervals if i['bed']==bed),key=lambda i:i['start'])
        latest=bw[-1] if bw else None
        state='空床';basis='目录空床';released_at='';cleaned_at=''
        early_window=next((w for w in bw
                           if any(w['released_at']<=i['start']<w['cleaned_at'] for i in bi)),None)
        if early_window is not None:
            incoming=next(i for i in bi if early_window['released_at']<=i['start']<early_window['cleaned_at'])
            state='待复核';basis=f"清洁结束前入住 {incoming['patient']}；{early_window['basis']}"
            latest=early_window
        elif latest is not None:
            released_at=latest['released_at'];cleaned_at=latest['cleaned_at']
            after=next((i for i in bi if i['start']>=latest['cleaned_at']),None)
            if after is not None:
                state='占用中';basis=f"清洁完成后收治 {after['patient']}；{latest['basis']}"
            elif latest['cleaned_at']<=end:
                state='可收治';basis=latest['basis']
            else:
                state='清洁中';basis=latest['basis']
        elif bi:
            last=bi[-1];state='占用中';basis=f"在院收治 {last['patient']}（开始 {last['start']}）"
        if latest is not None and not released_at:
            released_at=latest['released_at'];cleaned_at=latest['cleaned_at']
        board.append({'bed':bed,'ward':BEDS[bed],'state':state,
                      'released_at':released_at,'cleaned_at':cleaned_at,
                      'basis':basis,'review':state=='待复核'})
    return board
