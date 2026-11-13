"""Ledger arithmetic."""

from decimal import Decimal, ROUND_HALF_EVEN


def total(entries):
    """Round ledger entries to cents and return their exact sum."""
    return sum((round_cents(entry) for entry in entries), Decimal("0.00"))


def round_cents(amount):
    """Round an amount to cents using decimal half-to-even rounding."""
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
