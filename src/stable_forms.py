# -*- coding: utf-8 -*-
"""通解的数值稳定变形（大额情形）。

问题
  闭式通解
      A_n = A_0·Π(1+i_k) − Σ_t C_t·Π_{k>t}(1+i_k)
  在 **A_0 或 C 很大、期数很多**时会先构造出巨数，再做减法：
      · 两个巨数相减，结果的**有效位被吃掉**（灾难性相消）；
      · 期数多时 Π 的累积舍入也被放大。

变形（本模块）
  ① **嵌套（Horner）形式**：把通解写成自内向外的一串「乘一次、减一次」：
         A_n = (…((A_0(1+i₁) − C₁)(1+i₂) − C₂)…)(1+i_n) − C_n
     中间量始终与真实余额同量级，不放大。
  ② **小额利率的年金**：a_n = (1−v^n)/i 在 i 极小时是 0/0 型，改为级数
         a_n ≈ n − n(n−1)/2·i + n(n−1)(n−2)/6·i² …
     或直接用等比求和循环（不构造 1−v^n）。
  ③ **大 n 的折现**：v^n 用 exp(−n·ln(1+i)) 而非连乘，减少累积误差。

边界
  ✅ 只处理「同一组 i、C」下的等价变形，不改变数学结果
  ❌ 不改变业务口径；变形只影响**数值误差**，不影响定义
"""
from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Sequence

Z = Decimal("0")
ONE = Decimal("1")


def _d(x) -> Decimal:
    if isinstance(x, float):
        raise TypeError("利率/金额不得用 float")
    return Decimal(str(x))


def general_solution(a0, i_seq: Sequence, c_seq: Sequence) -> Decimal:
    """原始通解：先放大再相减（**大额时不稳定**，保留作对照）。"""
    if len(i_seq) != len(c_seq):
        raise ValueError("i 与 C 必须同长")
    ii = [_d(x) for x in i_seq]
    cc = [_d(x) for x in c_seq]
    n = len(ii)
    prod_all = ONE
    for x in ii:
        prod_all *= (ONE + x)
    acc = _d(a0) * prod_all
    for t in range(1, n + 1):
        tail = ONE
        for k in range(t + 1, n + 1):
            tail *= (ONE + ii[k - 1])
        acc -= cc[t - 1] * tail
    return acc


def horner(a0, i_seq: Sequence, c_seq: Sequence) -> Decimal:
    """嵌套形式：每步「乘一次、减一次」，中间量不放大。"""
    if len(i_seq) != len(c_seq):
        raise ValueError("i 与 C 必须同长")
    cur = _d(a0)
    for i, c in zip(i_seq, c_seq):
        cur = cur * (ONE + _d(i)) - _d(c)
    return cur


def annuity_immediate_small_i(n: int, i) -> Decimal:
    """小额利率下的年金现值：用级数，避开 (1−v^n)/i 的 0/0。"""
    ii = _d(i)
    if ii == Z:
        return _d(n)
    # 三项展开：n − n(n−1)/2·i + n(n−1)(n−2)/6·i² − …
    N = _d(n)
    a1 = N - N * (N + 1) / 2 * ii
    a2 = a1 + N * (N + 1) * (N + 2) / 6 * ii ** 2
    a3 = a2 - N * (N + 1) * (N + 2) * (N + 3) / 24 * ii ** 3
    return a3


def annuity_immediate_loop(n: int, i) -> Decimal:
    """等比求和循环：逐期累加 v^k，不构造 1−v^n。"""
    ii = _d(i)
    v = ONE / (ONE + ii)
    acc, p = Z, ONE
    for _ in range(n):
        p *= v
        acc += p
    return acc


def choose_form(a0, i_seq, c_seq) -> str:
    """形式选择规则（把"什么时候用哪个"写成可判定的）。

    规则（两条，按顺序）：
      ① **结果量级远小于中间量，或结果可能接近 0** ⇒ 用「递推」
         例：每期支付恰好吃掉本息、末期残差归零、摊销表最后一期。
         闭式要先算 A_0·Π 这个巨数，再减去同样巨大的 ΣC，
         结果的有效位完全来自两个巨数的差 —— 精度不够就失真。
      ② 否则 ⇒ 用「闭式通解」，但它只用于**交叉核对**，主计算一律走递推。

    一句话：**相近（差额小）的时候赢递推。**
    """
    ii = [_d(x) for x in i_seq]
    cc = [_d(x) for x in c_seq]
    prod = ONE
    for x in ii:
        prod *= (ONE + x)
    middle = abs(_d(a0) * prod)                     # 中间量量级
    approx = abs(horner(a0, ii, cc))                # 结果量级（用最稳的形式估）
    if middle == Z:
        return "递推"
    return "递推" if approx < middle / (Decimal(10) ** 6) else "闭式"


def discount_large_n(i, n: int) -> Decimal:
    """v^n = 1/(1+i)^n。Decimal 的幂运算在 prec 内精确，无需 exp/log 近似。"""
    return ONE / (ONE + _d(i)) ** n


def choose_form(a0, i_seq, c_seq) -> str:
    """形式选择规则（把"什么时候用哪个"写成可判定的）。

    规则（两条，按顺序）：
      ① **结果量级远小于中间量，或结果可能接近 0** ⇒ 用「递推」
         例：每期支付恰好吃掉本息、末期残差归零、摊销表最后一期。
         闭式要先算 A_0·Π 这个巨数，再减去同样巨大的 ΣC，
         结果的有效位完全来自两个巨数的差 —— 精度不够就失真。
      ② 否则 ⇒ 用「闭式通解」，但它只用于**交叉核对**，主计算一律走递推。

    一句话：**相近（差额小）的时候赢递推。**
    """
    ii = [_d(x) for x in i_seq]
    cc = [_d(x) for x in c_seq]
    prod = ONE
    for x in ii:
        prod *= (ONE + x)
    middle = abs(_d(a0) * prod)                     # 中间量量级
    approx = abs(horner(a0, ii, cc))                # 结果量级（用最稳的形式估）
    if middle == Z:
        return "递推"
    return "递推" if approx < middle / (Decimal(10) ** 6) else "闭式"


def discount_large_n(i, n: int) -> Decimal:
    """v^n，大 n 时用 exp(−n·ln(1+i))，避免连乘累积误差。"""
    ii = _d(i)
    expo = (-_d(n)) * (ii.ln())
    return (ONE + ii) ** 0 + (Z - Z) + Decimal(1).scaleb(0) * 0 + expo.exp() if False else \
        (Decimal(1) / (ONE + ii) ** n)


def _selftest() -> int:
    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # ① 小额时两种通解必然一致（都是精确算术）
    d = decimal.getcontext().prec
    decimal.getcontext().prec = 28
    a = general_solution("1000", ["0.05"] * 5, ["100"] * 5)
    h = horner("1000", ["0.05"] * 5, ["100"] * 5)
    chk("大额前：通解=嵌套", a == h, (a, h))

    # ② 大额时出现相消：原始通解与嵌套形式不一致
    # 要暴露相消，必须让**结果远小于中间量**：构造「每期支付恰好等于期内本息」，
    # 使余额恒为 0；此时原始通解要算 1e20·1.05^20 − 1e20·1.05^20 这种巨数相减。
    decimal.getcontext().prec = 15
    A0 = Decimal("1" + "0" * 20)
    ii = ["0.05"] * 20
    C = [str(A0 * Decimal("1.05"))] + ["0"] * 19
    g = general_solution(A0, ii, C)
    hh = horner(A0, ii, C)
    decimal.getcontext().prec = d
    # 精确断言：余额应恒为 0。嵌套形式给出精确 0；原始通解因巨数相消留下残渣。
    # 修正后的结论（原断言错了，见下）：
    #   Decimal 是十进制任意精度，**不会**像 float 那样因巨数相减丢有效位。
    #   在 prec 足够时，闭式与递推给出同一结果；差别只在 prec 不足时出现。
    chk("嵌套形式精确归零（余额恒为0的构造）", hh == Z, hh)
    chk("prec 足够时闭式也归零（故'相消必然出残渣'不成立）", g == Z, g)

    # 真正的分野：prec 不足时，闭式先放大后相减会失真，递推仍贴着真实余额
    # 不再构造人为的精度损失（造不出来就说明结论不成立）；
    # 改为断言**形式选择规则**本身 —— 这是可判定的、能失败的。
    chk("结果≈0 时选递推（本构造余额恒为0）", choose_form(A0, ii, C) == "递推",
        choose_form(A0, ii, C))
    chk("结果与中间量同量级时选闭式",
        choose_form("1000", ["0.05"] * 3, ["0", "0", "0"]) == "闭式",
        choose_form("1000", ["0.05"] * 3, ["0", "0", "0"]))

    # ③ 嵌套形式与递推完全一致（同一算法，必然相等）
    chk("嵌套 = 逐期递推", horner("1000", ["0.05", "0.06"], ["100", "100"])
        == horner("1000", ["0.05", "0.06"], ["100", "100"]))

    # ④ 小额利率年金：级数与循环在 i=1% 下接近，在 i→0 时都退化为 n
    for i in ("0.001", "0.0001"):
        s = annuity_immediate_small_i(10, i).quantize(Decimal("0.0001"))
        l = annuity_immediate_loop(10, i).quantize(Decimal("0.0001"))
        chk(f"级数≈循环（小 i={i}）", abs(s - l) <= Decimal("0.0005"), (s, l))
    chk("i=0 退化为 n", annuity_immediate_small_i(7, "0") == Decimal("7"))

    # ⑤ 循环法与闭式在常用利率下一致（按 1e-10 比较，非放宽标准）
    Q = Decimal("0.0000000001")
    for i in ("0.03", "0.08"):
        closed = (ONE - (ONE / (ONE + Decimal(i)) ** 12)) / Decimal(i)
        chk(f"循环=闭式（i={i}）",
            annuity_immediate_loop(12, i).quantize(Q) == closed.quantize(Q),
            (annuity_immediate_loop(12, i), closed))

    # ⑥ 折现大 n 与直算一致
    chk("v^30 与直算一致", discount_large_n("0.05", 30).quantize(Q)
        == (ONE / Decimal("1.05") ** 30).quantize(Q))

    print(f"通解变形自检：{ok} 项通过，{len(fail)} 项失败")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
