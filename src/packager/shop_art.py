"""Restore retained shop artwork from supplied clients using 1.9 sprite layouts."""
from copy import deepcopy
import hashlib
from pathlib import Path
import zipfile
import UnityPy
from PIL import Image


def prepare(client19, client24, output, supplemental_images=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    prefix = 'assets/bin/Data/'
    prefab_name = 'f441e7f7f7f787a4897c8edd0b612778'
    texture_name = '80a0c9063f3cb5246ac5285e882c8299'
    restored = {7217: '59142d4dd13dbdb48a9d46d9e52b89ee',
                7224: 'f0a7a4fa6e508244a899237d5fd7f521',
                7226: '34fdb36ff37e0dd4d9de4495d8fbf76a',
                5606: '97965658a013602409b9179864d3ea5d'}
    with zipfile.ZipFile(client19) as old, zipfile.ZipFile(client24) as reference:
        manager_env = UnityPy.load(old.read(prefix + 'globalgamemanagers'))
        manager_file = next(iter(manager_env.files.values()))
        manager = next(o for o in manager_env.objects if o.type.name == 'ResourceManager')
        tree = manager.read_typetree()
        original_dependencies = deepcopy(tree['m_DependentAssets'])
        external_ids = {x.path: i + 1 for i, x in enumerate(manager_file.externals)}
        old_prefab, old_texture = external_ids[prefab_name], external_ids[texture_name]
        jobs = []
        for identity, source_name in restored.items():
            source = UnityPy.load(reference.read(prefix + source_name))
            source_texture = next(o.read() for o in source.objects if o.type.name == 'Texture2D')
            if source_texture.m_Name != str(identity):
                raise ValueError('Unexpected retained shop texture')
            pixels = source_texture.image
            paths = ['spriteoutput/' + category + '/' + str(identity)
                     for category in ('materialicons', 'materialfigures')]
            jobs.append((str(identity), pixels, paths))
        if supplemental_images is not None:
            root = Path(supplemental_images) / 'gallery'
            jobs.extend([
                ('m134', Image.open(root / 'm134.png').convert('RGBA'),
                 ['spriteoutput/weaponicons/weapon_cannon_b22_172_' + str(tier) for tier in (4, 5)]),
                ('unavailable', Image.open(root / 'unavailable.png').convert('RGBA'),
                 ['spriteoutput/stigmataicons/s3ai_3', 'spriteoutput/stigmatafigures/s3ai_3',
                  'spriteoutput/compat/unavailable']),
            ])
        for identity, pixels, paths in jobs:
            new_names = [hashlib.md5(('bh2017-shop-' + str(identity) + '-' + kind).encode()).hexdigest()
                         for kind in ('prefab', 'texture')]
            new_ids = []
            for name in new_names:
                if name in external_ids:
                    raise ValueError('Shop artwork already registered')
                external = deepcopy(manager_file.externals[-1])
                external.path = name
                manager_file.externals.append(external)
                new_ids.append(len(manager_file.externals))
            prefab_env = UnityPy.load(old.read(prefix + prefab_name))
            prefab_file = next(iter(prefab_env.files.values()))
            assert prefab_file.externals[1].path == texture_name
            prefab_file.externals[1].path = new_names[1]
            game_object = next(o for o in prefab_env.objects if o.type.name == 'GameObject')
            obj = game_object.read_typetree(); obj['m_Name'] = str(identity)
            game_object.save_typetree(obj)
            texture_env = UnityPy.load(old.read(prefix + texture_name))
            texture_file = next(iter(texture_env.files.values()))
            texture = next(o.read() for o in texture_env.objects if o.type.name == 'Texture2D')
            texture.m_Name = str(identity)
            texture.set_image(pixels, target_format=4)  # RGBA32; preserve source pixels.
            texture.save()
            sprite = next(o for o in texture_env.objects if o.type.name == 'Sprite')
            obj = sprite.read_typetree(); width, height = pixels.size
            obj['m_Name'] = str(identity)
            rect = dict(x=0.0, y=0.0, width=float(width), height=float(height))
            obj['m_Rect'] = rect.copy()
            rd = obj['m_RD']; rd['textureRect'] = rect.copy()
            rd['textureRectOffset'] = dict(x=0.0, y=0.0)
            rd['vertices'] = [{'pos': dict(x=x, y=y, z=0.0)} for x, y in
                              [(-width/2, -height/2), (-width/2, height/2),
                               (width/2, height/2), (width/2, -height/2)]]
            rd['indices'] = [0, 1, 2, 0, 2, 3]
            rd['settingsRaw'] = 0  # Full rectangle, unrotated and unpacked.
            rd['uvTransform'] = dict(x=1.0, y=width/2, z=1.0, w=height/2)
            sprite.save_typetree(obj)
            # Replace empty/placeholder entries without duplicate resource keys.
            tree['m_Container'] = [(key, value) for key, value in tree['m_Container'] if key not in paths]
            for path in paths:
                tree['m_Container'].append((path, dict(m_FileID=new_ids[0], m_PathID=1)))
            replacements = {old_prefab: new_ids[0], old_texture: new_ids[1]}
            for dependency in original_dependencies:
                if dependency['m_Object']['m_FileID'] not in replacements:
                    continue
                row = deepcopy(dependency)
                for pointer in [row['m_Object']] + row['m_Dependencies']:
                    pointer['m_FileID'] = replacements.get(pointer['m_FileID'], pointer['m_FileID'])
                tree['m_DependentAssets'].append(row)
            (output / new_names[0]).write_bytes(prefab_file.save())
            (output / new_names[1]).write_bytes(texture_file.save())
        tree['m_Container'].sort(key=lambda pair: pair[0])
        manager.save_typetree(tree)
        (output / 'globalgamemanagers').write_bytes(manager_file.save())
    return {'restored_items': sorted(restored), 'files': len(jobs) * 2 + 1,
            'gallery_artwork': supplemental_images is not None}
