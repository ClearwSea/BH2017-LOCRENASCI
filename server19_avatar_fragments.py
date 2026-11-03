"""Bounded owned-avatar fragment rewards; no material or avatar-card substitute.

Original AvatarDataItem.GetAvatarFragmentDataItem51691@134531f constructs the
Storage item from fragment metadata, then copies avatar.fragment into number.
The fragment constructor51744 and GetMaxLimit51779 consume metadata ID/rarity/
quantityLimit. GetAvatarDataRsp is therefore the authoritative saved quantity.
Only the two Chapter1 Extra fragment IDs are audited here. New-avatar unlock,
card duplication and locked/shared-fragment ownership are separate features.
"""
import server19_stage as stage

AUDITED_IDS = {
    10101: 101, 10102: 102, 10103: 103, 10104: 104, 10112: 112,
    10201: 201, 10202: 202, 10203: 203, 10204: 204, 10211: 211, 10212: 212, 10213: 213,
    10301: 301, 10302: 302, 10303: 303, 10304: 304, 10311: 311, 10312: 312,
    10401: 401, 10402: 402, 10403: 403, 10404: 404,
    10501: 501, 10502: 502, 10504: 504,
}


def metadata(identity):
    if type(identity) is not int or identity not in AUDITED_IDS:
        raise ValueError("Fragment reward outside the audited Chapter1 flow")
    rows = stage._table("avatarfragmentdata", field="ID", identities=(identity,))
    avatars = stage._table("avatardata", field="avatarID", identities=(AUDITED_IDS[identity],))
    if len(rows) != 1 or len(avatars) != 1 or avatars[0].get("avatarFragmentID") != identity:
        raise ValueError("Avatar fragment metadata mapping changed")
    row = rows[0]
    if any(row.get(key) != value for key, value in {
            "ItemType": "11002", "BaseType": 2, "maxLv": 1, "rarity": 4,
            "quantityLimit": 2999,
            "iconPath": "SpriteOutput/AvatarFragmentIcons/" + str(identity),
            "imagePath": "SpriteOutput/AvatarFragmentFigures/" + str(identity)}.items()):
        raise ValueError("Audited fragment storage/limit configuration changed")
    return row


def grant(account, identity, level, count):
    """Mutate only caller-owned transaction copy; limits fail without a grant."""
    row = metadata(identity)
    if level != 0 or type(count) is not int or count <= 0:
        raise ValueError("Fragment drop level/count is invalid")
    avatars = account.setdefault("avatar_list", [])
    selected = [avatar for avatar in avatars if avatar.get("avatar_id") == AUDITED_IDS[identity]]
    if selected:
        total = stage._u32(selected[0].get("fragment", 0), "stored avatar fragment") + count
        if total > row["quantityLimit"]:
            raise ValueError("Avatar fragment quantity limit would lose a reward")
        selected[0]["fragment"] = total
    else:
        total = count
        if total > row["quantityLimit"]:
            raise ValueError("Avatar fragment quantity limit would lose a reward")
        avatars.append({"avatar_id": AUDITED_IDS[identity], "star": 0, "level": 1, "exp": 0, "fragment": total})
    return {"avatar_id": AUDITED_IDS[identity], "fragment_id": identity, "added": count, "total": total}
