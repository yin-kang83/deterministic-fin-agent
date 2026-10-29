# -*- coding: utf-8 -*-
"""生成并校验 knowledge/ 元知识库（与代码分离）。

为什么要单独一层
  代码是「怎么算」，知识是「算什么、什么不许算」。两者变更频率不同：
    · 引擎半年不动；规则随监管变，一季度就可能改。
  混在一起会互相拖累——改一条阈值要动代码文件，改一次算法要过知识评审。
  所以：**代码在 src/，知识在 knowledge/，校验器在 scripts/。**

目录约定（三层，对应元知识的三个来源）
  knowledge/compliance/   合规与风控（监管条文、阈值、红线）
  knowledge/valuation/    估值（模型选择与参数约束）
  knowledge/tax/          税务与会计处理

每条卡必须有的字段（缺一个就拒收）
  card_id / 版本 / 来源 / priority / 输入 / 规则
  规则里的「条件」必须是**结构化比较树**，不许是字符串——
  字符串条件要靠 eval 或自造解析器，前者不安全，后者易错。
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge"
sys.path.insert(0, str(ROOT / "src"))

from card_eval import validate_card  # noqa: E402

CARDS = {
    "compliance/merger_risk.json": {
        "card_id": "FIN_RISK_MERGER_001",
        "版本": "1.0",
        "来源": "《商业银行并购贷款风险管理指引》（示例，阈值需以原文核对）",
        "priority": 1,
        "输入": {
            "负债率_百分比": {"类型": "数量", "单位": "百分数（80 表示 80%）",
                          "必填": True},
            "现金流": {"类型": "金额", "必填": True},
            "行业": {"类型": "文本", "必填": True},
        },
        "规则": [
            {"rule_id": "R1",
             "条件": {"op": ">", "left": {"var": "负债率_百分比"},
                    "right": {"num": 80}},
             "动作": "FAIL_CLOSED",
             "消息": "标的方负债率超 80%，触发风控熔断"},
            {"rule_id": "R2",
             "条件": {"and": [
                 {"op": "<", "left": {"var": "现金流"}, "right": {"num": 0}},
                 {"op": "==", "left": {"var": "行业"}, "right": {"str": "高污染"}}]},
             "动作": "FAIL_CLOSED",
             "消息": "高污染行业且现金流为负，双重不达标"},
        ],
    },
    "valuation/enterprise_dcf.json": {
        "card_id": "FIN_VAL_DCF_001",
        "版本": "1.0",
        "来源": "DCF 通行做法（非准则条文）；g < WACC 为永续增长项的存在条件",
        "priority": 5,
        "输入": {
            "WACC": {"类型": "比率", "必填": True},
            "永续增长率": {"类型": "比率", "必填": True},
            "自由现金流": {"类型": "列表", "必填": True},
        },
        "规则": [
            {"rule_id": "R1",
             "条件": {"op": ">=", "left": {"var": "永续增长率"},
                    "right": {"var": "WACC"}},
             "动作": "FAIL_CLOSED",
             "消息": "永续增长率 ≥ WACC：永续增长项无意义（分母 ≤ 0），拒绝计算"},
        ],
    },
    "tax/deferred_tax_basic.json": {
        "card_id": "FIN_TAX_DTA_001",
        "版本": "1.0",
        "来源": "CAS 18（所得税）：递延所得税资产以「很可能取得足够应纳税所得额」为确认前提",
        "priority": 3,
        "输入": {
            "很可能取得足够应纳税所得额": {"类型": "开关", "必填": True},
            "可抵扣暂时性差异": {"类型": "金额", "必填": True},
        },
        "规则": [
            {"rule_id": "R1",
             "条件": {"op": "==", "left": {"var": "很可能取得足够应纳税所得额"},
                    "right": {"bool": False}},
             "动作": "FAIL_CLOSED",
             "消息": "无足够应纳税所得额的证据：不得确认递延所得税资产（谨慎性）"},
        ],
    },
}


def main() -> int:
    bad = []
    for rel, card in CARDS.items():
        probs = validate_card(card)
        if probs:
            bad.append(f"{rel}: {probs}")
            continue
        p = KB / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  写入 {rel}（{card['card_id']}，priority={card['priority']}）")
    if bad:
        print("不合规：", bad)
        return 1
    print(f"共 {len(CARDS)} 张卡，全部通过结构校验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
