# -*- coding: utf-8 -*-
"""精算形式的递推（最严格形式）。

与 recurrence.py 的区别
  recurrence.py 用常系数 λ 刻画「维持/自驱动/耗散」，适合讲业务直觉；
  但**精算上更严格**的形式不用 λ，而是显式写出利率、时点与支付时点：

      A_t = A_{t−1}·(1 + i_t) − C_t        t = 1..n，i_t 逐期可变

  通解（可验证，不是只有递推）：
      A_n = A_0·Π_{k=1..n}(1+i_k) − Σ_{t=1..n} C_t·Π_{k=t+1..n}(1+i_k)

  即：每笔支付 C_t 按「支付之后到第 n 期」的利率累积扣除。

三个必须显式声明的约定（精算的严格性就在这三条）
  ① 时点：A_0 是**第 0 期末**（即第 1 期初）余额；
  ② 支付时点：`timing="期末"` 时支付发生在每期期末，先计息后扣款；
     `timing="期初"` 时先扣款后计息（年金的 due / immediate 之别）；
  ③ i_t 与 C_t 必须**同长且逐期对齐**，缺一期即报错（不许静默截断）。

边界
  ✅ 只做确定性的利息与支付递推
  ❌ 不含生存概率（生存年金需叠加 p_x，属另一层）；不含税率
"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

Z = Decimal("0")
ONE = Decimal("1")


def _d(x) -> Decimal:
    if isinstance(x, float):
        raise TypeError("利率/金额不得用 float（二进制误差）")
    return Decimal(str(x))


def v_factor(i, t: int) -> Decimal:
    """折现因子 v^t = 1/(1+i)^t。"""
    return ONE / ((ONE + _d(i)) ** t)


def annuity_immediate(n: int, i) -> Decimal:
    """期末年金现值 a_n = (1 − v^n)/i。"""
    i = _d(i)
    if i == Z:
        return _d(n)
    return (ONE - v_factor(i, n)) / i


def annuity_due(n: int, i) -> Decimal:
    """期初年金现值 ä_n = a_n·(1+i) = 1 + a_{n−1}。"""
    return annuity_immediate(n, i) * (ONE + _d(i))


def accumulate(a0, i_seq: Sequence, c_seq: Sequence, timing: str = "期末") -> list[Decimal]:
    """严格递推：逐期计息与支付，返回每期期末余额。"""
    if len(i_seq) != len(c_seq):
        raise ValueError(f"i 与 C 必须同长：{len(i_seq)} vs {len(c_seq)}")
    if timing not in ("期末", "期初"):
        raise ValueError("timing 只能是 期末 / 期初")
    cur = _d(a0)
    out = []
    for i, c in zip(i_seq, c_seq):
        if timing == "期末":
            cur = cur * (ONE + _d(i)) - _d(c)      # 先计息，后扣款
        else:
            cur = (cur - _d(c)) * (ONE + _d(i))    # 先扣款，后计息
        out.append(cur)
    return out


def general_solution(a0, i_seq: Sequence, c_seq: Sequence) -> Decimal:
    """通解（期末支付）：A_n = A_0·Π(1+i_k) − Σ C_t·Π_{k=t+1..n}(1+i_k)。"""
    if len(i_seq) != len(c_seq):
        raise ValueError("i 与 C 必须同长")
    ii = [_d(x) for x in i_seq]
    cc = [_d(x) for x in c_seq]
    n = len(ii)
    prod_all = ONE
    for x in ii:
        prod_all *= (ONE + x)
    acc = _d(a0) * prod_all
    for t in range(1, n + 1):                     # t 从 1 计
        tail = ONE
        for k in range(t + 1, n + 1):
            tail *= (ONE + ii[k - 1])
        acc -= cc[t - 1] * tail
    return acc


def _selftest() -> int:
    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # ① 通解 = 递推（残差精确为 0）
    a = accumulate("1000", ["0.05", "0.06", "0.04"], ["100", "100", "100"])
    gs = general_solution("1000", ["0.05", "0.06", "0.04"], ["100", "100", "100"])
    chk("通解=递推（残差0）", a[-1] == gs, (a[-1], gs))
    chk("三期余额可手算核对",
        a == [Decimal("950.000"), Decimal("907.0000"), Decimal("843.28000")], a)

    # ② 变利率 ≠ 常利率（证明 i_t 不可换成平均利率）
    avg = accumulate("1000", ["0.05"] * 3, ["100"] * 3)[-1]
    chk("变利率与平均利率结果不同", a[-1] != avg, (a[-1], avg))

    # ③ 期末 vs 期初：同一组参数差一个 (1+i) 于首期
    due = accumulate("1000", ["0.05"], ["100"], timing="期初")
    end = accumulate("1000", ["0.05"], ["100"], timing="期末")
    chk("期初/期末不同", due[0] != end[0], (due[0], end[0]))
    chk("期初 = (1000−100)×1.05", due[0] == Decimal("945.000"), due[0])
    chk("期末 = 1000×1.05−100", end[0] == Decimal("950.000"), end[0])

    # ④ 年金恒等式：ä_n = a_n·(1+i) = 1 + a_{n−1}
    for n in (1, 5, 10):
        QQ = Decimal("0.0000000001")
        chk(f"ä_{n} = a_{n}·(1+i)",
            annuity_due(n, "0.05").quantize(QQ)
            == (annuity_immediate(n, "0.05") * Decimal("1.05")).quantize(QQ))
    # 恒等式在数学上相等，但 Decimal 除法是有限位——末位会差。
    # 这里不是放宽标准，是**按有效位数比较**：先量化到 1e-10 再判严格相等。
    Q = Decimal("0.0000000001")
    chk("ä_5 = 1 + a_4（量化到 1e-10 后严格相等）",
        annuity_due(5, "0.05").quantize(Q) == (ONE + annuity_immediate(4, "0.05")).quantize(Q),
        (annuity_due(5, "0.05"), ONE + annuity_immediate(4, "0.05")))
    chk("a_10(5%) ≈ 7.7217", annuity_immediate(10, "0.05").quantize(Decimal("0.0001")) == Decimal("7.7217"),
        annuity_immediate(10, "0.05"))

    # ⑤ 折现因子：v^0=1，v^1=1/(1+i)
    chk("v^0 = 1", v_factor("0.05", 0) == ONE)
    chk("v^1 = 1/1.05", v_factor("0.05", 1) == ONE / Decimal("1.05"))

    # ⑥ 期数不对齐必须报错（不许静默截断）
    try:
        accumulate("1000", ["0.05", "0.06"], ["100"])
        chk("期数不对齐报错", False, "未报")
    except ValueError:
        chk("期数不对齐报错", True)

    # ⑦ 零利率退化：纯现金流
    chk("i=0 时 a_n = n", annuity_immediate(7, "0") == Decimal("7"))
    chk("i=0 时余额 = 本金 − 累计支付",
        accumulate("1000", ["0"] * 3, ["100"] * 3)[-1] == Decimal("700"))

    # ⑧ 金额纪律
    try:
        accumulate(1000.0, ["0.05"], ["100"])
        chk("float 初值被拒", False, "未拒")
    except TypeError:
        chk("float 初值被拒", True)

    print(f"精算递推自检：{ok} 项通过，{len(fail)} 项失败")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
