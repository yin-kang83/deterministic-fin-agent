# -*- coding: utf-8 -*-
"""记账状态机 + 强制平账（ε = 0）。

论文里的「确定性状态机……强制平账反证（ε_t = 0）」原先是句空话：
演示代码只是把金额抄进分录，没有任何平账校验，也没有状态。

本模块把它做成可跑的东西：
  ① **状态机**：待处理 → 已定性 → 已计量 → 已平账 → 已存证。
     任一环节失败即进入终态「拒绝」，**不可回退**（可废止逻辑：被更高优先级否定后不再继续）。
  ② **平账反证**：借贷双方各自用 Decimal 求和，残差 ε = 借方 − 贷方。
     **ε 必须精确等于 0**（Decimal 相等，不用容差）——容差会放过 0.01 的错。
  ③ **非法转移**：跳步（如从「待处理」直接到「已存证」）必须被拒绝并记录。

边界（写明，免得被当成万灵药）
  ✅ 保证「分录自身借贷相等」
  ❌ 不保证「分录方向符合准则」——那是定性环节（卡 + 规则）的职责，本模块只验算术。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

STATES = ("待处理", "已定性", "已计量", "已平账", "已存证")
NEXT = {STATES[i]: STATES[i + 1] for i in range(len(STATES) - 1)}
TERMINAL_FAIL = "拒绝"


@dataclass
class Entry:
    """一笔分录行。方向只能是 借 / 贷。"""
    科目: str
    方向: str
    金额: Decimal

    def __post_init__(self) -> None:
        if self.方向 not in ("借", "贷"):
            raise ValueError(f"方向必须是 借/贷，收到 {self.方向!r}")
        if isinstance(self.金额, float):
            raise TypeError("金额不得用 float")
        self.金额 = Decimal(str(self.金额))
        if self.金额 < 0:
            raise ValueError("金额不得为负；负数只会掩盖方向写反")


@dataclass
class Machine:
    trace_id: str
    state: str = "待处理"
    log: list[str] = field(default_factory=list)
    ε: Decimal | None = None

    def _to(self, target: str, why: str) -> None:
        expected = NEXT.get(self.state)
        if self.state in (TERMINAL_FAIL, "已存证"):
            raise RuntimeError(f"{self.state} 是终态，不可再转移")
        if target != expected:
            raise RuntimeError(f"非法转移：{self.state} → {target}（应到 {expected}）；{why}")
        self.state = target
        self.log.append(f"{self.state}：{why}")

    def 定性(self, card_id: str) -> "Machine":
        self._to("已定性", f"命中卡 {card_id}")
        return self

    def 计量(self, entries: list[Entry]) -> "Machine":
        if not entries:
            raise ValueError("无分录，不得进入计量")
        self.entries = entries
        self._to("已计量", f"{len(entries)} 条分录")
        return self

    def 平账(self) -> "Machine":
        """强制平账：ε 必须精确为 0。"""
        dr = sum((e.金额 for e in getattr(self, "entries", []) if e.方向 == "借"), Decimal("0"))
        cr = sum((e.金额 for e in getattr(self, "entries", []) if e.方向 == "贷"), Decimal("0"))
        self.ε = dr - cr
        if self.ε != Decimal("0"):
            self.state = TERMINAL_FAIL
            self.log.append(f"拒绝：借贷不平，ε={self.ε}")
            raise ValueError(f"借贷不平：借 {dr} / 贷 {cr} / ε={self.ε}")
        self._to("已平账", f"借={dr} 贷={cr} ε=0")
        return self

    def 存证(self, chain=None) -> "Machine":
        rec = {"trace_id": self.trace_id, "ε": str(self.ε), "分录": [
            {"科目": e.科目, "方向": e.方向, "金额": format(e.金额, "f")}
            for e in getattr(self, "entries", [])]}
        if chain is not None:
            chain.append(rec)
        self._to("已存证", "已入底稿链")
        return self


def _selftest() -> int:
    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # ① 正常流程走到已存证
    m = Machine("T-1").定性("RULE_MKT").计量([
        Entry("销售费用", "借", "5000.00"), Entry("银行存款", "贷", "5000.00")]).平账().存证()
    chk("五步走完", m.state == "已存证", m.state)
    chk("ε 精确为 0", m.ε == Decimal("0"), m.ε)

    # ② 不平必须被拒（且是终态）
    m2 = Machine("T-2").定性("R").计量([
        Entry("销售费用", "借", "5000.00"), Entry("银行存款", "贷", "4999.99")])
    try:
        m2.平账()
        chk("不平被拒", False, "未拒")
    except ValueError:
        chk("不平被拒", m2.state == "拒绝" and m2.ε == Decimal("0.01"), (m2.state, m2.ε))
    chk("ε=0.01 不被容差放过", m2.ε != Decimal("0"), m2.ε)

    # ③ 非法跳步被拒
    m3 = Machine("T-3")
    try:
        m3._to("已存证", "跳步")
        chk("跳步被拒", False, "未拒")
    except RuntimeError as e:
        chk("跳步被拒", "非法转移" in str(e), str(e))

    # ④ 终态不可再转移
    try:
        m2._to("已存证", "试图继续")
        chk("终态不可转移", False, "未拒")
    except RuntimeError as e:
        chk("终态不可转移", "终态" in str(e), str(e))

    # ⑤ 金额纪律
    for bad, why in ((lambda: Entry("a", "借", 0.1), "float 被拒"),
                     (lambda: Entry("a", "错", "1"), "方向必须借贷"),
                     (lambda: Entry("a", "借", "-1"), "负金额被拒")):
        try:
            bad()
            chk(why, False, "未拒")
        except (TypeError, ValueError):
            chk(why, True)

    # ⑥ 与哈希链联动：存证后链可验
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from audit_chain import Chain
    c = Chain()
    Machine("T-4").定性("R").计量([
        Entry("库存商品", "借", "100.00"), Entry("银行存款", "贷", "100.00")]).平账().存证(c)
    okv, pos, _ = c.verify()
    chk("存证后链完整", okv and pos is None, (okv, pos, _))
    c.tamper_for_test(0, "ε", "1.00")
    okv2, pos2, _ = c.verify()
    chk("篡改 ε 被发现", okv2 is False and pos2 == 0, (okv2, pos2))

    print(f"记账状态机自检：{ok} 项通过，{len(fail)} 项失败")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
