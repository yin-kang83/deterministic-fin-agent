# -*- coding: utf-8 -*-
"""新增原子能力断言：截断递推 / 累计曲线 / 递延税滚动 / 分币量化 / 分段累进。

运行：python tests/test_atoms_tax.py
（不依赖 pytest；与 src/*.py 自检风格一致）
"""
from __future__ import annotations

import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

D = Decimal


def main() -> int:
    from recurrence import iterate
    from recurrence_ext import clipped_recurrence, cumulative, deferred_rows
    from tax_atoms import progressive_amount, quantize_cents

    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # ① 累计曲线 = λ=1 递推（与 iterate 一致）
    incs = [D("10"), D("-3"), D("5")]
    chk("累计曲线与 iterate 一致", cumulative(incs) == iterate(1, D("0"), incs),
        (cumulative(incs), iterate(1, 0, incs)))

    # ② 截断递推：不得为负；下限生效
    clipped = clipped_recurrence([D("100"), D("-150"), D("50")], floor=D("0"))
    chk("截断递推下限", clipped == [D("100"), D("0"), D("50")], clipped)

    # ③ 递延税滚动：DT = τ·G，含税率变动
    rows = deferred_rows([D("100"), D("-40"), D("60")], [D("0.25"), D("0.25"), D("0.15")])
    dts = [r["DT"] for r in rows]
    chk("递延税 DT 序列", dts == [D("25.00"), D("15.00"), D("18.00")], dts)

    # ④ 分币量化：HALF_UP；拒绝 float
    chk("量化 0.015→0.02", quantize_cents("0.015") == D("0.02"), quantize_cents("0.015"))
    chk("量化 0.014→0.01", quantize_cents("0.014") == D("0.01"), quantize_cents("0.014"))
    try:
        quantize_cents(0.1)
        chk("拒绝 float", False, "未抛 TypeError")
    except TypeError:
        chk("拒绝 float", True)

    # ⑤ 分段累进：个税七级表（示例参数）
    tiers = [
        (36000, "0.03", 0), (144000, "0.10", 2520), (300000, "0.20", 16920),
        (420000, "0.25", 31920), (660000, "0.30", 52920), (960000, "0.35", 85920),
        (10**30, "0.45", 181920),
    ]
    chk("累进 0→0", progressive_amount(tiers, 0) == D("0.00"), progressive_amount(tiers, 0))
    chk("累进 36000→1080", progressive_amount(tiers, 36000) == D("1080.00"), progressive_amount(tiers, 36000))
    chk("累进 500000→97080", progressive_amount(tiers, 500000) == D("97080.00"), progressive_amount(tiers, 500000))

    print(f"== 原子能力断言：{ok} pass / {len(fail)} fail ==")
    for f in fail:
        print("  FAIL", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
