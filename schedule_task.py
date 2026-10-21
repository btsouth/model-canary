"""The schedule part of the canary task: a cron-style scheduler built from a written spec.

The model gets SCHEDULE.md and a stub. The reference implementation here answers the hidden
tests and is itself checked against a brute-force search in gen.py's check.
"""
import random

STUB = '''"""Cron-style schedules. SCHEDULE.md has the full rules."""


def matches(expr, when):
    """True if the schedule expr runs at the minute of the datetime when."""
    raise NotImplementedError


def next_run(expr, after):
    """The first run of expr strictly after the datetime after, or None."""
    raise NotImplementedError
'''

REFERENCE = '''"""Cron-style schedules. SCHEDULE.md has the full rules."""
import calendar
import datetime as dt
import re

RULE = "@RULE@"
WRAP = @WRAP@
YEARS = @YEARS@

MACROS = {"@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *",
          "@weekly": "0 0 * * 0", "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
          "@hourly": "0 * * * *"}
MONTHS = {n: i for i, n in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DAYS = {n: i for i, n in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"])}
BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def _value(text, field):
    names = MONTHS if field == 3 else DAYS if field == 4 else {}
    if text.lower() in names:
        return names[text.lower()]
    if not re.fullmatch(r"[0-9]+", text):
        raise ValueError(f"bad value {text!r}")
    n = int(text)
    lo, hi = BOUNDS[field]
    if not lo <= n <= hi:
        raise ValueError(f"{n} is out of range")
    return n


def _range(a, b, field):
    lo, hi = BOUNDS[field]
    if a <= b:
        return list(range(a, b + 1))
    if not WRAP:
        raise ValueError("range runs backwards")
    if field == 4:
        a, b, hi = a % 7, b % 7, 6
    seq, v = [], a
    while True:
        seq.append(v)
        if v == b:
            return seq
        v = v + 1 if v < hi else lo


def _field(text, field):
    lo, hi = BOUNDS[field]
    if text == "*" or (text == "?" and field in (2, 4)):
        return set(range(lo, hi + 1)) if field != 4 else set(range(7)), [], False
    values, extra = set(), []
    for item in text.split(","):
        if field == 2 and item.upper() == "L":
            extra.append(("L",))
            continue
        if field == 4:
            m = re.fullmatch(r"([0-7])[Ll]", item)
            if m:
                extra.append(("L", int(m[1]) % 7))
                continue
            m = re.fullmatch(r"([0-7])#([1-5])", item)
            if m:
                extra.append(("#", int(m[1]) % 7, int(m[2])))
                continue
        m = re.fullmatch(r"(\\*|[0-9A-Za-z]+)(?:-([0-9A-Za-z]+))?(?:/([0-9]+))?", item)
        if not m or (m[1] == "*" and m[2]):
            raise ValueError(f"bad item {item!r}")
        step = int(m[3]) if m[3] else 1
        if step < 1:
            raise ValueError("step must be at least 1")
        if m[1] == "*":
            seq = list(range(lo, hi + 1))
        else:
            a = _value(m[1], field)
            b = _value(m[2], field) if m[2] else (hi if m[3] else a)
            seq = _range(a, b, field)
        values.update(seq[::step])
    if field == 4:
        values = {v % 7 for v in values}
    return values, extra, True


def _parse(expr):
    text = expr.strip()
    if text.startswith("@"):
        if text.lower() not in MACROS:
            raise ValueError(f"unknown shortcut {text!r}")
        text = MACROS[text.lower()]
    parts = text.split()
    if len(parts) != 5:
        raise ValueError("an expression needs five fields")
    return [_field(part, i) for i, part in enumerate(parts)]


def _day_ok(fields, day):
    dom, dom_extra, dom_restricted = fields[2]
    dow, dow_extra, dow_restricted = fields[4]
    last = calendar.monthrange(day.year, day.month)[1]
    weekday = day.isoweekday() % 7
    dom_ok = day.day in dom or (("L",) in dom_extra and day.day == last)
    dow_ok = weekday in dow or any(
        (e[0] == "L" and e[1] == weekday and day.day + 7 > last)
        or (e[0] == "#" and e[1] == weekday and (day.day - 1) // 7 + 1 == e[2])
        for e in dow_extra)
    if RULE == "or" and dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def matches(expr, when):
    fields = _parse(expr)
    return (when.minute in fields[0][0] and when.hour in fields[1][0]
            and when.month in fields[3][0] and _day_ok(fields, when.date()))


def next_run(expr, after):
    fields = _parse(expr)
    start = after.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    limit = after + dt.timedelta(days=365 * YEARS)
    minutes, hours, months = sorted(fields[0][0]), sorted(fields[1][0]), fields[3][0]
    day = start.date()
    while day <= limit.date():
        if day.month in months and _day_ok(fields, day):
            for h in hours:
                for m in minutes:
                    t = dt.datetime(day.year, day.month, day.day, h, m)
                    if t >= start:
                        return t if t <= limit else None
        day += dt.timedelta(days=1)
    return None
'''

SPEC = '''# Schedules

`tally/schedule.py` reads cron-style schedule expressions. Implement `matches(expr, when)`
and `next_run(expr, after)` exactly as described here. Times are naive `datetime` objects;
there are no time zones or daylight saving changes.

## Expressions

An expression is five fields separated by one or more spaces or tabs. Leading and trailing
whitespace is ignored.

| Field | Values | Names |
|---|---|---|
| minute | 0-59 | |
| hour | 0-23 | |
| day of month | 1-31 | |
| month | 1-12 | `JAN`-`DEC` |
| day of week | 0-7, where 0 and 7 are both Sunday | `SUN`-`SAT` |

Names are the first three letters of the English month or day name, in any case. They are
only allowed in the month and day-of-week fields. Numbers are plain decimal digits; leading
zeros are fine.

Each field is a comma-separated list of one or more items. An item is one of:

- `*`: every value of the field.
- `N`: a single value.
- `A-B`: every value from A to B. @WRAP_TEXT@
- Any of the above followed by `/S`, where S is a whole number of at least 1. Of the values
  the item lists, in order, it keeps the first and then every S-th one after it, so `*/15`
  in the minute field is 0, 15, 30 and 45. `N/S` lists N up to the field's maximum.
- Day of month only: `L`, the last day of the month.
- Day of week only: `NL`, the last day N of the month (`5L` is the last Friday), and `N#K`,
  the K-th day N of the month, where K is 1 to 5 (`1#2` is the second Monday). Here N is a
  number from 0 to 7, not a name.

A whole day-of-month or day-of-week field may also be `?`, which means the same as `*`.

Instead of five fields, an expression may be one of these shortcuts, in any case:
`@yearly` and `@annually` (`0 0 1 1 *`), `@monthly` (`0 0 1 * *`), `@weekly` (`0 0 * * 0`),
`@daily` and `@midnight` (`0 0 * * *`), and `@hourly` (`0 * * * *`).

Anything else raises `ValueError`: the wrong number of fields, a value outside its field's
range, an empty item, a step of 0, a name in the wrong field or in a step, `L`, `NL` or `N#K`
in the wrong field, a `?` outside the two day fields, an unknown shortcut, and so on. Both
functions check the whole expression first and raise `ValueError` for a bad one, whatever
the other argument is.

## When a schedule runs

A schedule runs at every minute whose minute, hour and month are listed in their fields, on
every day that is allowed. @RULE_TEXT@

`matches(expr, when)` returns `True` if the schedule runs at `when`'s minute. Seconds and
microseconds are ignored.

`next_run(expr, after)` returns the first run strictly after `after`, as a `datetime` with
zero seconds and microseconds. For a schedule that runs every minute, both 10:00:00 and
10:00:30 give 10:01. If there is no run within @YEARS@ × 365 days after `after` (a run exactly
at that limit still counts), it returns `None`. It must stay fast even then: each call
should take well under a tenth of a second.
'''

WRAP_TEXT = {
    True: ("If A is greater than B, the range wraps around: it counts up from A to the field's "
           "maximum, then carries on from the field's minimum up to B, so `22-2` in the hour field "
           "is 22, 23, 0, 1 and 2. In the day-of-week field a wrapping range counts through 0 to 6 "
           "with 7 treated as 0, so `FRI-MON` is Friday, Saturday, Sunday and Monday."),
    False: ("A must not be greater than B, so `22-2` in the hour field raises `ValueError`. "
            "In the day-of-week field `6-7` is fine and means Saturday and Sunday."),
}

RULE_TEXT = {
    "or": ("Days follow the classic cron rule. The day-of-month and day-of-week fields each "
           "count as unrestricted only when they are exactly `*` or `?`; anything else, "
           "including `*/2`, restricts them. When both are restricted, a day is allowed if it "
           "matches either one. When only one is restricted, the day must match that one. When "
           "neither is, every day is allowed."),
    "and": ("A day is allowed only when it matches both the day-of-month field and the "
            "day-of-week field. A field that is `*` or `?` matches every day."),
}


def params(rng):
    return {"rule": rng.choice(["or", "and"]), "wrap": rng.choice([True, False]),
            "years": rng.choice([10, 20, 50])}


def files(sp, fixed):
    """Return (schedule.py source, SCHEDULE.md text) for these schedule params."""
    values = {"RULE": sp["rule"], "WRAP": sp["wrap"], "YEARS": sp["years"],
              "WRAP_TEXT": WRAP_TEXT[sp["wrap"]], "RULE_TEXT": RULE_TEXT[sp["rule"]]}
    code, spec = (REFERENCE if fixed else STUB), SPEC
    for key, value in values.items():
        code = code.replace(f"@{key}@", str(value))
        spec = spec.replace(f"@{key}@", str(value))
    return code, spec


def _random_field(rng, field):
    lo, hi = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)][field]
    names = {3: ["JAN", "feb", "Mar", "APR", "may", "Jun", "JUL", "aug", "SEP", "oct", "Nov", "DEC"],
             4: ["SUN", "mon", "Tue", "WED", "thu", "Fri", "sat"]}.get(field)

    def val():
        if names and rng.random() < 0.4:
            return rng.choice(names)
        return str(rng.randint(lo, hi))

    def item():
        kind = rng.random()
        if field == 2 and kind < 0.08:
            return "L"
        if field == 4 and kind < 0.1:
            return f"{rng.randint(0, 7)}L"
        if field == 4 and kind < 0.2:
            return f"{rng.randint(0, 7)}#{rng.randint(1, 5)}"
        if kind < 0.45:
            return val()
        a, b = sorted(rng.sample(range(lo, hi + 1), 2))
        if rng.random() < 0.05:
            a, b = b, a
        text = f"{a}-{b}"
        if rng.random() < 0.4:
            text += f"/{rng.randint(1, 5)}"
        return text

    r = rng.random()
    if r < 0.3 and field != 0:
        return "*"
    if r < 0.4:
        return f"*/{rng.randint(2, 12)}"
    return ",".join(item() for _ in range(rng.choice([1, 1, 2, 3])))


def random_expr(rng):
    return " ".join(_random_field(rng, f) for f in range(5))


def random_time(rng):
    return (f"dt.datetime({rng.randint(2020, 2034)}, {rng.randint(1, 12)}, {rng.randint(1, 28)}, "
            f"{rng.randint(0, 23)}, {rng.randint(0, 59)}, {rng.choice([0, 0, 30])})")


FIXED_RUNS = [
    ("every_quarter_hour", "*/15 * * * *", "dt.datetime(2026, 5, 4, 10, 7)"),
    ("strictly_after", "30 9 * * *", "dt.datetime(2026, 5, 4, 9, 30)"),
    ("ignores_seconds", "* * * * *", "dt.datetime(2026, 5, 4, 10, 0, 30)"),
    ("year_rollover", "0 0 1 1 *", "dt.datetime(2026, 12, 31, 23, 59)"),
    ("leap_day", "0 0 29 2 *", "dt.datetime(2025, 3, 1)"),
    ("last_day", "0 18 L * *", "dt.datetime(2027, 2, 3)"),
    ("last_day_leap", "0 18 L 2 *", "dt.datetime(2028, 1, 31)"),
    ("last_friday", "0 9 * * 5L", "dt.datetime(2026, 7, 1)"),
    ("third_monday", "0 9 * * 1#3", "dt.datetime(2026, 7, 1)"),
    ("fifth_monday", "0 9 * * 1#5", "dt.datetime(2026, 7, 1)"),
    ("sunday_as_seven", "0 8 * * 7", "dt.datetime(2026, 7, 1)"),
    ("both_day_fields", "0 12 1 * MON", "dt.datetime(2026, 6, 2)"),
    ("both_day_fields_step", "0 12 */10 * 1-5/2", "dt.datetime(2026, 6, 2)"),
    ("wrapping_hours", "0 22-2/2 * * *", "dt.datetime(2026, 6, 2, 3)"),
    ("wrapping_days", "0 6 * * FRI-MON", "dt.datetime(2026, 6, 2)"),
    ("question_mark", "0 7 ? * ?", "dt.datetime(2026, 6, 2, 8)"),
    ("shortcut_weekly", "@WEEKLY", "dt.datetime(2026, 6, 2)"),
    ("shortcut_hourly", "  @hourly ", "dt.datetime(2026, 6, 2, 8, 0)"),
    ("never_feb_30", "0 0 30 2 *", "dt.datetime(2026, 6, 2)"),
    ("never_short_months_31", "0 0 31 4,6,9,11 *", "dt.datetime(2026, 6, 2)"),
    ("rare_leap_monday", "0 0 29 2 1#5", "dt.datetime(2026, 6, 2)"),
    ("rare_leap_sunday_last", "0 0 29 FEB 0L", "dt.datetime(2026, 6, 2)"),
    ("names_any_case", "0 0 1 jAn-MaR sUn", "dt.datetime(2026, 1, 2)"),
    ("tabs_between_fields", "5\t4 \t * * *", "dt.datetime(2026, 1, 2)"),
    ("leading_zeros", "05 04 01 01 *", "dt.datetime(2026, 1, 2)"),
    ("step_from_value", "10/20 * * * *", "dt.datetime(2026, 1, 2, 3, 51)"),
    ("dow_step_wraps_seven", "0 0 * * 1/3", "dt.datetime(2026, 1, 3)"),
]

INVALID = [
    "60 * * * *", "* 24 * * *", "* * 0 * *", "* * 32 * *", "* * * 13 *", "* * * * 8",
    "*/0 * * * *", "* * * *", "* * * * * *", "@reboot", "a * * * *", "* L * * *",
    "* * * * L", "* * * * 8L", "* * * * 1#6", "* * * JAN-MAR/x *", "1,,2 * * * *",
    "* * * * JAN", "* * * MON *", "? * * * *", "* * 5L * *", "* * * * MON#2", "*-5 * * * *",
    "", "5-1 * * * *", "* * * * SAT-TUE", "1-2-3 * * * *", "* * L/2 * *",
]


def cases(rng):
    hidden = []
    for name, expr, after in FIXED_RUNS:
        hidden.append((f"next_{name}", "auto", f"schedule.next_run({expr!r}, {after})"))
    for i in range(30):
        hidden.append((f"next_random_{i:02d}", "auto",
                       f"schedule.next_run({random_expr(rng)!r}, {random_time(rng)})"))
    for i in range(4):
        hidden.append((f"matches_random_{i:02d}", "auto",
                       f"schedule.matches({random_expr(rng)!r}, {random_time(rng)})"))
    # A run time of the schedule (found by the reference when the tests are written), with
    # seconds added, so these should mostly be True.
    for i in range(10):
        expr = random_expr(rng)
        hidden.append((f"matches_run_time_{i:02d}", "auto",
                       f"schedule.matches({expr!r}, @HIT:{expr!r}|{random_time(rng)}@)"))
    for i, expr in enumerate(INVALID):
        hidden.append((f"bad_expr_{i:02d}", "auto", f"schedule.next_run({expr!r}, dt.datetime(2026, 1, 1))"))
    hidden.append(("matches_checks_expr", "auto", "schedule.matches('61 * * * *', dt.datetime(2026, 1, 1))"))
    hidden.append(("fast_when_rare", "true",
                   "_fast(lambda: [schedule.next_run(e, dt.datetime(2026, 6, 2)) for e in "
                   "['0 0 30 2 *', '0 0 29 2 1#5', '0 0 31 4,6,9,11 *'] * 10], 3.0)"))
    visible = [
        ("schedule_quarter_hour", "eq", "schedule.next_run('*/15 * * * *', dt.datetime(2026, 5, 4, 10, 7))"),
        ("schedule_daily", "eq", "schedule.next_run('@daily', dt.datetime(2026, 5, 4, 10, 7))"),
        ("schedule_matches", "eq", "schedule.matches('30 9 * * *', dt.datetime(2026, 5, 4, 9, 30, 15))"),
        ("schedule_rejects", "raises", "schedule.next_run('60 * * * *', dt.datetime(2026, 5, 4))"),
    ]
    return visible, hidden
