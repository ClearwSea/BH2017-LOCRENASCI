"""Reviewed compatibility adjustments for the six-chapter difficulty catalog."""


def adapt(rows):
    for row in rows:
        identity = row['levelId']
        if identity in (20103, 30103):
            # User selected the retained earlier script instead of later robots.
            row['luaFile'] = 'Lua/Levels/MainLine_Stage01/Level hard 1-3.lua'
        if identity in (20122, 20127, 20333, 30112, 30203):
            # Explicitly approved: omit the two unresolvable item identities,
            # preserving every other authored reward and its quantity.
            row['firstDisplayDropList'] = [x for x in row['firstDisplayDropList']
                                           if x['id'] not in (10601, 10603)]
            row['displayDropList'] = [x for x in row['displayDropList']
                                      if x not in (10601, 10603)]

