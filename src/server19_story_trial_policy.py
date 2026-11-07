"""指定试用角色限制 / Prescribed story trial roster policy.

Only stages explicitly supplied by the deployment are selected. Ordinary
stages and in-level scripted support avatars retain their existing behavior.
"""
from copy import deepcopy


def prescribed_rosters(level_rows, avatar_rows, stage_ids):
    trials = {row['ID']: row for row in avatar_rows}
    result = {}
    for row in level_rows:
        identity = row['stageID']
        if identity not in stage_ids or not row['avatarList']:
            continue
        if identity in result:
            raise ValueError('Duplicate trial stage: ' + str(identity))
        avatars = tuple(trials[key]['avatarID'] for key in row['avatarList'])
        if any(type(key) is not int or key <= 0 for key in avatars):
            raise ValueError('Invalid prescribed avatar')
        result[identity] = tuple(dict.fromkeys(avatars))
    return result


def trial_only_rows(level_rows, rosters):
    """复用原生禁用自有角色模式 / Reuse the native trial-only mode."""
    rows = deepcopy(level_rows)
    for row in rows:
        if row['stageID'] in rosters:
            if row['fakeAvatarID']:
                raise ValueError('Fake-avatar stage requires separate consumer review')
            row['allowedPlayerAvatar'] = 0
    return rows


def configure(metadata_dir):
    import json
    from pathlib import Path
    import server19_stage as stage
    directory = Path(metadata_dir)
    levels = json.loads((directory / 'leveltrialdata').read_bytes())
    avatars = json.loads((directory / 'avatartrialdata').read_bytes())
    rosters = prescribed_rosters(levels, avatars, stage.supported_stage_ids())
    if any(row['allowedPlayerAvatar'] != 0 or row['fakeAvatarID']
           for row in levels if row['stageID'] in rosters):
        raise ValueError('Client trial-only policy has not been projected')
    stage.STORY_TRIAL_AVATARS = rosters
    return rosters


def main():
    import argparse
    import hashlib
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--stage-ids', type=int, nargs='+', required=True)
    args = parser.parse_args()
    levels_raw = (args.metadata_dir / 'leveltrialdata').read_bytes()
    avatars_raw = (args.metadata_dir / 'avatartrialdata').read_bytes()
    levels, avatars = json.loads(levels_raw), json.loads(avatars_raw)
    rosters = prescribed_rosters(levels, avatars, set(args.stage_ids))
    projected = trial_only_rows(levels, rosters)
    args.out.mkdir(parents=True, exist_ok=False)
    output = json.dumps(projected, ensure_ascii=False, separators=(',', ':')).encode()
    (args.out / 'leveltrialdata').write_bytes(output)
    (args.out / 'avatartrialdata').write_bytes(avatars_raw)
    manifest = dict(policy='prescribed_trial_only', rosters=rosters,
                    changed_rows=[a['stageID'] for a, b in zip(levels, projected) if a != b],
                    source_sha256=hashlib.sha256(levels_raw).hexdigest(),
                    output_sha256=hashlib.sha256(output).hexdigest(),
                    avatartrial_sha256=hashlib.sha256(avatars_raw).hexdigest())
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
