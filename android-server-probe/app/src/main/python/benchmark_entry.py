"""Request-level A/B benchmark in private fixtures; formal account is read-only."""
import ast
import json
from pathlib import Path
import statistics
import time
import traceback


def old_function(path, name, module):
    ns=dict(module.__dict__)
    node=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
    return ns[name]


def benchmark(files, runtime, sha):
    import server19_portable as portable
    data=files/('request-benchmark-'+str(time.time_ns()));data.mkdir()
    raw=(files/'formal-data/account.json').read_bytes()
    (data/'account.json').write_bytes(raw)
    server,_=portable.configure(data)
    import server19_stage as stage
    import server19_missions as missions
    import server19_avatar_skills as skills
    import server19_protocol as proto
    old_wins=old_function(files/'benchmark-before-missions.py','_confirmed_wins',missions)
    old_main=old_function(files/'benchmark-before-skills.py','sync_skill_point',skills)
    new_wins,new_main=missions._confirmed_wins,skills.sync_skill_point
    fixture=json.loads(raw)
    # Explicit isolated fixture: retain realistic history/population size, reopen
    # story missions only in this copy so a real reward transaction is measured.
    fixture['mission_runtime']['claimed_ids']=[]
    fixture['mission_runtime']['receipts']=[]
    fixture['mission_data']['mission_list']=[r for r in fixture['mission_data']['mission_list'] if r['mission_id'] not in missions.SUPPORTED_MISSION_IDS]
    fixture['main']['scoin']=4500
    results={};evidence={}
    for label,wins,main in [('before',old_wins,old_main),('after',new_wins,new_main)]:
        missions._confirmed_wins,skills.sync_skill_point=wins,main
        timings={name:[] for name in ('KeepAliveNotify','GetMainDataReq','GetMissionRewardReq')}
        for name in timings:
            for repeat in range(3):
                (data/'account.json').write_text(json.dumps(fixture),encoding='utf-8')
                account=stage.copy_account(fixture)
                started=time.perf_counter()
                if label=='before' or name!='KeepAliveNotify':stage.refresh_account(account,data/'account.json')
                response=server.response(name,account,{'mission_id':10001} if name=='GetMissionRewardReq' else {},account_path=data/'account.json')
                assert response[1].get('retcode',0)==0,response
                packets=[response]
                if name=='GetMissionRewardReq':packets+=missions.notification_snapshot(account)
                wire=[proto.encode_frame(n,proto.encode_message(n,v),user_id=account['uid']) for n,v in packets]
                timings[name].append(time.perf_counter()-started)
                evidence[label,name]=wire
                if name=='GetMissionRewardReq':
                    assert account['mission_runtime']['claimed_ids']==[10001]
                    saved=(data/'account.json').read_bytes()
                    duplicate=server.response(name,account,{'mission_id':10001},account_path=data/'account.json')
                    assert duplicate[1]['retcode']==3 and (data/'account.json').read_bytes()==saved
        results[label]={k:dict(seconds=v,median=statistics.median(v)) for k,v in timings.items()}
    missions._confirmed_wins,skills.sync_skill_point=new_wins,new_main
    for name in timings:assert evidence['before',name]==evidence['after',name],name
    assert (files/'formal-data/account.json').read_bytes()==raw
    return dict(status='PASS',formal_unchanged=True,identical_response_frames=True,duplicate_reward_rejected=True,runtime_sha256=sha,measurements=results)


def run(context):
    files=Path(str(context.getFilesDir().getAbsolutePath()))
    try:
        from probe_entry import extract_runtime
        files,runtime,sha=extract_runtime(context)
        report=benchmark(files,runtime,sha)
        (files/'benchmark-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        return json.dumps(report)
    except BaseException:
        (files/'benchmark-error.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
