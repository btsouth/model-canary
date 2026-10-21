def merge(intervals):
    """Merge half-open [start, end) intervals.

    Intervals that overlap or touch (one ends exactly where the next starts)
    become one. Input may be in any order; empty intervals (start == end) are
    dropped. Returns a sorted list of (start, end) tuples.
    """
    result = []
    for start, end in intervals:
        if start == end:
            continue
        if result and start < result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def free_slots(busy, day_start, day_end, min_length=1):
    """Return the free [start, end) gaps inside [day_start, day_end).

    busy is a list of intervals in any order, which may stick out past the
    day. Gaps shorter than min_length are left out.
    """
    slots = []
    cursor = day_start
    for start, end in merge(busy):
        if end <= day_start or start >= day_end:
            continue
        if start - cursor >= min_length:
            slots.append((cursor, start))
        cursor = max(cursor, end)
    if day_end - cursor >= min_length:
        slots.append((cursor, day_end))
    return slots
