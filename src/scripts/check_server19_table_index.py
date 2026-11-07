"""Compare indexed NS table queries with the original verified-table adapter."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import hashlib,json,tempfile,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server19_table_cache as nx_startup_tables

def run(runtime):
    sys.path.insert(0,str(Path(runtime).resolve()))
    import server19_portable as portable
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        rows=[{'id':2,'nested':[{'v':1}]},{'id':1},{'id':2},{'other':3},{'id':None},{'id':True},{'id':'2'}]
        raw=json.dumps(rows).encode();(root/'table').write_bytes(raw)
        (root/'other').write_bytes(json.dumps([{'id':9}]).encode())
        (root/'portable-manifest.json').write_text(json.dumps({'files':[{'path':n,'sha256':hashlib.sha256((root/n).read_bytes()).hexdigest()} for n in ['table','other']]}))
        stage=SimpleNamespace(TABLE_OVERRIDES={},TABLE_DIRECTORY=root)
        previous=portable.ROOT;portable.ROOT=root
        try:portable.install_table_cache(stage)
        finally:portable.ROOT=previous
        original=stage._table;stats=nx_startup_tables.install_table_cache(stage,root);candidate=stage._table
        cases=[{}, {'field':'id','identities':[2,1,2]}, {'field':'id','identities':[None]}, {'field':'id','identities':[]}, {'field':'id','identities':['2',True]}, {'field':'missing','identities':[None]}]
        for kw in cases:
            assert original('table',**kw)==candidate('table',**kw)
        selected=candidate('table',field='id',identities=[2]);selected[0]['nested'][0]['v']=999;selected.clear()
        assert candidate('table')==rows
        for kw in [{'identities':[1]},{'field':'id'},{'field':'id','identities':[[1]]}]:
            errors=[]
            for fn in [original,candidate]:
                try:fn('table',**kw)
                except Exception as e:errors.append(type(e))
            assert len(errors)==2 and errors[0]==errors[1]
        stage.TABLE_OVERRIDES['table']=root/'other'
        assert original('table')==candidate('table')==[{'id':9}]
        stage.TABLE_OVERRIDES.clear()
        (root/'table').write_bytes(b'corrupt')
        for fn in [original,candidate]:
            try:fn('table')
            except ValueError:pass
            else:raise AssertionError('changed source accepted')
        print('PASS: source order, duplicate rows, missing/null keys, bool/int equality, empty selection, nested copy isolation, override switching, corruption rejection and invalid arguments',stats)
if __name__=='__main__':run(sys.argv[1])
