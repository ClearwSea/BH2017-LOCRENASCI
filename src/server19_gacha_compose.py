"""Compose native supply art without regenerating weapon/stigmata subjects.

User approved deterministic original-art compositing on 2026-10-13.
Only uniform resizing and alpha placement are applied to source sprites.
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

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ART = ROOT / 'assets/gacha/native'
WIDTH, HEIGHT = 1680, 350


def compose(background, output, font_path, art_only=False, pool='precision'):
    if output.exists():
        raise ValueError('Use a new versioned output; preserve previous artwork')
    canvas = Image.open(background).convert('RGBA')
    # Background may be resized independently; original subjects keep aspect.
    canvas = canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    layer = Image.new('RGBA', canvas.size)
    draw = ImageDraw.Draw(layer)
    draw.rectangle((0, 0, 730, HEIGHT), fill=(12, 17, 64, 112))
    canvas.alpha_composite(layer)
    if pool == 'expansion':
        if not art_only:
            raise ValueError('Expansion artwork must retain native UI text only')
        source = Image.open(ART / 'ziyuan-card.png').convert('RGBA')
        scaled = source.resize((873, 600), Image.Resampling.LANCZOS)
        canvas.alpha_composite(scaled, (805, -78))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.convert('RGB').save(output)
        output.with_suffix('.json').write_text(json.dumps({
            'method': 'original_sprite_alpha_compositing', 'pool': pool,
            'size': [WIDTH, HEIGHT], 'text_in_bitmap': False,
            'source': 'assets/gacha/native/ziyuan-card.png',
            'subjects_generated': False, 'device_updated': False,
            'human_visual_acceptance': 'pending'}, indent=2)+'\n', 'utf8')
        return output
    # Original figures are slightly staggered, with clear faces and no mirroring.
    placements = [('dracula-top.png', 684, -37, 470),
                  ('dracula-middle.png', 985, -23, 448),
                  ('dracula-bottom.png', 1275, -2, 417)]
    for name, x, y, height in placements:
        source = Image.open(ART / name).convert('RGBA')
        width = round(source.width * height / source.height)
        scaled = source.resize((width, height), Image.Resampling.LANCZOS)
        canvas.alpha_composite(scaled, (x, y))
    # Native inventory icon is 128x112 and clips the lower cross. Instead use
    # the unchanged full weapon render from its published original guide card.
    # Cropping removes labels/stars, not any weapon pixels; no subject redraw.
    guide = Image.open(ART / 'bloodembrace-guide-original.jpg').convert('RGBA')
    weapon = guide.crop((20, 106, 825, 414))
    # Remove the guide's blue backdrop and its lower-right UI label. RGB values
    # of retained subject pixels are unchanged; this is an alpha mask only.
    pixels = weapon.load()
    for y in range(weapon.height):
        for x in range(weapon.width):
            r, g, b, a = pixels[x, y]
            if (b > r + 9 and g > r + 5) or (x >= 650 and y >= 235):
                pixels[x, y] = (r, g, b, 0)
    weapon = weapon.resize((275, round(308 * 275 / 805)), Image.Resampling.LANCZOS)
    canvas.alpha_composite(weapon, (430, 165))
    draw = ImageDraw.Draw(canvas)
    def text(x, y, value, size, color='#f6f5ff'):
        font = ImageFont.truetype(str(font_path), size)
        draw.text((x+2, y+3), value, font=font, fill='#181a50')
        draw.text((x, y), value, font=font, fill=color)
    if not art_only:
        text(40, 22, '精准补给', 70)
        draw.line((42, 114, 394, 114), fill='#ab9ee7', width=2)
        text(44, 149, '仿犹大·血之拥抱', 30)
        text(44, 205, '德古拉（上、中、下）', 29)
        text(45, 294, '获取概率提升', 26, '#cceaff')
    # All text and figure placement is rendered directly at native 4.2:1.
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert('RGB').save(output)
    receipt = {'method': 'original_sprite_alpha_compositing',
               'size': [WIDTH, HEIGHT], 'background': str(background),
               'subjects_generated': False, 'source_art': str(ART),
               'text_in_bitmap': not art_only,
               'allowed_subject_operations': ['uniform_resize', 'alpha_placement'],
               'weapon': {'source': 'bloodembrace-guide-original.jpg',
                          'crop': [20, 106, 825, 414], 'background_alpha_mask_only': True,
                          'redraw': False},
               'placements': placements, 'device_updated': False,
               'human_visual_acceptance': 'pending'}
    output.with_suffix('.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', 'utf8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--background', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--art-only', action='store_true')
    parser.add_argument('--pool', choices=('precision', 'expansion'), default='precision')
    args = parser.parse_args()
    print(compose(args.background, args.output, args.font, args.art_only, args.pool))
