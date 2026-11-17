# -*- coding: utf-8 -*-
"""自有原子引擎扩展：税务递推所需的曲线/截断/递延税滚动。

依赖同目录 `recurrence.py`（自有移植副本，康正原子引擎谱系）。
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Sequence

from recurrence import _d, iterate

Z = Decimal("0")
CENT = Decimal("0.01")


def _money(x) -> Decimal:
    return _d(x).quantize(CENT, rounding=ROUND_HALF_UP)


def cumulative(increments: Iterable) -> list[Decimal]:
    """λ=1 的累计曲线：S_t = S_{t-1} + x_t（用自有引擎的 iterate 实现）。"""
    return iterate(1, Z, [_money(x) for x in increments])


def clipped_recurrence(
    increments: Iterable,
    opening=Z,
    floor=Z,
    ceiling: Decimal | None = None,
) -> list[Decimal]:
    """截断递推：A_t = max(floor, A_{t-1} + x_t)，可选上界（如留抵退税上限）。

    说明：截断不是线性算子，不能用一次 iterate 表达；本实现逐步调用引擎的
    标量递推语义（λ=1、θ=x_t），再应用截断，保证与引擎口径一致。
    """
    cur = _money(opening)
    out = []
    for x in increments:
        cur = _d(1) * cur + _money(x)
        if floor is not None and cur < floor:
            cur = floor
        if ceiling is not None and cur > ceiling:
            cur = ceiling
        out.append(cur)
    return out


def deferred_rows(
    differences: Sequence,
    rates: Sequence,
    opening_difference=Z,
) -> list[dict]:
    """递延税滚动：G_t = G_{t-1} + ΔG_t（自有引擎累计）；DT_t = τ_t·G_t。"""
    if len(differences) != len(rates):
        raise ValueError("differences 与 rates 期间数不一致")
    g_curve = cumulative(differences)  # 注意：这里以 opening=0 的增量累计
    opening = _money(opening_difference)
    rows = []
    g_prev = opening
    dt_prev = _money(_d(rates[0]) * g_prev) if rates else Z
    for i, (delta, tau) in enumerate(zip(differences, rates)):
        d = _money(delta)
        g = _money(g_prev + d)
        dt = _money(_d(tau) * g)
        rows.append({
            "G_prev": g_prev,
            "delta_G": d,
            "G": g,
            "tau": _d(tau),
            "DT": dt,
            "delta_DT": _money(dt - dt_prev),
        })
        g_prev, dt_prev = g, dt
    return rows
