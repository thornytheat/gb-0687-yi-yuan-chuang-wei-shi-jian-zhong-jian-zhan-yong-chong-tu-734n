from collections import defaultdict
from decimal import Decimal as D
def conflicts(intervals):
    beds=defaultdict(list)
    for item in intervals:beds[item['bed']].append(item)
    result=[]
    for bed,items in sorted(beds.items()):
        ordered=sorted(items,key=lambda x:(x['start'],x['end'],x['patient']))
        for i,left in enumerate(ordered):
            for right in ordered[i+1:]:
                if right['start']>=left['end']:break
                start=max(left['start'],right['start']);end=min(left['end'],right['end'])
                if start<end and left['patient']!=right['patient']:
                    result.append({'bed':bed,'patient':left['patient']+' / '+right['patient'],'start':start,'end':end,'minutes':D(str((end-start).total_seconds()))/60,'state':'双占'})
    return result
def early_admissions(intervals,windows):
    """新患者在清洁结束前入住：双方占床段都保留并标待复核，不删除任何一段。"""
    by_bed=defaultdict(list)
    for item in intervals: by_bed[item['bed']].append(item)
    flagged=set();result=[]
    for window in windows:
        for item in by_bed.get(window['bed'],()):
            if window['released_at']<=item['start']<window['cleaned_at']:
                result.append({'bed':window['bed'],'patient':window['patient']+' / '+item['patient'],
                               'start':item['start'],'end':window['cleaned_at'],
                               'minutes':D(str((window['cleaned_at']-item['start']).total_seconds()))/60,
                               'state':'待复核','code':'EARLY',
                               'basis':window['basis'],'release_id':window['release_id'],'clean_id':window['clean_id']})
                flagged.add((item['patient'],item['bed'],item['start']))
                for prior in by_bed.get(window['bed'],()):
                    if prior['patient']==window['patient'] and prior['end']==window['released_at']:
                        flagged.add((prior['patient'],prior['bed'],prior['start']))
    for item in intervals:
        if (item['patient'],item['bed'],item['start']) in flagged: item['review']=True
    return sorted(result,key=lambda x:(x['start'],x['bed']))
