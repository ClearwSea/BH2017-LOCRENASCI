"""User-approved local compatibility policy; NOT recovered official rates.

2026-11-10: item 8403, group 1009, one reward per jar, equal weights.
7.0 export text identifies the two rewards; quantities/weights are custom.
"""
SAKURA_JAR = {
    "material_id": 8403,
    "drop_group": 1009,
    "rewards": (
        {"item_id": 10212, "num": 1, "weight": 50},
        {"item_id": 10304, "num": 1, "weight": 50},
    ),
}
