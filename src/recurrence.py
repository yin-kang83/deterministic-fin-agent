# -*- coding: utf-8 -*-
"""一阶递推（差分方程）的四种形式与收敛判据。

论文的核心命题
  会计与金融的价值演化可写成  A_t = λ·A_{t-1} + θ_t
  λ 的取值决定业务性质：
    λ = 1        维持（如应收账款滚动：本期余额 = 上期 + 新增 − 收回）
    λ = 1 + r    自驱动（摊余成本：按实际利率生息，负债越滚越大）
    λ = 1 − p    耗散（折旧/摊销：按比率递减）

  但**并非所有折旧方法都有常数 λ**——这是本模块要证伪的一条常见误解。

四种形式
  ① 常系数标量      A_t = λ A_{t-1} + θ_t              （有闭式解，可与迭代互验）
  ② 变系数标量      A_t = λ_t A_{t-1} + θ_t            （年数总和法、双倍余额递减）
  ③ 矩阵形式        A_t = M A_{t-1} + b                （多链并存：租赁 + 税会差异）
  ④ 无递推          A_t 直接由用量决定                  （工作量法：不存在 A_{t-1} 项）

收敛判据
  |λ| < 1 收敛到 A* = θ/(1−λ)；λ = 1 线性增长；|λ| > 1 发散（除 θ 反号且初值为负）。

边界
  ✅ 本模块只做算术与形式判定
  ❌ 不判断「某业务该用哪种形式」——那是定性环节
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable, Sequence

Z = Decimal("0")


def _d(x) -> Decimal:
    if isinstance(x, float):
        raise TypeError("金额/余额不得用 float")
    return Decimal(str(x))


def closed_form(lam, a0, thetas: Sequence) -> list[Decimal]:
    """常系数形式的闭式解：A_t = λ^t·A0 + Σ_{k=1..t} λ^{t−k}·θ_k。"""
    L, A = _d(lam), _d(a0)
    out, acc = [], A
    for t, th in enumerate(thetas, 1):
        acc = (L ** t) * A + sum((L ** (t - k)) * _d(thetas[k - 1]) for k in range(1, t + 1))
        out.append(acc)
    return out


def iterate(lam, a0, thetas: Sequence) -> list[Decimal]:
    """逐步迭代（与闭式解应完全一致，残差 0）。"""
    L, cur = _d(lam), _d(a0)
    out = []
    for th in thetas:
        cur = L * cur + _d(th)
        out.append(cur)
    return out


def variable_lambda(lams: Sequence, a0, thetas: Sequence) -> list[Decimal]:
    """变系数：A_t = λ_t·A_{t−1} + θ_t。"""
    cur, out = _d(a0), []
    for L, th in zip(lams, thetas):
        cur = _d(L) * cur + _d(th)
        out.append(cur)
    return out


def matrix_form(M: Sequence[Sequence], a0: Sequence, bs: Sequence[Sequence]) -> list[list[Decimal]]:
    """矩阵形式：A_t = M·A_{t−1} + b_t（多链并存）。"""
    n = len(a0)
    cur = [_d(x) for x in a0]
    out = []
    for b in bs:
        cur = [sum(_d(M[i][j]) * cur[j] for j in range(n)) + _d(b[i]) for i in range(n)]
        out.append(list(cur))
    return out


def pure_ratio_lambda(series: Sequence) -> tuple[bool, Decimal | None]:
    """判定是否存在常数 λ 使**纯比例形式** A_t = λ·A_{t−1} 成立（即无加项 θ=0）。

    ⚠ 为什么必须限定「纯比例」
      若允许任意加项 θ_t，则**任何序列**都能写成 λ=1、θ_t=A_t−A_{t−1}——
      那样「有没有常数 λ」就恒为真，命题失去意义。
      会计上的真正区别是：
        · 折旧/摊销（按比率递减）  ⇒ 纯比例形式成立，λ = 1 − p
        · 直线法（折旧额恒定）      ⇒ **纯比例形式不成立**（差额恒定、比值不恒定）
"""
    s = [_d(x) for x in series]
    if len(s) < 3 or any(x == Z for x in s[:-1]):
        return False, None
    ratios = [s[i] / s[i - 1] for i in range(1, len(s))]
    first = ratios[0]
    if all(r == first for r in ratios):
        return True, first
    return False, None


def straight_line(cost, salvage, n: int) -> list[Decimal]:
    """直线法：每期折旧额恒定（余额构成等差数列）。"""
    c, s = _d(cost), _d(salvage)
    d = (c - s) / _d(n)
    return [c - d * _d(t) for t in range(1, n + 1)]


def sum_of_years_digits(cost, salvage, n: int) -> list[Decimal]:
    """年数总和法：折旧额按 n, n−1, …, 1 的比例递减（余额差分非等比）。"""
    c, s = _d(cost), _d(salvage)
    base = c - s
    total = _d(n * (n + 1) // 2)
    cur, out = c, []
    for t in range(1, n + 1):
        cur -= base * _d(n - t + 1) / total
        out.append(cur)
    return out


def amortized_cost(principal, rate, periods: int, payment=Z) -> list[Decimal]:
    """摊余成本：λ = 1 + r（自驱动/耗散由现金流方向决定）。"""
    return iterate(Decimal("1") + _d(rate), principal, [-_d(payment)] * periods)


def _selftest() -> int:
    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # ① λ=1 维持：A0=0，每期 +100，五期 ⇒ 100..500
    a = iterate("1", "0", ["100"] * 5)
    chk("λ=1 维持（等额累加）", [str(x) for x in a] == ["100", "200", "300", "400", "500"], a)

    # ② λ=1+r 自驱动：1000 本金、10%，无现金流
    b = amortized_cost("1000", "0.1", 3)
    chk("λ=1+r 自驱动（复利）", [str(x.quantize(Decimal('0.01'))) for x in b]
        == ["1100.00", "1210.00", "1331.00"], b)

    # ③ λ=1−p 耗散：1000，每期 10%
    c = iterate("0.9", "1000", ["0", "0", "0"])
    chk("λ=1−p 耗散（等比递减）",
        [str(x.quantize(Decimal('0.01'))) for x in c] == ["900.00", "810.00", "729.00"], c)

    # ④ 闭式解 与 迭代 完全一致（残差 0，不是"接近"）
    th = ["100", "-50", "30", "20", "-10"]
    chk("闭式解=迭代（残差0）", closed_form("0.8", "1000", th) == iterate("0.8", "1000", th),
        (closed_form("0.8", "1000", th), iterate("0.8", "1000", th)))

    # ⑤ 收敛判据
    chk("|λ|<1 收敛", abs(Decimal("0.8")) < 1)
    chk("λ=1 不收敛（线性增长）", iterate("1", "0", ["10"] * 3)[-1] == Decimal("30"))

    # ⑥ 直线法**不存在常数 λ**（这是要证伪的常见误解）
    sl = straight_line("1100", "100", 5)
    has_l, lam = pure_ratio_lambda([Decimal("1100")] + sl)
    chk("直线法无纯比例常数 λ", has_l is False, (has_l, lam, sl))
    # 但它确实可写成 λ=1、θ=常数 —— 这条区别必须显式断言，否则命题不严谨
    chk("直线法可写成 λ=1 且 θ 恒定",
        iterate("1", "1100", ["-200"] * 5)[-1] == Decimal("100"), None)
    # 对照：等比递减**存在**常数 λ
    geo = iterate("0.9", "1000", ["0", "0", "0", "0"])
    has_g, lam_g = pure_ratio_lambda([Decimal("1000")] + geo)
    chk("等比递减有常数 λ=0.9", has_g and lam_g == Decimal("0.9"), (has_g, lam_g))

    # ⑦ 年数总和法：变系数，且也非等比
    syd = sum_of_years_digits("1100", "100", 5)
    chk("年数总和法余额递减", syd[-1] == Decimal("100"), syd)
    chk("年数总和法非等比（无纯比例λ）", pure_ratio_lambda([Decimal("1100")] + syd)[0] is False)

    # ⑧ 矩阵形式：两链互不影响
    M = [[Decimal("1.04"), Z], [Z, Decimal("0.9")]]      # 链1自驱动、链2耗散
    out = matrix_form(M, ["100", "100"], [["0", "0"], ["0", "0"]])
    chk("矩阵链1自驱动", out[0][0] == Decimal("104.00"), out[0][0])
    chk("矩阵链2耗散", out[0][1] == Decimal("90.0"), out[0][1])
    chk("两链互不影响", out[1][0] == Decimal("108.1600") and out[1][1] == Decimal("81.00"), out[1])

    # ⑨ 变量系数：λ 逐年变化
    v = variable_lambda(["0.5", "0.25"], "100", ["0", "0"])
    chk("变系数递推", v == [Decimal("50.0"), Decimal("12.500")], v)

    # ⑩ 金额纪律
    try:
        iterate(0.9, "100", ["0"])
        chk("lambda 不得为 float", False, "未拒")
    except TypeError:
        chk("lambda 不得为 float", True)

    print(f"差分方程自检：{ok} 项通过，{len(fail)} 项失败")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
