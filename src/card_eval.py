# -*- coding: utf-8 -*-
"""风控条件的安全求值（替代 `"condition": "debt_ratio > 80"` 这种字符串表达式）。

问题
  最常见的金融卡写法是把条件写成字符串：
      "condition": "debt_ratio > 80"
  两种实现都不可接受：
    · `eval()` —— 任何一张卡都能执行任意代码（卡是外部可编辑数据）；
    · 自己写表达式解析器 —— 又是一套 DSL，出错面比收益大。

本模块的做法
  条件写成**结构化的比较树**，不解释字符串：
      {"op": ">", "left": {"var": "debt_ratio"}, "right": {"num": 80}}
      {"and": [ {…}, {"or": [ {…}, {…} ]} ]}
  求值器只认白名单里的算子（>, >=, <, <=, ==, !=, and, or, not），
  变量必须是 facts 里**已存在**的键——缺失即拒绝，不猜（fail-closed）。

两条硬约束
  ① **不做隐式单位换算**：80 与 0.8 是两个不同的数，卡里必须写清单位字段；
  ② **不做隐式类型转换**：字符串 "85" 与数字 85 不相等，比较前必须同型。

边界
  ✅ 只做比较与布尔组合
  ❌ 不做算术（区间、比率计算请由引擎先算成事实）
"""
from __future__ import annotations

from typing import Any

OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


class CardError(Exception):
    """卡本身不合法（结构错），与「业务不通过」区分开。"""


def _operand(node: dict, facts: dict) -> Any:
    if not isinstance(node, dict) or len(node) != 1:
        raise CardError(f"操作数必须是单键对象，收到 {node!r}")
    (k, v), = node.items()
    if k == "var":
        if v not in facts:
            raise CardError(f"缺事实 {v!r}（fail-closed，不猜）")
        return facts[v]
    if k in ("num", "str", "bool"):
        return v
    raise CardError(f"未知操作数类型 {k!r}（只允许 var/num/str/bool）")


def evaluate(cond: Any, facts: dict) -> bool:
    """求值。结构不合法抛 CardError；事实缺失抛 CardError。"""
    if not isinstance(cond, dict):
        # 关键防线：拒绝字符串条件。这是本模块存在的理由。
        raise CardError(
            f"条件必须是结构化对象，收到 {type(cond).__name__}：{cond!r}\n"
            "字符串条件（如 \"debt_ratio > 80\"）不予解释——"
            "eval 不安全，自造解析器易错。请改写成比较树。")
    # 节点有两类形态，**先分形态再看键数**：
    #   ① 比较节点：{"op": ">", "left": …, "right": …}——三键
    #   ② 组合节点：{"and": [...]} / {"or": [...]} / {"not": …}——单键
    # 早先把「单键」当成通用规则，比较节点一律被拒（自检外的真实调用立刻暴露）。
    if "op" in cond:
        op = cond["op"]
        arg = cond
    else:
        if len(cond) != 1:
            raise CardError(f"组合节点必须有且仅有一个键，收到 {list(cond)}")
        (op, arg), = cond.items()

    if op in ("and", "or"):
        if not isinstance(arg, list) or not arg:
            raise CardError(f"{op} 的操作数必须是非空数组")
        vals = [evaluate(c, facts) for c in arg]
        return all(vals) if op == "and" else any(vals)
    if op == "not":
        return not evaluate(arg, facts)
    if op in OPS:
        left, right = _operand(cond.get("left"), facts), _operand(cond.get("right"), facts)
        if type(left) is not type(right):
            raise CardError(
                f"类型不一致：left={left!r}({type(left).__name__}) "
                f"right={right!r}({type(right).__name__})；不做隐式转换")
        return bool(OPS[op](left, right))
    raise CardError(f"未知算子 {op!r}（允许 {sorted(OPS) + ['and', 'or', 'not']}）")


def validate_card(card: dict) -> list[str]:
    """卡结构校验：把「字符串条件」这类问题在加载时就挡掉。"""
    probs = []
    for k in ("card_id", "输入", "规则"):
        if k not in card:
            probs.append(f"缺字段 {k}")
    for i, rule in enumerate(card.get("规则") or [], 1):
        c = rule.get("条件")
        if isinstance(c, str):
            probs.append(f"第{i}条规则的条件是字符串——必须改写成结构化比较树")
        elif not isinstance(c, dict):
            probs.append(f"第{i}条规则的条件类型非法：{type(c).__name__}")
        if rule.get("动作") not in ("FAIL_CLOSED", "CALCULATE", "PASS"):
            probs.append(f"第{i}条规则的动作非法：{rule.get('动作')!r}")
    return probs


# ---- 一张真实的卡（并购贷款风控）----
MERGER_RISK_CARD = {
    "card_id": "FIN_RISK_MERGER_001",
    "版本": "1.0",
    "来源": "《商业银行并购贷款风险管理指引》（构造示例，条款数值需以原文核对）",
    "priority": 1,
    "输入": {"负债率_百分比": {"类型": "数量", "单位": "百分数（80 表示 80%）"},
             "现金流": {"类型": "金额"},
             "行业": {"类型": "文本"}},
    "规则": [
        {"rule_id": "R1", "条件": {"op": ">", "left": {"var": "负债率_百分比"},
                                 "right": {"num": 80}},
         "动作": "FAIL_CLOSED", "消息": "标的方负债率超 80%，触发风控熔断"},
        {"rule_id": "R2", "条件": {"and": [
            {"op": "<", "left": {"var": "现金流"}, "right": {"num": 0}},
            {"op": "==", "left": {"var": "行业"}, "right": {"str": "高污染"}}]},
         "动作": "FAIL_CLOSED", "消息": "高污染行业且现金流为负，双重不达标"},
    ],
}


def run_card(card: dict, facts: dict) -> dict:
    """跑一张卡：按顺序判规则，命中即熔断；规则都不命中则放行。"""
    probs = validate_card(card)
    if probs:
        return {"status": "CARD_INVALID", "问题": probs}
    for rule in card["规则"]:
        if evaluate(rule["条件"], facts):
            return {"status": "FAIL_CLOSED", "命中规则": rule["rule_id"],
                    "消息": rule["消息"], "facts": facts}
    return {"status": "PASS", "消息": "未命中任何熔断规则", "facts": facts}


def _selftest() -> int:
    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    F85 = {"负债率_百分比": 85, "现金流": 100, "行业": "制造"}
    F79 = {"负债率_百分比": 79, "现金流": 100, "行业": "制造"}

    # ① 卡结构合法
    chk("卡结构合法", validate_card(MERGER_RISK_CARD) == [], validate_card(MERGER_RISK_CARD))
    # ② 负债率 85% 必须熔断
    r = run_card(MERGER_RISK_CARD, F85)
    chk("负债率85% 熔断", r["status"] == "FAIL_CLOSED" and r["命中规则"] == "R1", r)
    # ③ 79% 放行
    chk("负债率79% 放行", run_card(MERGER_RISK_CARD, F79)["status"] == "PASS")
    # ④ 高污染 + 负现金流 熔断（组合条件）
    r2 = run_card(MERGER_RISK_CARD, {"负债率_百分比": 50, "现金流": -1, "行业": "高污染"})
    chk("高污染且负现金流 熔断", r2["命中规则"] == "R2", r2)
    # ⑤ 只满足一个条件不熔断
    chk("仅高污染但现金流为正 ⇒ 放行",
        run_card(MERGER_RISK_CARD, {"负债率_百分比": 50, "现金流": 1,
                                 "行业": "高污染"})["status"] == "PASS")
    # ⑥ 字符串条件被拒绝（本模块存在的理由）
    try:
        evaluate("debt_ratio > 80", F85)
        chk("字符串条件被拒绝", False, "未拒")
    except CardError as e:
        chk("字符串条件被拒绝", "不予解释" in str(e), str(e)[:30])
    # ⑦ 缺事实 ⇒ 拒绝，不猜
    try:
        evaluate(MERGER_RISK_CARD["规则"][0]["条件"], {"现金流": 1})
        chk("缺事实被拒绝", False, "未拒")
    except CardError as e:
        chk("缺事实被拒绝", "缺事实" in str(e), str(e))
    # ⑧ 类型不一致 ⇒ 拒绝（"85" ≠ 85）
    try:
        evaluate({"op": ">", "left": {"var": "负债率_百分比"}, "right": {"num": 80}},
                 {"负债率_百分比": "85"})
        chk("字符串数字与数字不可比", False, "未拒")
    except CardError as e:
        chk("字符串数字与数字不可比", "类型不一致" in str(e), str(e))
    # ⑨ 未知算子 ⇒ 拒绝
    try:
        evaluate({"算": 1}, F85)
        chk("未知算子被拒绝", False, "未拒")
    except CardError:
        chk("未知算子被拒绝", True)
    # ⑩ 校验器能抓出字符串条件
    bad = validate_card({"card_id": "X", "输入": {}, "规则": [
        {"条件": "debt_ratio > 80", "动作": "FAIL_CLOSED"}]})
    chk("校验器抓出字符串条件", bad and "字符串" in bad[0], bad)

    print(f"卡条件求值自检：{ok} 项通过，{len(fail)} 项失败")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
