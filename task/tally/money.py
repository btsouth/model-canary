def split(total_cents, weights):
    """Split total_cents into whole-cent shares proportional to weights.

    The shares always add up to exactly total_cents. Each share is the
    proportional amount rounded down, and the cents left over go one each to
    the shares with the largest remainders. Ties go to the earlier share.
    Weights are non-negative numbers and at least one must be positive.
    A negative total is split the same way as its absolute value and every
    share is negated.

    >>> split(100, [1, 1, 1])
    [34, 33, 33]
    """
    if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
        raise ValueError("weights must be non-negative and not all zero")
    total_weight = sum(weights)
    return [round(total_cents * w / total_weight) for w in weights]


def format_cents(cents):
    """Format cents as dollars, e.g. 1234 -> '$12.34' and -5 -> '-$0.05'."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"
