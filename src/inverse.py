# -*- coding: utf-8 -*-
"""逆运算：从结果反解参数，并用往返残差自证。

为什么逆运算比正运算危险
  ① **可能无解**：价格低于内在价值时，隐含波动率不存在；
  ② **可能多解**：现金流符号变化多次时，IRR 可能有多个根（笛卡尔符号法则）；
  ③ **可能病态**：接近平价时 vega 极小，隐含波动率对价格极其敏感。
  正运算永远有解且唯一，逆运算三条都可能违反——所以**必须自带失败分支**。

三条逆运算
  ytm_from_price   债务：价格 → 到期收益率
  implied_vol      期权：价格 → 隐含波动率
  irr              现金流：净现值=0 → 内部收益率

往返自证（本模块的核心断言）
  正算 ∘ 反解 = 恒等：残差必须趋于 0，否则说明「正算与反解不是同一套口径」。
  这正是会计线 paired_check 的金融版：两条路径必须给出同一个数。

边界
  ✅ 只做数值反解与往返校验
  ❌ 不判断「这个价格是否合理」——那是市场的事
"""
from __future__ import annotations

import math
from typing import Callable, Sequence


def bisect(f: Callable[[float], float], lo: float, hi: float,
           tol: float = 1e-12, max_iter: int = 200) -> tuple[float | None, int]:
    """二分求根。返回 (根或 None, 迭代次数)。

    用二分而非牛顿：**保证单调区间内必收敛**，且不需要导数。
    代价是慢，但逆运算一共只算几次，慢得起。
    """
    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo, 0
    if fhi == 0:
        return hi, 0
    if flo * fhi > 0:
        return None, 0                     # 区间内无符号变化 ⇒ 不保证有根
    for i in range(1, max_iter + 1):
        mid = (lo + hi) / 2
        fm = f(mid)
        if abs(fm) < tol or (hi - lo) < tol:
            return mid, i
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2, max_iter


def bond_price(face: float, coupon: float, ytm: float, n: int) -> float:
    """正算：债券价格（年付息）。"""
    c = face * coupon
    return sum(c / (1 + ytm) ** t for t in range(1, n + 1)) + face / (1 + ytm) ** n


def ytm_from_price(price: float, face: float, coupon: float,
                   n: int) -> tuple[float | None, str]:
    """逆运算：价格 → 到期收益率。"""
    f = lambda y: bond_price(face, coupon, y, n) - price
    lo, hi = -0.9999, 10.0
    r, it = bisect(f, lo, hi, tol=1e-14)
    if r is None:
        return None, "区间内无符号变化：该价格在利率 ∈ (−1, 10) 内不可达"
    return r, f"二分 {it} 次收敛"


def bs_call(s: float, k: float, t: float, r: float, sigma: float) -> float:
    """正算：欧式看涨（Black-Scholes）。"""
    if t <= 0 or sigma <= 0:
        return max(s - k, 0.0)
    d1 = (math.log(s / k) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    ncdf = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    return s * ncdf(d1) - k * math.exp(-r * t) * ncdf(d2)


def implied_vol(price: float, s: float, k: float, t: float,
                r: float) -> tuple[float | None, str]:
    """逆运算：期权价格 → 隐含波动率。

    三个失败分支必须显式：
      ① 价格低于内在价值 ⇒ 不存在（无解）
      ② 价格高于标的价格 ⇒ 不存在（欧式看涨上界）
      ③ 区间内无符号变化 ⇒ 收敛失败
    """
    intrinsic = max(s - k * math.exp(-r * t), 0.0)
    if price < intrinsic - 1e-12:
        return None, f"价格 {price:.4f} 低于内在价值 {intrinsic:.4f}：隐含波动率不存在"
    if price >= s:
        return None, f"价格 {price:.4f} 不低于标的价格 {s:.4f}：违反无套利上界"
    f = lambda sig: bs_call(s, k, t, r, sig) - price
    r_, it = bisect(f, 1e-6, 5.0, tol=1e-12)
    if r_ is None:
        return None, "区间内无符号变化：收敛失败"
    return r_, f"二分 {it} 次收敛"


def npv(rate: float, flows: Sequence[float]) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(flows))


def irr(flows: Sequence[float]) -> tuple[float | None, str]:
    """逆运算：内部收益率。**必须检查多解**。"""
    if not any(x > 0 for x in flows) or not any(x < 0 for x in flows):
        return None, "现金流全同号：IRR 不存在"
    # 笛卡尔符号法则的上界：符号变化次数
    signs = [1 if x > 0 else -1 for x in flows if x != 0]
    changes = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
    roots = []
    lo, hi = -0.99, 10.0
    step = 0.01
    x = lo
    while x < hi:                          # 扫描找符号变化，逐段求根
        f1, f2 = npv(x, flows), npv(x + step, flows)
        if f1 == 0:
            roots.append(x)
        elif f1 * f2 < 0:
            r_, _ = bisect(lambda y: npv(y, flows), x, x + step, tol=1e-12)
            if r_ is not None:
                roots.append(r_)
        x += step
    # 去重键用 round，但**返回值必须用原值**：
    # 早先直接返回 round(r, 8)，导致 NPV(IRR) = −6.79e-06（不是≈0）。
    seen: dict[float, float] = {}
    for r in roots:
        seen.setdefault(round(r, 8), r)
    uniq = [seen[k] for k in sorted(seen)]
    # 分三种情况，**多解必须拒绝**：挑一个就是猜。
    if len(uniq) == 0:
        return None, "无解：扫描未找到根"
    if len(uniq) == 1:
        return uniq[0], f"唯一解（符号变化 {changes} 次）"
    return None, (f"多解：找到 {len(uniq)} 个根 {[round(r, 6) for r in uniq]}；"
                  f"符号变化 {changes} 次 ⇒ IRR 不唯一，拒绝给出单一数值，交人工/上层判定")


def _selftest() -> int:
    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # ① 债券往返：ytm → price → ytm，残差应≈0
    for ytm in (0.03, 0.06, 0.09):
        p = bond_price(100.0, 0.03, ytm, 5)
        back, msg = ytm_from_price(p, 100.0, 0.03, 5)
        chk(f"ytm 往返 {ytm:.0%}", back is not None and abs(back - ytm) < 1e-9,
            (back, msg))

    # ② 期权往返：sigma → price → sigma
    for sig in (0.15, 0.25, 0.40):
        c = bs_call(12.0, 10.0, 3.0, 0.03, sig)
        back, msg = implied_vol(c, 12.0, 10.0, 3.0, 0.03)
        chk(f"sigma 往返 {sig}", back is not None and abs(back - sig) < 1e-6,
            (back, msg))

    # ③ 期权逆运算的三条失败分支（正运算没有的风险）
    v, why = implied_vol(0.5, 12.0, 10.0, 3.0, 0.03)   # 低于内在价值
    chk("低于内在价值 ⇒ 无解且说明原因", v is None and "不存在" in why, why)
    v2, why2 = implied_vol(13.0, 12.0, 10.0, 3.0, 0.03)  # 高于标的价
    chk("高于标的价格 ⇒ 违反无套利上界", v2 is None and "上界" in why2, why2)

    # ④ IRR：唯一解
    r, msg = irr([-1000.0, 300.0, 350.0, 400.0, 250.0])
    chk("IRR 唯一解", r is not None and abs(npv(r, [-1000.0, 300.0, 350.0, 400.0, 250.0])) < 1e-6,
        (r, msg))
    chk("IRR 的 NPV(IRR)≈0", abs(npv(r, [-1000.0, 300.0, 350.0, 400.0, 250.0])) < 1e-6)

    # ⑤ IRR 多解必须被识别（符号变化多次）
    # 双根例子：[−1000, 2100, −1100] ⇒ 1000x²−2100x+1100=0 ⇒ x=1.1 或 1.0 ⇒ r=10% 或 0%
    flows_multi = [-1000.0, 2100.0, -1100.0]
    rm, msgm = irr(flows_multi)
    chk("IRR 多解被拒绝（不挑一个）", rm is None and "多解" in msgm, (rm, msgm))
    # 两个根都必须确实使 NPV≈0 —— 证明"多解"不是扫描假象
    chk("双根 0% 与 10% 确实都是根",
        abs(npv(0.0, flows_multi)) < 1e-6 and abs(npv(0.10, flows_multi)) < 1e-6,
        (npv(0.0, flows_multi), npv(0.10, flows_multi)))


    # ⑥ 无解：现金流全同号
    none_r, why3 = irr([100.0, 200.0, 300.0])
    chk("全同号现金流 ⇒ IRR 不存在", none_r is None and "不存在" in why3, why3)

    # ⑦ 二分在无符号变化时明确返回 None（不硬给一个数）
    r_none, it = bisect(lambda x: x * x + 1, -1, 1)
    chk("无根区间返回 None（不硬凑）", r_none is None and it == 0, (r_none, it))

    print(f"逆运算自检：{ok} 项通过，{len(fail)} 项失败")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
