"""Ledger arithmetic."""


def total(entries):
    """Sum ledger entries."""
    return sum(map(float, entries))


def round_cents(amount):
    """Round an amount to two decimal places."""
    return round(float(amount), 2)
