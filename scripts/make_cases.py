# -*- coding: utf-8 -*-
"""生成 cases/ 下的干净案例。

为什么用脚本生成而不是手写 JSON
  案例要能被复现和批量校验（如「每条都必须有来源与依据」）。
  脚本是唯一事实源，JSON 是产物。

数据纪律
  全部为**构造**案例，不复用任何业务数据；每条都必须写明「来源」与「依据」。
"""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "cases"

CASES = [
    {
        "id": "CASE-001",
        "来源": "构造（合成数据，非真实业务数据）",
        "用途": "验证 fail-closed：缺关键事实即拒绝，不猜",
        "原始文本": "老板说给十万现金返点，没发票。",
        "期望事实集": {"事件": "返点", "支付方式": "现金", "有发票": False,
                   "金额": "100000.00"},
        "期望结果": {"status": "REJECTED",
                  "原因": "无票现金返点触及红线，拒绝而非计算"},
        "依据": "《企业所得税税前扣除凭证管理办法》第九条（无合法凭证不得税前扣除）；本案例为构造，仅用于验证机制",
        "对应断言": "tests/test_cases.py::test_case_001",
    },
    {
        "id": "CASE-002",
        "来源": "构造（合成数据，非真实业务数据）",
        "用途": "验证多卡冲突：同一业务命中两张卡时按 priority 取，且冲突被记录",
        "原始文本": "对甲公司（本公司关联方）支付市场推广返点五千元，已取得发票。",
        "期望事实集": {"事件": "返点", "对方": "甲公司", "关联方": True,
                   "支付方式": "转账", "有发票": True, "金额": "5000.00"},
        "期望结果": {"采用卡": "RULE_RELATED_REBATE", "冲突": True,
                  "说明": "市场返点卡与关联方返点卡同时适用，按 priority 取关联方卡"},
        "依据": "CAS 36 关联方披露（关联方交易须单独识别与披露）；本案例为构造",
        "对应断言": "tests/test_cases.py::test_case_002",
    },
    {
        "id": "CASE-003",
        "来源": "构造（合成数据，非真实业务数据）",
        "用途": "验证哈希链：篡改历史底稿必须被发现并定位",
        "原始文本": "（不涉及业务，直接构造两条底稿后篡改第一条）",
        "期望事实集": None,
        "期望结果": {"verify_前": True, "篡改后": False, "断点位置": 0},
        "依据": "机制验证，无准则依据；本案例为构造",
        "对应断言": "tests/test_cases.py::test_case_003",
    },
]

REQUIRED = ("id", "来源", "用途", "期望结果", "依据", "对应断言")


def main() -> int:
    bad = []
    for c in CASES:
        miss = [k for k in REQUIRED if not str(c.get(k) or "").strip()]
        if miss:
            bad.append(f"{c.get('id')} 缺 {miss}")
    if bad:
        print("案例不合规：", bad)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for c in CASES:
        (OUT / f"{c['id']}.json").write_text(
            json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {len(CASES)} 个案例 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
