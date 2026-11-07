"""Early cumulative recharge rewards using deployed source reward rows.

Only six historically cross-checked thresholds are admitted. Later tiers
remain missing rather than receiving invented or modern substitute rewards.
"""
from copy import deepcopy
from pathlib import Path
import time
import server19_stage as stage
import server19_missions as missions

TIERS = ((1,10,2001),(2,300,2002),(3,500,2003),
         (4,1000,2004),(5,2000,2005),(6,5000,2006))
EXPECTED = {2001:[(20171,1,1)],2002:[(4001,0,10),(4005,0,10),(6011,0,10)],
            2003:[(20184,1,1)],2004:[(4006,0,10),(4010,0,10),(6012,0,10)],
            2005:[(20197,1,1)],2006:[(4003,0,10),(4011,0,10),(6013,0,10)]}


def catalog():
    rows=stage._table('rewarddata',field='RewardID',identities=EXPECTED)
    result={}
    for level,threshold,identity in TIERS:
        matches=[r for r in rows if r['RewardID']==identity]
        if len(matches)!=1:raise ValueError('Missing source welfare reward')
        row=matches[0]
        items=[{'id':row[f'RewardItem{i}ID'],'level':row[f'RewardItem{i}Level'],
                'num':row[f'RewardItem{i}Num']} for i in range(1,6) if row[f'RewardItem{i}ID']]
        if [(i['id'],i['level'],i['num']) for i in items]!=EXPECTED[identity]:
            raise ValueError('Changed source welfare reward')
        if any(row[k] for k in ('RewardExp','RewardSCoin','RewardHCoin','RewardStamina',
                                'RewardSkillPoint','RewardFriendPoint','RewardDutyPoint')):
            raise ValueError('Unexpected welfare currency')
        result[level]={'threshold':threshold,'reward_id':identity,'reward':{
            'exp':0,'scoin':0,'hcoin':0,'stamina':0,'skill_point':0,
            'friends_point':0,'duty_point':0,'item_list':items}}
    return result


def total(account):
    import server19_recharge as recharge
    orders=account.get('local_recharge_runtime',{}).get('orders',{})
    if not isinstance(orders,dict):raise ValueError('Invalid recharge receipts')
    value=0
    for receipt in orders.values():
        pack=recharge.BY_NAME.get(receipt.get('product'))
        if pack is None:raise ValueError('Unrecognized recharge receipt')
        value+=pack['pay_hcoin']
    return stage._u32(value,'cumulative purchased hcoin')


def runtime(account):
    r=account.setdefault('local_recharge_welfare',{'schema':1,'receipts':{}})
    if r.get('schema')!=1 or not isinstance(r.get('receipts'),dict):
        raise ValueError('Invalid welfare state')
    return r


def snapshot(account):
    count=total(account);claimed=account.get('local_recharge_welfare',{}).get('receipts',{})
    return 'GetVipRewardDataRsp',{'retcode':0,'total_pay_hcoin':count,'vip_reward_list':[
        {'vip_level':level,'pay_hcoin':row['threshold'],'reward_id':row['reward_id'],
         'reward_batch':0,'status':3 if str(level) in claimed else
         2 if count>=row['threshold'] else 1} for level,row in catalog().items()]}


def response(name,account,values=None,*,account_path=None):
    if name=='GetVipRewardDataReq':return snapshot(account)
    if name!='GetVipRewardReq':return None
    levels=(values or {}).get('vip_level_list',[])
    if not isinstance(levels,list) or not levels or len(levels)>len(TIERS) or \
            any(type(n) is not int for n in levels) or len(set(levels))!=len(levels):
        return 'GetVipRewardRsp',{'retcode':1}
    path=Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before=stage._read(path,account);current=deepcopy(before)
        configs=catalog();r=runtime(current);count=total(current)
        if any(n not in configs or count<configs[n]['threshold'] for n in levels):
            return 'GetVipRewardRsp',{'retcode':1}
        pending=[n for n in levels if str(n) not in r['receipts']]
        rewards=[]
        try:
            for n in pending:
                reward=deepcopy(configs[n]['reward'])
                missions._preflight(current,reward)
                stage._grant_drops(current,{(i['id'],i['level']):i['num'] for i in reward['item_list']})
                r['receipts'][str(n)]={'reward_id':configs[n]['reward_id'],
                                      'claimed_at':int(time.time()),'reward':reward}
                rewards.append(reward)
        except (ValueError, missions._Rejected):
            return 'GetVipRewardRsp',{'retcode':1}
        stage._save(path,before,current);stage._sync(account,current)
    # Repeated claims report no new rewards; state snapshot still closes UI.
    return 'GetVipRewardRsp',{'retcode':0,'reward_list':rewards}


def notification_snapshot(account):
    return [('GetEquipmentDataRsp',{'retcode':0,**{k:deepcopy(account.get(k,[]))
            for k in ('weapon_list','stigmata_list','material_list')}}),snapshot(account)]
