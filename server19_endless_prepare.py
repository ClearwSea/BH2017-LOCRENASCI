"""Generate approved offline Endless data/scripts without touching the device."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import csv,json,re,zipfile,hashlib
import server19_resources as resources
from server19_stage_resources import text_record
import server19_metadata_export as metadata
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'server19-run/endless-20261026/candidate-v1'
TABLES=ROOT/'.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'
RAW=ROOT/'.local-baseline/server19-dev/resource-fallback/data/_exceloutput'
def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def raw(name):return list(csv.DictReader((RAW/name).read_text(encoding='utf-8-sig').splitlines(),delimiter='\t'))
def accepted_table(name):
 ledger=json.loads((ROOT/'server19-run/sakura-baseline-20261026-cycle4/runtime-artifacts.json').read_bytes())
 row=next(r for r in ledger if r['remote']=='/sdcard/bh3-server19-metadata/_exceloutputasset/'+name)
 data=(ROOT/row['local']).read_bytes();assert hashlib.sha256(data).hexdigest()==row['sha256']
 return json.loads(data)
def prepare():
 OUT.mkdir(parents=True,exist_ok=True)
 groups=[];rewards=accepted_table('rewarddata')
 for i in range(1,8):
  groups.append(dict(groupLevel=i,groupName='EL_GROUP_%02d'%i,isGlobal=int(i==7),minCapacity=20,maxCapacity=20,unlockCapacity=0,
   promoteRank=5 if i<7 else 0,demoteRank=6 if i==7 else 16 if i>1 else 21,prototeRewardID=980000+i*10+1,normalRewardID=980000+i*10+2,
   demoteRewardID=980000+i*10+3,baseHardLevel=float(8+6*(i-1)),deltaHardLevel=1.0))
  for rank in range(1,4):
   r={k:('' if isinstance(v,str) else 0) for k,v in rewards[0].items()};r['RewardID']=980000+i*10+rank
   r['RewardHCoin']=40+20*i+(20 if rank==1 else 0);r['RewardSCoin']=10000*i
   rewards=[x for x in rewards if x['RewardID']!=r['RewardID']]+[r]
 # Native 1.9 luaPath is a string list indexed by group, not later group:path IDs.
 base=raw('endlesstype')[0];type_row={n:metadata.convert(base.get(n,''),p) for n,p in metadata.fields(7118) if n!='luaPath'}
 type_row['luaPath']=['Lua/Levels/Event/LevelInfinite.lua']*8  # index 0 plus native group IDs 1..7
 items=[]
 uniques=accepted_table('uniquemonsterdata')
 template=uniques[0]
 for source in raw('uniquemonsterdata'):
  if not 401<=int(source['UniqueID'])<=431:continue
  lower={k.lower():v for k,v in source.items()};row={}
  for key,value in template.items():
   text=lower[key.lower()]
   if isinstance(value,list):row[key]=[type(value[0])(x) for x in text.split(',')] if text else []
   else:row[key]=type(value)(text)
  uniques=[x for x in uniques if x['uniqueID']!=row['uniqueID']]+[row]
 # Approved current-client enemy compatibility: preserve target difficulty
 # multipliers while using original-client entities/configuration/abilities.
 byid={r['uniqueID']:r for r in uniques}
 for target,reference in {421:419,422:413,430:429,431:429}.items():
  for key in ('name','monsterName','typeName','configType','AIName','attackCDNames','attackCDs','abilities'):
   byid[target][key]=byid[reference][key]
 save(OUT/'metadata/_exceloutputasset/uniquemonsterdata',uniques)
 monsters=accepted_table('monsterconfigdata')
 existing={(r['monsterName'],r['typeName']) for r in monsters}
 needed={(r['monsterName'],r['typeName']) for r in uniques if 401<=r['uniqueID']<=431}-existing
 for source in raw('monsterconfigdata'):
  lower={k.lower():v for k,v in source.items()}
  if (lower['monstername'],lower['typename']) in needed:
   monsters.append({k:type(v)(lower[k.lower()]) for k,v in monsters[0].items()})
 save(OUT/'metadata/_exceloutputasset/monsterconfigdata',monsters)
 oldfields=json.loads((TABLES/'endlessitem').read_bytes())[0]
 for row in raw('endlessitem'):
  if int(row['ID']) not in (70001,70002,70003,70008,70013,70014,70015,70016,70017):continue
  items.append({k:int(row[k]) if isinstance(v,int) else row[k] for k,v in oldfields.items()})
 drops=[dict(ID=g*100+f,endlesstype=1,group=g,level=f,dropList=[],dropDisplayList=[],firstDropList=[],firstDropDisplayList=[]) for g in range(1,8) for f in range(1,26)]
 for n,value in [('endlessgroup',groups),('endlesstype',[type_row]),('endlessdrop',drops),('endlessitem',items),('rewarddata',rewards)]:save(OUT/'metadata/_exceloutputasset'/n,value)
 save(OUT/'catalog.json',dict(floors=25,groups=groups,items=items,bot_names=json.loads((ROOT/'data/endless-bot-names.json').read_bytes()),item_ids=[r['ID'] for r in items],source='User-approved offline values; 2.4 enemy reference, 1.9 native client'))
 mapping={r['path']:r for r in resources.resource_map(resources.DEFAULT24)}
 selected=['lua/levels/event/levelinfinite.lua','lua/base/levelinfinitecommon.lua','lua/base/globalluafunctions.lua']
 with zipfile.ZipFile(resources.DEFAULT24) as z:
  for name in selected:
   data,proof=text_record(z,mapping[name],'2.4');text=data.decode('utf-8-sig')
   if name.endswith('globalluafunctions.lua'):
    start=text.index('math.randomseed =');end=text.index('GlobalLuaFunction = {}')
    text=text[:start]+'''local compatible_seed=1
math.randomseed=function(value) compatible_seed=math.floor(value)%2147483647; if compatible_seed==0 then compatible_seed=1 end end
math.random=function(a,b)
 compatible_seed=(compatible_seed*16807)%2147483647
 local x=(compatible_seed-1)/2147483646
 if a==nil then return x end
 if b==nil then b=a;a=1 end
 assert(b>=a, "Invalid random interval")
 return a+math.floor(x*(b-a+1))
end
''' + text[end:]
    configs={(r['monsterName'],r['typeName']):r for r in monsters}
    nature='{'+','.join('[%d]=%d'%(i,configs[(r['monsterName'],r['typeName'])]['nature']) for i,r in byid.items() if 401<=i<=431)+'}'
    text='local compatible_nature='+nature+'\n'+text
    text=text.replace('LevelDesign:GetMonsterNatureByUniqueID(this_uniqueID)','compatible_nature[this_uniqueID]')
    from server19_endless_pool_fix import patch as fix_pool
    text=fix_pool(text)
   if name.endswith('levelinfinitecommon.lua'):
    a=text.index('local function generate_monster_data(');b=text.index('InfiData.Settings',a)
    common_rows=raw('endlesscommon')
    entries=[]
    for m in common_rows:
     if int(m['uniqueID']) in byid and int(m['uniqueID'])>0:m['name']=byid[int(m['uniqueID'])]['monsterName']
     lo,hi=map(int,m['groupLevelRange'].split(','));entries.append('{kind=%s,lo=%s,hi=%s,name=%s,uniqueID=%s,configType=%s,thread=%s}'%(m['type'],lo,hi,json.dumps(m['name']),m['uniqueID'],json.dumps(m['configType']),m['thread']))
    function='local compatible_monsters={'+','.join(entries)+'}\nlocal function generate_monster_data(kind)\n local result={}\n local group=LevelDesign:GetEndlessGroupLevel()\n for _,r in ipairs(compatible_monsters) do if r.kind==kind and group>=r.lo and group<=r.hi then table.insert(result,{name=r.name,uniqueID=r.uniqueID,configType=r.configType,thread=r.thread}) end end\n return result\nend\n\n'
    text=text[:a]+function+text[b:]
    text=text.replace('totalSection = 33','totalSection = 25').replace('LevelDesign:GetEndlessPlayerGroup()','3 -- offline single legacy bracket, 25 floors')
    text=text.replace('#Settings.allEnvs - 2','math.max(1, #Settings.allEnvs - 2)')
    text=re.sub(r'^.*Env = "Stage_PassageWay_Battle0[13]".*\n','',text,flags=re.M)
    text=re.sub(r'^\s*\{Env = "Stage_Hyperion_Stage_AirIsland_Boss_(?:Dark|Light)"[^\n]*',
     '\t\t{Env = "NZ_Town_02", avatarPos = "Born", monsterPos = {"Center","Spawn01","Spawn02","Spawn03","Spawn04"}, bgm = "NZ_Town"},',text,flags=re.M)
    # Keep damage coroutine; later UI countdown/actor override APIs do not exist.
    for api in ('InitEndlessBlendingCountdown','LevelUpEndlessBlending','SetLevelActorLevel'):
     text=re.sub(r'LevelDesign:'+api+r'\([^\n]*\)', '-- Native 1.9: retain original actor level and damage; later '+api+' unavailable.',text)
   text=text.replace('LevelDesign:GetEndlessGroupHardLevel()','LevelDesign:GetEndlessGroupLevel()')
   p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
 save(OUT/'source-records.json',dict(resource_package=str(resources.DEFAULT24),scripts=selected,notes=['later enemy table embedded locally','25 floor bracket','native legacy group API','bleed damage retained; later countdown UI omitted','native actor level preserved']))
 return OUT
if __name__=='__main__':print(prepare())
