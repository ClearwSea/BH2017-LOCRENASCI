"""Read Lua table spans to audit Rogue room/area bindings without executing Lua."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import hashlib
import re
import server19_stage_resources as lua


class Tables:
    def __init__(self,text):
        self.text=text;self.tokens=lua.lua_tokens(text);self.pairs={};stack=[]
        for i,t in enumerate(self.tokens):
            if t[0] in ('{','(','['):stack.append(i)
            elif t[0] in ('}',')',']'):
                start=stack.pop();self.pairs[start]=i

    def atom(self,i):
        t=self.tokens[i]
        if t[0]=='{':return self.table(i)
        if t[3]=='string':return t[0][1:-1]
        if t[0].isdigit():return int(t[0])
        if t[0] in ('true','false'):return t[0]=='true'
        return ('expression',t[0])

    def table(self,start):
        end=self.pairs[start];fields={};i=start+1;position=1
        while i<end:
            if self.tokens[i][0] in (',',';'):i+=1;continue
            if i+1<end and self.tokens[i+1][0]=='=':
                key=self.tokens[i][0];i+=2
            elif self.tokens[i][0]=='[' and self.tokens[self.pairs[i]+1][0]=='=':
                key=self.atom(i+1);i=self.pairs[i]+2
            else:key=position;position+=1
            fields[key]=self.atom(i)
            # Skip the complete value, including nested tables/expressions.
            while i<end and self.tokens[i][0] not in (',',';'):
                i=self.pairs[i]+1 if i in self.pairs else i+1
        return dict(fields=fields,start=self.tokens[start][1],end=self.tokens[end][2])

    def assignment(self,name):
        parts=re.findall(r'\w+|\.',name)+['=','{']
        hits=[i+len(parts)-1 for i in range(len(self.tokens)-len(parts)+1)
              if [t[0] for t in self.tokens[i:i+len(parts)]]==parts]
        if len(hits)!=1:raise ValueError('Ambiguous Lua table assignment: '+name)
        return self.table(hits[0])


def fields(node):
    if not isinstance(node,dict):raise ValueError('Expected literal Lua table')
    return node['fields']


def bindings(text,common_raw,preset_raw):
    from server19_chiyou_dependencies import COMMON_SHA
    if hashlib.sha256(common_raw).hexdigest()!=COMMON_SHA:
        raise ValueError('Rogue room declarations changed')
    if hashlib.sha256(preset_raw).hexdigest()!='7176148a82ffe6d223ecf4c2aafe83972ee9e94db9dfcb365c5a77e996a182e5':
        raise ValueError('Rogue area generation changed')
    source=Tables(text);common=Tables(common_raw.decode('utf-8-sig'))
    rogue=fields(source.assignment('rogue_data'))
    if 'endlessmode' in rogue or 'override_name' in rogue:
        raise ValueError('Rogue override/endless binding needs separate audit')
    layouts=fields(common.assignment('roguecommon.prefabconfig'))
    points=fields(common.assignment('roguecommon.env_points'))
    chosen=list(fields(rogue['selected_prefab']).values()) if 'selected_prefab' in rogue else list(layouts)
    if not chosen or not all(isinstance(v,str) and v in layouts for v in chosen):
        raise ValueError('Nonliteral random room pool')
    level=fields(source.assignment('level.leveldata'));result=[]
    for section,path_node in fields(rogue['path']).items():
        path=fields(path_node);count=path['nodes']
        if not isinstance(count,int) or not 1<=count<=26:raise ValueError('Dynamic room count')
        areas=fields(fields(level[section])['area_config'])
        start=path.get('startprefab');start_pool=[start] if start else chosen
        for i in range(1,count+1):
            area='area_'+chr(64+i)
            configured=fields(path[i]).get('prefab') if i in path else None
            links=[v for k,v in fields(path[i]).items() if isinstance(k,int)] if i in path else []
            if any(not isinstance(v,int) or (v!=-1 and not 1<=v<=count) for v in links):
                raise ValueError('Room graph edge outside declared nodes')
            pool=start_pool if i==1 else ([configured] if configured else chosen)
            area_node=areas.get(area)
            area_text=text[area_node['start']:area_node['end']] if area_node else ''
            from server19_chapter1_readonly_audit import normal_point_literals
            explicit=sorted({p for p in normal_point_literals(area_text)
                if re.fullmatch(r'(?:Spawn|MS|Wall|InnerWall|Field|Exit|Born|Box|Arrow|Center|Trigger|Portal_|Stone|RewardPoint)[\w]*',p)})
            for scene in pool:
                if scene not in points or scene not in layouts:raise ValueError('Unknown room: '+str(scene))
                locators=fields(points[scene]);required=set(explicit)|{'Center'}
                if i==1:required.add('Born')
                for kind in ('monster','stone','wifi'):
                    required.update(fields(locators[kind]).values())
                # preplinks stores chosenportal and prefabconfig[next][k],
                # which are direction angles, not positions in the array.
                for portal in fields(layouts[scene]).values():
                    if not isinstance(portal,int):raise ValueError('Dynamic portal direction')
                    required.update((f'Portal_{portal}',f'Portal_{portal}_In'))
                result.append(dict(section_name=section,area_name=area,scene=scene,
                    selection='fixed' if (i==1 and start) or (i!=1 and configured) else 'conservative_random_pool',
                    point_names_all_branches=sorted(required),explicit_points=explicit,
                    outgoing_nodes=links,random_graph=path.get('random',False),
                    runtime_prefix=area+'_',source='create_path/add_points_to_level/portal assignment'))
    return result
