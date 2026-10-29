# -*- coding: utf-8 -*-
"""三任务演示：定价（客观）→ 估价（主观受约束）→ 决策（阈值拦截）。

为什么要有这个脚本
  「跑一下截个图」不能作为证据：截图不能复核、不能回归、不能证伪。
  本脚本把三个任务的**输入、中间量、判定、依据**全部打印出来，
  每一行都能被人拿计算器重算——这才是可以进论文的运行结果。

三段的本质区别（这是方法论，不是代码）
  定价  objective   时间线递推；对错由**往返残差**判定（正算∘反解 = 恒等）
  估价  subjective  空间归一化；对错由**参数约束**判定（g < WACC 才存在永续项）
  决策  threshold   阈值比对；对错由**引用是否可溯**判定（市价必须说明来源）

边界（必写在输出里，免得被当成投资建议）
  · 估价用的是构造假设，不是对真实公司的判断；
  · 决策部分的市价是**参数**，不由本脚本决定；没有真实来源时输出即不可用于交易。
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from inverse import bs_call, implied_vol          # noqa: E402


def 定价(s, k, t, r, sigma) -> dict:
    """任务一：定价。客观，用往返残差自证。"""
    price = bs_call(s, k, t, r, sigma)
    back, msg = implied_vol(price, s, k, t, r)
    residual = abs(back - sigma) if back is not None else None
    return {"任务": "定价", "标的": s, "行权": k, "期限": t, "无风险利率": r,
            "波动率": sigma, "理论价格": round(price, 6),
            "反解波动率": round(back, 10) if back is not None else None,
            "往返残差": f"{residual:.2e}" if residual is not None else msg,
            "判定": "PASS" if (residual is not None and residual < 1e-9) else "FAIL_CLOSED",
            "依据": "无套利；残差不为 0 说明正算与反解不是同一套口径"}


def 估价(fcf: list[float], wacc: float, g: float) -> dict:
    """任务二：估价。主观，但参数受约束：g 必须 < WACC。"""
    if g >= wacc:
        return {"任务": "估价", "判定": "FAIL_CLOSED",
                "原因": f"永续增长率 {g:.2%} ≥ WACC {wacc:.2%}："
                        "永续项分母 ≤ 0，级数不收敛，拒绝计算",
                "依据": "CAS 无关；这是数学约束（几何级数收敛条件）"}
    pv = sum(cf / (1 + wacc) ** (i + 1) for i, cf in enumerate(fcf))
    tv = fcf[-1] * (1 + g) / (wacc - g)                 # 永续增长（Gordon）
    pv_tv = tv / (1 + wacc) ** len(fcf)
    return {"任务": "估价", "预测期年数": len(fcf), "WACC": wacc, "永续增长率": g,
            "预测期现值": round(pv, 2), "永续价值": round(tv, 2),
            "永续价值现值": round(pv_tv, 2), "企业价值": round(pv + pv_tv, 2),
            "判定": "PASS", "依据": "多阶段 DCF；g < WACC 已校验"}


def 决策(估值: float, 市价: float, 市价来源: str, 安全边际: float = 0.20) -> dict:
    """任务三：决策。阈值比对；**市价来源不可缺**，否则输出不可用。"""
    if not 市价来源.strip():
        return {"任务": "决策", "判定": "FAIL_CLOSED",
                "原因": "未提供市价来源：拿不出处的市价做决策等于编数据"}
    if 估值 <= 0:
        return {"任务": "决策", "判定": "REJECT", "原因": "估值为非正，无可比基础"}
    if 市价 <= 0:
        return {"任务": "决策", "判定": "FAIL_CLOSED", "原因": "市价非正"}
    ratio = 估值 / 市价
    if ratio < 1.0:
        verdict, why = "REJECT", f"估值低于市价（{ratio:.2f}×），NPV < 0"
    elif ratio >= 1 + 安全边际:
        verdict, why = "BUY", f"估值高于市价 {ratio:.2f}×，达到 {安全边际:.0%} 安全边际"
    else:
        verdict, why = "HOLD", f"估值高于市价但仅 {ratio:.2f}×，未达安全边际"
    return {"任务": "决策", "估值": 估值, "市价": 市价, "市价来源": 市价来源,
            "估值/市价": round(ratio, 4), "安全边际要求": 安全边际,
            "判定": verdict, "理由": why,
            "依据": "阈值比对；**不构成投资建议**，市价为外部参数"}


def main() -> int:
    print("=" * 74)
    print("三任务：定价（客观）· 估价（主观受约束）· 决策（阈值拦截）")
    print("=" * 74)

    r1 = 定价(s=100.0, k=100.0, t=1.0, r=0.03, sigma=0.25)
    print("\n【一】定价")
    for k in ("标的", "行权", "波动率", "理论价格", "反解波动率", "往返残差", "判定"):
        print(f"  {k}: {r1[k]}")

    print("\n【二】估价")
    r2 = 估价(fcf=[100.0, 110.0, 120.0, 130.0, 140.0], wacc=0.10, g=0.03)
    for k in ("WACC", "永续增长率", "预测期现值", "永续价值", "企业价值", "判定"):
        print(f"  {k}: {r2[k]}")
    r2b = 估价([100.0, 110.0], wacc=0.08, g=0.08)
    print(f"  反例（g = WACC）: {r2b['判定']} — {r2b['原因'][:46]}…")

    print("\n【三】决策")
    for market, src in ((1500.0, "构造（示例市价）"), (1800.0, "构造（示例市价）"),
                        (2100.0, "构造（示例市价）"), (1500.0, "")):
        r3 = 决策(r2["企业价值"], market, src)
        print(f"  市价 {market:>7.0f} [{src or '无来源'}] → {r3['判定']}: "
              f"{r3.get('理由') or r3.get('原因')}")

    print("\n" + "=" * 74)
    print("说明：估值为构造假设，非对真实公司的判断；决策段市价为外部参数，")
    print("      不构成投资建议。以上每行均可用计算器复算。")
    return 0 if r1["判定"] == "PASS" and r2["判定"] == "PASS" else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
