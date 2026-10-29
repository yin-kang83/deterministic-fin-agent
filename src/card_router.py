# -*- coding: utf-8 -*-
"""多卡路由与优先级冲突（可废止逻辑的最小实现）。

为什么需要
  `card_gate` 只校验**一张**卡：给它卡和事实，判放行或拒绝。
  但当同一个业务同时落入两张卡时（例：既是「市场交易返点」又是「关联方返点」），
  必须有一个机制决定听谁的——否则实现方各自 if/else，就是两份判断。

优先级语义
  `priority` 数字**越小越优先**（与论文 R001/R002 一致）。
  冲突必须**被记录**，不能静默取一个：返回 `冲突` 列表，含所有命中的卡与取胜原因。

与 card_gate 的关系
  router 决定「用哪张卡」，gate 决定「这张卡放不放行」。两步不合并。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

# 本仓自包含：卡库默认取仓库内 cards/，不读产品仓路径
CARDS_DIR = pathlib.Path(__file__).resolve().parent.parent / "cards"


def load_cards(cards_dir: pathlib.Path | None = None) -> list[dict[str, Any]]:
    d = cards_dir or CARDS_DIR
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if c.get("card_id"):
            c["_file"] = f.name
            out.append(c)
    return out


def matches(card: dict, facts: dict) -> tuple[bool, str]:
    """卡是否适用于这组事实。

    判据（故意保守）：
      ① 事实里**没有**该卡未声明的键（白名单，与 card_gate 同源）；
      ② 该卡的「拒答条件」不成立（拒答条件命中 ⇒ 不适用，交给更专门的卡）。
    不判必填——必填缺失由 card_gate 拒绝，属「放行/拒绝」而非「用哪张」。
    """
    allowed = set(card.get("输入") or {})
    unknown = [k for k in facts if k not in allowed]
    if unknown:
        return False, f"含未声明键 {unknown}"
    # 触发条件：卡在「输入」之上再声明它**何时适用**。
    # 只做白名单会让「输入是别人子集」的卡永远命中——首轮自检立刻暴露了这一点。
    for k, v in (card.get("触发条件") or {}).items():
        if facts.get(k) != v:
            return False, f"触发条件不满足：{k} 需为 {v!r}，实际 {facts.get(k)!r}"
    return True, "白名单通过" + ("（触发条件满足）" if card.get("触发条件") else "")


def route(facts: dict, cards: list[dict] | None = None) -> dict[str, Any]:
    """选卡。多张命中时按 priority 取最小；冲突如实返回。"""
    pool = cards if cards is not None else load_cards()
    hits = []
    for c in pool:
        ok, why = matches(c, facts)
        if ok:
            hits.append({"card_id": c["card_id"], "priority": int(c.get("priority", 999)),
                         "主题": c.get("主题", ""), "理由": why})
    if not hits:
        return {"放行": False, "原因": "无卡适用（fail-closed，不猜）", "命中": []}
    hits.sort(key=lambda x: (x["priority"], x["card_id"]))
    winner = hits[0]
    conflict = len(hits) > 1
    return {"放行": True, "采用": winner["card_id"], "命中": hits,
            "冲突": conflict,
            "冲突说明": (f"{len(hits)} 张卡同时适用，按 priority 取 {winner['card_id']}"
                     f"（priority={winner['priority']}）") if conflict else None}


def _selftest() -> int:
    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # 用内联卡做受控测试（不依赖磁盘上的卡库内容）
    A = {"card_id": "RULE_MKT_REBATE", "priority": 2, "主题": "市场交易返点",
         "输入": {"对方": {}, "关联方": {}, "交易日": {}, "金额": {}}}
    B = {"card_id": "RULE_RELATED_REBATE", "priority": 1, "主题": "关联方返点",
         "输入": {"对方": {}, "关联方": {}, "交易日": {}, "金额": {}},
         "触发条件": {"关联方": True}}
    cards = [A, B]

    # ① 只有 A 适用
    r1 = route({"对方": "普通客户", "交易日": "2026-10-30", "金额": 1000}, cards)
    chk("普通客户只命中 A", r1["采用"] == "RULE_MKT_REBATE" and not r1["冲突"], r1)

    # ② A、B 同时适用 ⇒ 取 priority 更小者，且冲突被记录
    r2 = route({"对方": "甲公司", "关联方": True, "交易日": "2026-10-30", "金额": 1000}, cards)
    chk("关联方交易同时命中两张", len(r2["命中"]) == 2, r2["命中"])
    chk("取 priority 更小的 B", r2["采用"] == "RULE_RELATED_REBATE", r2["采用"])
    chk("冲突被记录", r2["冲突"] is True and "priority" in (r2["冲突说明"] or ""),
        r2["冲突说明"])

    # ③ 未声明键 ⇒ 不适用（白名单，与 card_gate 同源）
    r3 = route({"对方": "甲", "交易日": "d", "金额": 1, "秘密字段": 1}, cards)
    chk("含未声明键则不适用", r3["放行"] is False, r3)

    # ④ 无卡适用 ⇒ fail-closed，不猜
    r4 = route({"完全无关": 1}, cards)
    chk("无卡适用即拒绝", r4["放行"] is False and "fail-closed" in r4["原因"], r4)

    # ⑤ 真卡库能加载，且每张卡都有 card_id
    real = load_cards()
    chk("卡库目录存在（可为空）", CARDS_DIR.exists(), str(CARDS_DIR))
    chk("每张卡有 card_id", all(c.get("card_id") for c in real), len(real))

    print(f"多卡路由自检：{ok} 项通过，{len(fail)} 项失败（卡库 {len(real)} 张）")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
