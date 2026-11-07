"""Build scoped601 ability adapters, requiring matching native input/SP support.

The output is a research overlay until native behavior and resource closure pass.
Never deploy the stage7-based research containers over the live containers.
"""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import argparse
import json
from pathlib import Path
import server19_avatar_battle_resources as batch
import server19_stage_abilities as ability
import server19_resources as resources

ROOT=Path(__file__).resolve().parent
HOLD='MoleMole.Config.AvatarSkillButtonHoldModeExMixin'
OLD_HOLD='MoleMole.Config.AvatarSkillButtonHoldModeMixin'
RESTRICT='MoleMole.Config.ModifyDamageTakenWithRestrictMixin'
OLD_DAMAGE='MoleMole.Config.ModifyDamageTakenMixin'
HEAL='MoleMole.Config.HealSP'
ALIASES={HOLD:OLD_HOLD,RESTRICT:OLD_DAMAGE}
BASE_SCHEMA=batch.BattleSchema
BASE_READER=batch.BattleReader
BASE_TERMINALS=batch.retained_terminals


class FukaSchema(BASE_SCHEMA):
    def check(self,name):
        if name not in ALIASES:
            return super().check(name)
        if name in self.checks:
            return
        target=ALIASES[name]
        new=self.members(name,False);old=self.members(target,True)
        removed=['SkillIndex'] if name==HOLD else ['FireDamageTakenRatio','IceDamageTakenRatio','ThunderDamageTakenRatio']
        retained=[(n,p) for n,p in new if n not in removed]
        assert [(n,self.signature(p,False)) for n,p in retained]==[(n,self.signature(p,True)) for n,p in old]
        self.checks[name]={'type':name,'source_fields':[n for n,_ in new],
            'original_fields':[n for n,_ in old],'excluded_fields':removed,
            'compatibility_target':target,'requires_native_fuka601_adapter':True}

    def union(self,kind,tag,original):
        concrete,_=self.resolve_tag(kind,tag,original)
        if not original and concrete in ALIASES:
            assert kind==ability.MIXIN
            self.check(concrete)
            target=self.original_tags[kind][ALIASES[concrete]][0]
            return concrete,target
        return super().union(kind,tag,original)


class FukaReader(BASE_READER):
    def class_value(self,name,path,depth=0):
        if self.original or name not in (HOLD,RESTRICT,HEAL) or self.data[self.pos]==0xc0:
            return super().class_value(name,path,depth)
        self.schema.check(name)
        members=self.schema.members(name,False)
        node=self.header('array')
        if node['count']!=len(members):raise ValueError('Fuka source field count changed')
        node['children']=[]
        removed=self.schema.checks[name].get('excluded_fields',[])
        seen={}
        for field,pointer in members:
            child=self.typed(pointer,path+'.'+field,depth+1)
            node['children'].append(child);raw=self.data[child['start']:child['end']];seen[field]=raw
            if field not in removed:continue
            if name==HOLD:
                if field!='SkillIndex' or batch.baked.decode_integer(self.data,child)!=2:
                    raise ValueError('Only601 skill-index2 hold is supported')
                reason='Native601 button adapter consumes original hold lifecycle for SKL02 instead of ATK'
            elif name==HEAL:
                if field!='ConsumeWithProperty' or raw not in (b'\xc0',b'\xc3'):
                    raise ValueError('Fuka SP adapter requires true or original nil')
                reason='Native601 cost-SP calculation applies source cost delta and ratio'
            else:
                if raw!=b'\xc0':raise ValueError('Element-specific damage ratios are active; native backport required')
                reason='Only nil added element ratios are removed; identity-event profile checked below'
            self.edits.append((child['start'],child['end'],b''))
            self.records.append({'operation':'remove_later_field','path':path+'.'+field,
                'source_byte_span':[child['start'],child['end']],
                'reason':reason,'source_hex':raw.hex(),'requires_native_fuka601_adapter':name in (HOLD,HEAL)})
        if name==RESTRICT:
            # Restrict-specific event branches have no active per-element flags,
            # ratios, predicates or actions in these two actual601 instances.
            if seen.get('ModifyElemental')!=b'\xc3' or any(v!=b'\xc0' for k,v in seen.items() if k!='ModifyElemental'):
                raise ValueError('Restrict damage mixin is not the bounded identity profile')
        if name==HEAL:
            amount=path+'.Amount.fixedValue'
            leaf=self.leaves.get(amount)
            if seen.get('ConsumeWithProperty')==b'\xc3' and (not leaf or self.data[slice(*leaf['span'])]!=bytes.fromhex('cac1c80000')):
                raise ValueError('Only the actual601 fixed -25 SP cost is adapted')
        self.edits.append((node['start'],node['header_end'],ability.array_bytes(len(members)-len(removed))))
        node['end']=self.pos
        return node


def terminals(reader):
    source,translated=BASE_TERMINALS(reader)
    normalized={}
    for path,leaf in translated.items():
        for before,after in ALIASES.items():path=path.replace('<'+before+'>','<'+after+'>')
        if path in normalized:raise ValueError('Fuka translated terminal collision')
        normalized[path]=leaf
    return source,normalized


def build(candidate,output):
    candidate,output=Path(candidate).resolve(),Path(output).resolve()
    if not candidate.is_relative_to(ROOT) or not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use existing workspace candidate and fresh output')
    output.mkdir(parents=True)
    previous=(batch.TABLES,batch.BattleSchema,batch.BattleReader,batch.retained_terminals,batch.apply_edits)
    source=(batch.BASE/'reference'/ability.PATH).read_bytes()
    source_spans=batch.packed(source)[5]
    identities={span:identity for identity,span in source_spans.items()}
    projected={}
    def capture(*args,**kwargs):
        value=previous[4](*args,**kwargs)
        identity=identities.get((args[1],args[2]))
        if identity is None:raise ValueError('Projected root has no actual source identity')
        projected[identity]=value
        return value
    try:
        batch.TABLES=candidate/'battle-tables'
        batch.BattleSchema=FukaSchema;batch.BattleReader=FukaReader;batch.retained_terminals=terminals
        batch.apply_edits=capture
        files,report=batch.build(resources.DEFAULT19,resources.DEFAULT24)
    finally:
        batch.TABLES,batch.BattleSchema,batch.BattleReader,batch.retained_terminals,batch.apply_edits=previous
    for name,raw in files.items():
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    # Retain verified roots independently of batch resource readiness. They are
    # research inputs only; the later actual-device merge owns resource gates.
    roots=[]
    failed={(r['key'],r['variant']) for r in report['unsupported_roots']}
    for (key,variant),value in projected.items():
        if (key,variant) in failed:continue
        name=f'root-candidates/{key}-{variant}.bin'
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
        roots.append({'key':key,'variant':variant,'sha256':batch.baked.sha(value),'file':name,
                      'original_reader_check':'Passed shared bounded consumer and retained terminal checks'})
    report['research_root_candidates']=roots
    report['deployment_allowed']=False
    report['requires_native_support']=['601 SKL02 hold lifecycle','601 ConsumeWithProperty SP cost']
    report['limits']=['Research stage7 container: merge only selected roots into actual Sony resource',
                      'Original reader consumption does not prove native gameplay semantics']
    (output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();r=build(args.candidate,args.output)
    print(json.dumps({'unsupported_roots':r['unsupported_roots'],'deployment_allowed':False},ensure_ascii=False))
