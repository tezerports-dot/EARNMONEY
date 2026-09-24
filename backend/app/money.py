"""Money is integer paise. These helpers only format; they never do float math."""

from __future__ import annotations


def format_inr(paise: int) -> str:
    """``1234500`` → ``₹12,345``; ``1234550`` → ``₹12,345.50`` (Indian grouping)."""
    if not isinstance(paise, int):
        raise TypeError("paise must be an int")
    sign = "-" if paise < 0 else ""
    rupees, rest = divmod(abs(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"{sign}₹{digits}" + (f".{rest:02d}" if rest else "")


def rupees_to_paise(rupees: int) -> int:
    if not isinstance(rupees, int):
        raise TypeError("rupees must be an int")
    return rupees * 100
