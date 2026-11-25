"""Replay the B-011 acquisition data edits against staged build output.

Requires the separately built 601 character/table/icon overlay. This module
does not create it, change Unity textures or declare the full feature closed.
It has no dependency on any previously built APK.
"""
import copy
import json
from pathlib import Path
from .core import BuildError

ID = 900037
GOODS = {'ID': ID, 'ItemID': 10601, 'ItemLevel': 1, 'ItemNum': 20,
         'HCoinCost': 0, 'SCoinCost': 20000, 'CostItemId1': 0, 'CostItemNum1': 0,
         'CostItemId2': 0, 'CostItemNum2': 0, 'CostItemId3': 0, 'CostItemNum3': 0,
         'CostItemId4': 0, 'CostItemNum4': 0, 'CostItemId5': 0, 'CostItemNum5': 0,
         'MaxBuyTimes': 9999, 'PriceRateID': 1, 'Discount': 10000, 'IsSuperWorth': 0}
TSV = '900037\t\t10601\t1\t20\t0\t0\t20000\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t9999\t1\t10000\t0\t1.4\t\tall'
THEME = {'key':'E07','channel':5,'version':'2.0','date':'2018-01-12',
         'name':'处刑装·紫苑＋女武神·迅羽','pool':['处刑装·紫苑','女武神·迅羽']}
ANCHOR = "    ('E06', '1.9', '2017-11-24', '御神装·勿忘', 60212, '圣仪装·今样', 60112),"
ADDITION = "    ('E07', '2.0', '2018-01-12', '处刑装·紫苑', 60502, '女武神·迅羽', 60601),"
IMAGE_OLD = "    image = f'Server19/Gacha/Rotation/{theme_key}' if theme else config['image']"
IMAGE_NEW = "    image = 'Server19/Gacha/Rotation/E02' if theme_key == 'E07' else (f'Server19/Gacha/Rotation/{theme_key}' if theme else config['image'])"

def _one_replace(text, before, after):
    if text.count(before) != 1:
        raise BuildError('B-011 preimage missing or ambiguous')
    return text.replace(before, after, 1)

def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

def _read(root, name):
    path = root / name
    if not path.is_file() or path.is_symlink():
        raise BuildError('B-011 input missing: ' + name)
    return path.read_bytes()

def plan(work):
    """Compute all edits without writing. Reject missing 601 data and conflicts."""
    work = Path(work)
    meta = 'private/data/bh3-server19-metadata/_exceloutputasset/'
    paths = ['runtime/gm-catalog.json','runtime/server19_shop_config.json',
             'runtime/server19_supply_rotation.py','runtime/server19_gacha.py',
             'runtime/.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/shopgoodsdata',
             'resources/'+meta+'shopgoodsdata',
             'resources/private/data/bh3-server19-resources/data/_exceloutput/shopgoodsdata',
             'resources/'+meta+'avatardata','runtime/supply-posters/E02.png','gm2017.html']
    data = {p:_read(work,p) for p in paths}
    avatars=json.loads(data['resources/'+meta+'avatardata'])
    if len([r for r in avatars if r.get('avatarID')==601 and r.get('avatarCardID')==60601 and r.get('avatarFragmentID')==10601]) != 1:
        raise BuildError('B-011 requires the completed 601 data overlay')
    catalog=json.loads(data[paths[0]])
    if catalog.get('items',{}).get('10601',{}).get('available') is not False or catalog['items'].get('10603',{}).get('available') is not False:
        raise BuildError('Unexpected GM fragment catalog preimage')
    catalog['items']['10601']['available']=True
    updates={paths[0]:_json(catalog)}
    shops=json.loads(data[paths[1]])
    targets=[r for r in shops if r.get('shop_id')==2]
    if len(targets)!=1 or ID in targets[0]['goods_pool']:
        raise BuildError('Unexpected fragment shop preimage')
    targets[0]['goods_pool'].append(ID);updates[paths[1]]=_json(shops)
    rotation=data[paths[2]].decode('utf-8')
    if "'E07'" in rotation: raise BuildError('Supply E07 already exists')
    updates[paths[2]]=_one_replace(rotation,ANCHOR,ANCHOR+'\n'+ADDITION).encode('utf-8')
    updates[paths[3]]=_one_replace(data[paths[3]].decode('utf-8'),IMAGE_OLD,IMAGE_NEW).encode('utf-8')
    for path in paths[4:6]:
        rows=json.loads(data[path])
        if any(r.get('ID')==ID for r in rows): raise BuildError('Fragment goods already exists')
        rows.append(copy.deepcopy(GOODS));updates[path]=_json(rows)
    path=paths[6]; text=data[path].decode('utf-8'); lines=text.splitlines()
    matches=[i for i,line in enumerate(lines) if line.startswith('900036\t')]
    if len(matches)!=1 or any(line.startswith('900037\t') for line in lines):
        raise BuildError('Unexpected TSV shop preimage')
    lines.insert(matches[0]+1,TSV);updates[path]=(('\r\n' if '\r\n' in text else '\n').join(lines)+'\n').encode('utf-8')
    page=data['gm2017.html'].decode('utf-8'); lines=page.splitlines(keepends=True)
    for key in ('data','supplyData'):
        found=[i for i,line in enumerate(lines) if line.startswith('var '+key+'=')]
        if len(found)!=1: raise BuildError('GM page data preimage missing: '+key)
        i=found[0];line=lines[i];payload=line[len('var '+key+'='):].rstrip('\r\n')
        if not payload.endswith(';'):raise BuildError('Unexpected GM data encoding')
        value=json.loads(payload[:-1])
        if key=='data':
            if value.get('items',{}).get('10601',{}).get('available') is not False:raise BuildError('Unexpected GM display preimage')
            value['items']['10601']['available']=True
        else:
            if any(r.get('key')=='E07' for r in value['themes']) or 'E07' in value['previews'] or 'E02' not in value['previews']:raise BuildError('Unexpected supply display preimage')
            value['themes'].append(copy.deepcopy(THEME));value['previews']['E07']=value['previews']['E02']
        lines[i]='var '+key+'='+_json(value).decode('utf-8')+';'+ ('\r\n' if line.endswith('\r\n') else '\n')
    updates['gm2017.html']=''.join(lines).encode('utf-8')
    if not data[paths[8]].startswith(b'\x89PNG\r\n\x1a\n'):raise BuildError('Invalid E02 poster')
    if (work/'runtime/supply-posters/E07.png').exists():raise BuildError('E07 poster already exists')
    updates['runtime/supply-posters/E07.png']=data[paths[8]]
    return updates

def apply(work):
    work=Path(work);updates=plan(work)
    for name,data in updates.items():
        p=work/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    return {'modified':sorted(updates),'scope':'B011 data only; requires character and icon overlays'}
