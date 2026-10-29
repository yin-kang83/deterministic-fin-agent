# -*- coding: utf-8 -*-
"""哈希链底稿池 + Decimal 金额（可验证版）。

为什么重写这一小块
  上一版只有「声明」没有「断言」：
    · Decimal 用了，但没有 0.1+0.2 的断言证明它真的精确；
    · 哈希链建了，但**没有验链函数**——篡改后没人能发现，
      而论文里写的正是「一旦被篡改，链条断裂，审计师瞬间察觉」。
  本模块的每条能力都配一条**能被推翻的断言**。

三条断言（这是本模块存在的理由）
  ① Decimal 下 0.1 + 0.2 == 0.3 精确成立；float 下不成立（对照）。
  ② 篡改任意一块后 verify_chain() 必须失败，且能定位到第几块断链。
  ③ 只追加：已写入的记录不可修改（返回副本，改副本不影响链）。

不做的事
  · 不声称「满足司法证据保全」——那需要可信时间戳/第三方签名，本模块只有链内一致性；
  · 不把 hash 当签名：能验「有没有被改」，不能验「谁写的」。
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, getcontext
from typing import Any

getcontext().prec = 28


class Money:
    """金额：全程 Decimal，两位小数，禁止 float 参与。"""

    __slots__ = ("v",)

    def __init__(self, x: Any):
        if isinstance(x, float):
            raise TypeError("金额不得用 float 构造（会引入二进制误差），请用 str 或 Decimal")
        self.v = Decimal(str(x)).quantize(Decimal("0.01"))

    def __add__(self, o: "Money") -> "Money":
        return Money(self.v + o.v)

    def __sub__(self, o: "Money") -> "Money":
        return Money(self.v - o.v)

    def __eq__(self, o: object) -> bool:
        return isinstance(o, Money) and self.v == o.v

    def __repr__(self) -> str:
        return f"{self.v}"


def _canon(obj: Any) -> str:
    """规范化序列化：排序键、无空格、Decimal 转定长字符串。"""
    def conv(x: Any) -> Any:
        if isinstance(x, Decimal):
            return format(x, "f")
        if isinstance(x, Money):
            return format(x.v, "f")
        if isinstance(x, dict):
            return {k: conv(v) for k, v in sorted(x.items())}
        if isinstance(x, (list, tuple)):
            return [conv(v) for v in x]
        return x
    return json.dumps(conv(obj), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


GENESIS = "0" * 64


class Chain:
    """只追加的哈希链。"""

    def __init__(self) -> None:
        self._blocks: list[dict[str, Any]] = []
        self._prev = GENESIS

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"idx": len(self._blocks), "prev": self._prev, "payload": payload}
        h = hashlib.sha256((_canon(body) + self._prev).encode("utf-8")).hexdigest()
        block = dict(body, hash=h)
        self._blocks.append(block)
        self._prev = h
        return self.read(len(self._blocks) - 1)

    def read(self, i: int) -> dict[str, Any]:
        """返回**副本**：外部改副本不影响链（只追加语义）。"""
        return json.loads(json.dumps(self._blocks[i], default=str))

    def __len__(self) -> int:
        return len(self._blocks)

    def anchor(self) -> dict:
        """链外锚点：块数与末块哈希。必须**登记到链外**（日志/邮件/另一系统）。

        为什么需要它
          链内一致性只能发现「改」，**发现不了「删」**——
          删掉最后一块后，剩下的链依然自洽（实测：3 块删 1 块，verify() 仍返回 True）。
          而「删掉一笔不利的底稿」正是最常见的掩盖手段。
          要发现删除，只能靠外部记住「原来有几块、末块哈希是多少」。
        """
        return {"块数": len(self._blocks),
                "末块哈希": self._blocks[-1]["hash"] if self._blocks else GENESIS}

    def verify(self, expected_len: int | None = None,
               expected_head: str | None = None) -> tuple[bool, int | None, str]:
        """验链。返回 (是否完整, 首个断链位置, 原因)。

        传入 expected_len / expected_head（来自链外 anchor）时，
        **可发现尾部截断**；不传则只能发现「改」不能发现「删」，这是固有局限。
        """
        if expected_len is not None and len(self._blocks) != expected_len:
            return False, len(self._blocks), (
                f"块数不符：外部锚点 {expected_len} 块，实际 {len(self._blocks)} 块"
                "（疑似尾部被截断）")
        prev = GENESIS
        for i, b in enumerate(self._blocks):
            if b.get("prev") != prev:
                return False, i, f"第 {i} 块的 prev 与上一块 hash 不符"
            body = {"idx": b["idx"], "prev": b["prev"], "payload": b["payload"]}
            h = hashlib.sha256((_canon(body) + b["prev"]).encode("utf-8")).hexdigest()
            if h != b.get("hash"):
                return False, i, f"第 {i} 块内容被改（重算 hash 不符）"
            prev = b["hash"]
        if expected_head is not None and prev != expected_head:
            return False, len(self._blocks) - 1, "末块哈希与外部锚点不符"
        return True, None, f"{len(self._blocks)} 块完整"

    def tamper_for_test(self, i: int, key: str, val: Any) -> None:
        """仅供自检：模拟攻击者直接改内部数据。"""
        self._blocks[i]["payload"][key] = val


def _selftest() -> int:
    ok, fail = 0, []

    def chk(name, cond, got=None):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(f"{name} → {got}")

    # ① Decimal vs float（对照）
    chk("Decimal 0.1+0.2 == 0.3",
        Decimal("0.1") + Decimal("0.2") == Decimal("0.3"),
        Decimal("0.1") + Decimal("0.2"))
    chk("float 0.1+0.2 != 0.3（对照组）", (0.1 + 0.2) != 0.3, 0.1 + 0.2)
    m = Money("0.1") + Money("0.2")
    chk("Money 相加精确等于 0.30", m == Money("0.30"), m)
    try:
        Money(0.1)
        chk("float 构造被拒绝", False, "未拒绝")
    except TypeError:
        chk("float 构造被拒绝", True)

    # ② 链完整时 verify 通过
    c = Chain()
    c.append({"摘要": "费用报销", "金额": Money("1000.00")})
    c.append({"摘要": "收入", "金额": Money("2000.50")})
    c.append({"摘要": "税金", "金额": Money("60.02")})
    okv, pos, msg = c.verify()
    chk("三块链完整", okv and pos is None, (okv, pos, msg))

    # ③ 篡改中间块 ⇒ 必须被发现，且定位到第 1 块
    c.tamper_for_test(1, "金额", Money("9999.00"))
    okv2, pos2, msg2 = c.verify()
    chk("篡改后验链失败", okv2 is False, (okv2, msg2))
    chk("断链定位到第 1 块", pos2 == 1, pos2)

    # ④ 只追加：读出来的是副本
    c2 = Chain()
    c2.append({"金额": Money("1.00")})
    copy = c2.read(0)
    copy["payload"]["金额"] = "999.00"
    okv3, _, _ = c2.verify()
    chk("改副本不影响链", okv3 is True, c2.read(0)["payload"]["金额"])

    # ⑤ 规范化序列化与键序无关
    chk("键序不影响 hash",
        _canon({"a": 1, "b": 2}) == _canon({"b": 2, "a": 1}),
        (_canon({"a": 1, "b": 2}), _canon({"b": 2, "a": 1})))

    # ⑤b 尾部截断：不传锚点发现不了（如实断言局限），传锚点必须发现
    c3 = Chain()
    for i in range(3):
        c3.append({"n": i})
    anc = c3.anchor()
    c3._blocks.pop()
    ok_n, _, _ = c3.verify()
    chk("无锚点时尾部截断查不出（固有局限）", ok_n is True, ok_n)
    ok_a, pos_a, msg_a = c3.verify(expected_len=anc["块数"], expected_head=anc["末块哈希"])
    chk("有锚点时尾部截断被发现", ok_a is False and "块数不符" in msg_a, (ok_a, msg_a))

    # ⑥ 明确边界：本模块不验「谁写的」
    chk("不声称是签名（无签名接口）", not hasattr(Chain, "sign"))

    print(f"哈希链底稿池自检：{ok} 项通过，{len(fail)} 项失败")
    for f in fail:
        print("  ✗", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
