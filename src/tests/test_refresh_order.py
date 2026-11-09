"""Native success callbacks must observe committed state before repainting.
Execute the actual dispatch blocks without booting the network service.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "server19.py"


def dispatch(module, request, snapshots, retcode=0):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    blocks = [node for node in ast.walk(tree) if isinstance(node, ast.If)
              and ast.unparse(node.test).startswith("name in " + module + ".")
              and "values.get('retcode') == 0" in ast.unparse(node.test)]
    assert len(blocks) == 1, (module, len(blocks))
    rsp = request.removesuffix("Req") + "Rsp"
    scope = dict(name=request, values={"retcode": retcode},
                 packets=[(rsp, {"retcode": retcode})],
                 account={"main": {}, "avatar_list": []}, event=lambda *a, **k: None)
    scope[module] = SimpleNamespace(HANDLED_REQUESTS={request}, MUTATION_REQUESTS={request},
                                    notification_snapshot=lambda *a, **k: snapshots)
    exec(compile(ast.Module(body=blocks, type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["packets"]


class RefreshOrderTests(unittest.TestCase):
    def test_equipment_success_callback_sees_new_owner(self):
        for request in ("DressEquipmentReq", "ExchangeAvatarWeaponReq"):
            with self.subTest(request=request):
                packets = dispatch("server19_equipment", request,
                    [("GetAvatarDataRsp", {"owner": "new"}),
                     ("GetEquipmentDataRsp", {"owner": "new"})])
                cache = {"avatar": "old", "equipment": "old"}
                for name, body in packets:
                    if name == "GetAvatarDataRsp": cache["avatar"] = body["owner"]
                    elif name == "GetEquipmentDataRsp": cache["equipment"] = body["owner"]
                    else: self.assertEqual(cache, {"avatar": "new", "equipment": "new"})

    def test_guide_reward_refresh_reads_new_ticket_count(self):
        tickets = 0
        for name, body in dispatch("server19_cabin", "GetGuideRewardReq",
                                  [("GetEquipmentDataRsp", {"tickets": 1})]):
            if name == "GetEquipmentDataRsp": tickets = body["tickets"]
            else: self.assertEqual(tickets, 1)

    def test_failed_guide_reward_does_not_publish_success_snapshot(self):
        self.assertEqual(dispatch("server19_cabin", "GetGuideRewardReq",
            [("GetEquipmentDataRsp", {"tickets": 1})], retcode=1),
            [("GetGuideRewardRsp", {"retcode": 1})])

    def test_other_cabin_paths_keep_existing_order(self):
        self.assertEqual([p[0] for p in dispatch("server19_cabin", "IslandCollectReq",
            [("GetIslandRsp", {})])], ["IslandCollectRsp", "GetIslandRsp"])


if __name__ == "__main__":
    unittest.main()
