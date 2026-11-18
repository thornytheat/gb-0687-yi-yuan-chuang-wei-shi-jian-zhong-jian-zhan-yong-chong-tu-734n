from .rules import conflicts, early_admissions
def execute(ctx):
    rows=conflicts(ctx['intervals'])
    early=early_admissions(ctx['intervals'],ctx['cleaning'])
    ctx['conflicts']=rows;ctx['early_admissions']=early
    ctx['stages'].append({'title':'双占裁决','rows':rows,'metrics':{
        '冲突段':len(rows),'涉床':len({x['bed'] for x in rows}),
        '双占 min':str(sum((x['minutes'] for x in rows),0)),
        '清洁前入住待复核':len(early)}})
    return ctx
