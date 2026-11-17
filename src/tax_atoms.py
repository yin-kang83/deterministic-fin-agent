# -*- coding: utf-8 -*-
"""自有原子引擎扩展（税务算术）：分币量化 + 累进税率映射。

为什么需要补齐：
- 原引擎（recurrence/stable_forms/actuarial）覆盖「一阶递推、闭式解、年金、数值稳定」；
- 但税务算术还缺两类通用原子：
  ① 分位量化（金额按分四舍五入，避免浮点/长尾）；
  ② 累进税率映射（分段线性 + 速算扣除数；个税/企税等均用）。
本文件把这两类补进自有引擎谱系（可后续回移至「确定性业财智能体/src」与移植台账）。

仅算术，不含法律适用判断。
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

CENT = Decimal("0.01")
Z = Decimal("0")


def quantize_cents(x) -> Decimal:
    """按分四舍五入（拒绝 float，原则同引擎 _d）。"""
    if isinstance(x, float):
        raise TypeError("金额不得用 float")
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def progressive_amount(tiers: Sequence, taxable) -> Decimal:
    """累进税率：tiers = [(upper_bound, rate, quick_deduction), ...]，返回税额（分）。

    - taxable <= 0 → 0；
    - 段内：tax = taxable * rate - quick_deduction；
    - 边界口径：<= upper 归该段（与个税预扣率表口径一致）。
    """
    t = max(Z, quantize_cents(taxable))
    for upper, rate, quick in tiers:
        if t <= Decimal(str(upper)):
            return quantize_cents(t * Decimal(str(rate)) - Decimal(str(quick)))
    upper, rate, quick = tiers[-1]
    return quantize_cents(t * Decimal(str(rate)) - Decimal(str(quick)))
