"""Replay reviewed V0.3.0 staged content from an explicit supplemental package.

The package contains data only, with before/after SHA-256 for every path. This
stage runs after v021-game-content and before resource-packs/runtime-capabilities.
It never reads an old APK or carries over generated manifests or bulletins.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
from .core import BuildError

CONTENT_MANIFEST_SHA256='fe5ec9c53a45ffe65f7467c7cc5c6026b1110397d5ebd055c5ae98a753c70e10'
# The current original-input generator already includes the reviewed 604/804/805
# rows and the fixed-fire correction. Their exact generated preimages were
# checked against the accepted overlay: the existing rows match its output.
GENERATED_PREIMAGES={
    'runtime/.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/avatarsubskilldata': 'a30a6b3869f840f672e5ec1fc0846f8e186430265b39277d88def7b9e16c6f54',
    'resources/private/data/bh3-server19-metadata/_exceloutputasset/avatarsubskilldata': 'a30a6b3869f840f672e5ec1fc0846f8e186430265b39277d88def7b9e16c6f54',
    'resources/private/data/bh3-server19-baked/_baked/bakedabilitydata': 'f700a1952740dffeed45ed458a86a2e6b95102fc6427d13268d1982e2e7b89f1',
}

def _hash(data): return hashlib.sha256(data).hexdigest()

def plan(work, supplement):
    work=Path(work);root=Path(supplement)/'fuka601/v1/content'
    manifest_path=root/'manifest.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise BuildError('Missing reviewed V0.3.0 content manifest')
    manifest_bytes=manifest_path.read_bytes()
    if _hash(manifest_bytes)!=CONTENT_MANIFEST_SHA256:
        raise BuildError('Unreviewed V0.3.0 content manifest')
    manifest=json.loads(manifest_bytes)
    if manifest.get('schema') != 1 or manifest.get('kind') != 'bh2017-v030-verified-content':
        raise BuildError('Unexpected V0.3.0 content manifest')
    result=[];seen=set()
    for row in manifest.get('files',[]):
        name=row['path']; parts=PurePosixPath(name)
        if '\\' in name or parts.is_absolute() or '..' in parts.parts or name in seen or not (name.startswith('runtime/') or name.startswith('resources/') or name=='gm2017.html'):
            raise BuildError('Invalid V0.3.0 content target: '+name)
        seen.add(name)
        if name.endswith(('/portable-manifest.json','/build-capabilities.json','/server19_bulletin.py')):
            raise BuildError('Cannot replace generated manifest, capability or bulletin: '+name)
        payload_name=row['payload']; rel=PurePosixPath(payload_name)
        if '\\' in payload_name or rel.is_absolute() or '..' in rel.parts or not payload_name.startswith('payload/'):
            raise BuildError('Invalid V0.3.0 payload path')
        source=root/Path(*rel.parts);target=work/Path(*parts.parts)
        if not source.is_file() or source.is_symlink() or target.is_symlink() or not target.resolve().is_relative_to(work.resolve()) or not source.resolve().is_relative_to(root.resolve()):
            raise BuildError('Missing or linked V0.3.0 content: '+name)
        data=source.read_bytes()
        if _hash(data)!=row['after'] or len(data)!=row['size']:
            raise BuildError('V0.3.0 payload hash mismatch: '+name)
        current=_hash(target.read_bytes()) if target.is_file() else None
        if current!=row['before'] and not (name in GENERATED_PREIMAGES and current==GENERATED_PREIMAGES[name]):
            raise BuildError('V0.3.0 preimage mismatch: '+name+' ('+str(current)+')')
        result.append((target,data,name,row['after']))
    if len(seen)!=manifest.get('count') or not result:
        raise BuildError('V0.3.0 content count mismatch')
    return result

def apply(work, supplement):
    updates=plan(work,supplement)
    for target,data,name,expected in updates:
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        if _hash(target.read_bytes())!=expected:raise BuildError('V0.3.0 output mismatch: '+name)
    return {'files':len(updates),'content_manifest_sha256':_hash((Path(supplement)/'fuka601/v1/content/manifest.json').read_bytes())}
