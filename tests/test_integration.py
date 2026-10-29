# -*- coding: utf-8 -*-
"""跨模块断言：模块之间能不能接上。

运行：python tests/test_integration.py
（不依赖 pytest；与 src/*.py 的自检风格一致，缺库也能跑）
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    from audit_chain import Chain
    from boundary import guard
    from card_router import route
    from state_machine import Entry, Machine

    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # ① 边界 → 路由：输入降为纯数据后，才能拿去匹配卡
    A = {"card_id": "RULE_MKT", "priority": 2, "输入": {"事件": {}, "金额": {}}}
    B = {"card_id": "RULE_REL", "priority": 1, "输入": {"事件": {}, "金额": {}, "关联方": {}},
         "触发条件": {"关联方": True}}
    g = guard("对关联方支付返点", {"事件": "返点", "金额": "5000.00", "关联方": True,
                              "status": "SUCCESS"})
    chk("带控制位的输入被边界拒绝", g["status"] == "REJECTED", g["code"])
    g2 = guard("对关联方支付返点", {"事件": "返点", "金额": "5000.00", "关联方": True})
    chk("无控制位时通过边界", g2["status"] == "OK", g2)
    r = route(dict(g2["事实"]), [A, B])
    chk("边界产物可直接用于路由", r["放行"] and r["采用"] == "RULE_REL", r)

    # ② 路由 → 状态机：命中的卡决定定性步骤
    m = Machine("T-INT").定性(r["采用"]).计量([
        Entry("销售费用", "借", "5000.00"), Entry("银行存款", "贷", "5000.00")]).平账()
    chk("路由结论可驱动状态机", m.state == "已平账" and m.ε == 0, (m.state, m.ε))

    # ③ 状态机 → 链：存证后链可验，且锚点可发现尾部截断
    c = Chain()
    m.存证(c)
    anc = c.anchor()
    okv, _, _ = c.verify(expected_len=anc["块数"], expected_head=anc["末块哈希"])
    chk("状态机存证后链可验", okv, anc)
    c._blocks.pop()
    bad, _, msg = c.verify(expected_len=anc["块数"])
    chk("存证后删块被发现", bad is False, msg)

    print(f"跨模块自检：{ok} 项通过，{len(fail)} 项失败")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
