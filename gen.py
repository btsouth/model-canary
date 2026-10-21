#!/usr/bin/env python3
"""Generate the canary task for one seed.

Every seed has the same five modules and the same bugs, but different names, rules and
numbers, so remembering an earlier day's task doesn't help. Hidden test answers come from a
fixed reference copy of the same seed.

  gen.py SEED OUTDIR          write the task to OUTDIR/task and hidden tests to OUTDIR/hidden.py
  gen.py SEED OUTDIR --fixed  same, with the reference fix applied
  gen.py check [N]            check N seeds: the fix passes everything, the bugs fail
"""
import importlib
import random
import re
import shutil
import subprocess
import sys
import tempfile
import datetime
from fractions import Fraction
from pathlib import Path

import schedule_task

VERSION = 3
PKG = "tally"
MODULES = ("allocate", "intervals", "duration", "fields", "ledger", "schedule")

UNIT_SETS = [
    [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)],
    [("h", 3600), ("m", 60), ("s", 1)],
    [("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)],
]


def params(seed):
    rng = random.Random(f"canary-v{VERSION}-{seed}")
    return {
        "split": rng.choice(["split", "apportion", "allocate_units", "share_out"]),
        "tie": rng.choice(["earlier", "later"]),
        "units": rng.choice(UNIT_SETS),
        "sep": rng.choice([";", ",", "|"]),
        "quote": rng.choice(['"', "'"]),
        "rounding": rng.choice(["half_up", "half_even"]),
        "who": rng.choice(["person", "member", "client", "account"]),
        "symbol": rng.choice(["$", "€", "£"]),
        "schedule": schedule_task.params(rng),
    }


def fill(text, **values):
    for key, value in values.items():
        text = text.replace(f"@{key}@", str(value))
    return text.lstrip("\n")


# Each module: a template, plus (buggy, fixed) replacements for its @BUG...@ markers.

ALLOCATE = '''
from fractions import Fraction


def @SPLIT@(total, weights):
    """Split the whole number total into whole-number shares in proportion to weights.

    The shares always add up to exactly total. Every share starts as its exact
    proportional amount rounded down. The units left over then go one each to the
    shares with the largest remainders; when remainders are equal, the @TIE@
    share gets its unit first. Weights are non-negative numbers (int, float or
    Fraction) and at least one must be positive, otherwise ValueError is raised.
    A negative total is split like its absolute value, with every share negated.

    >>> @SPLIT@(100, [1, 1, 1])
    @EXAMPLE@
    """
    if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
        raise ValueError("weights must be non-negative and not all zero")
@BUG_SPLIT@


def format_amount(cents):
    """Format whole cents as money: 1234 -> '@SYM@12.34' and -5 -> '-@SYM@0.05'."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}@SYM@{cents // 100}.{cents % 100:02d}"
'''

ALLOCATE_BUGS = {
    "BUG_SPLIT": (
        '''    whole = sum(weights)
    return [round(total * w / whole) for w in weights]''',
        '''    sign = -1 if total < 0 else 1
    total = abs(total)
    ws = [Fraction(w) for w in weights]
    whole = sum(ws)
    exact = [total * w / whole for w in ws]
    shares = [int(e) for e in exact]
    order = sorted(range(len(ws)), key=lambda i: (shares[i] - exact[i], @TIEKEY@))
    for i in order[: total - sum(shares)]:
        shares[i] += 1
    return [sign * s for s in shares]'''),
}

INTERVALS = '''
def merge(intervals):
    """Merge half-open [start, end) intervals.

    Intervals that overlap or touch (one ends exactly where another starts) become
    one. Input may be in any order. Empty intervals (start == end) are dropped, and
    an interval with start > end raises ValueError. Returns a sorted list of
    (start, end) tuples.
    """
    result = []
@BUG_MERGE@
        if start == end:
            continue
@BUG_TOUCH@
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def free_slots(busy, day_start, day_end, min_length=1):
    """Return the free [start, end) gaps inside [day_start, day_end).

    busy is a list of intervals in any order, which may stick out past either end
    of the day. Gaps shorter than min_length are left out; a gap exactly
    min_length long is kept.
    """
    slots = []
    cursor = day_start
    for start, end in merge(busy):
        if end <= day_start or start >= day_end:
            continue
@BUG_MIN@
            slots.append((cursor, start))
        cursor = max(cursor, end)
    if day_end - cursor >= min_length:
        slots.append((cursor, day_end))
    return slots


def total_covered(intervals):
    """Total length covered by the intervals, counting overlaps once."""
    return sum(end - start for start, end in merge(intervals))
'''

INTERVALS_BUGS = {
    "BUG_MERGE": (
        "    for start, end in intervals:",
        '''    for start, end in sorted(intervals):
        if start > end:
            raise ValueError(f"interval ends before it starts: {(start, end)}")'''),
    "BUG_TOUCH": (
        "        if result and start < result[-1][1]:",
        "        if result and start <= result[-1][1]:"),
    "BUG_MIN": (
        "        if start - cursor > min_length:",
        "        if start - cursor >= min_length:"),
}

DURATION = '''
import re

_UNITS = {@UNITS_DICT@}
@BUG_PATTERN@


def parse(text):
    """Parse a duration like @EXAMPLES@ into seconds.

    The units are @UNIT_LIST@, in upper or lower case. Each unit may appear at most
    once, largest unit first, each with a whole number in front of it. Spaces around
    and between the parts are allowed. Anything else, including an empty string,
    raises ValueError.
    """
@BUG_PARSE@


def format_duration(seconds):
    """Format seconds the way parse() reads them, e.g. @FORMAT_EXAMPLE@ and 0 -> '0s'.

    Negative seconds raise ValueError.
    """
    if seconds < 0:
        raise ValueError("negative duration")
    if seconds == 0:
        return "0s"
    out = []
    for unit, size in _UNITS.items():
        if seconds >= size:
            out.append(f"{seconds // size}{unit}")
            seconds %= size
    return "".join(out)
'''

DURATION_BUGS = {
    "BUG_PATTERN": (
        '_PART = re.compile(r"(\\d+)([@UNIT_CHARS@])")',
        '_FULL = re.compile(r"\\s*" + "".join(rf"(?:(\\d+){u}\\s*)?" for u in _UNITS), re.IGNORECASE)'),
    "BUG_PARSE": (
        '''    parts = _PART.findall(text.strip())
    if not parts:
        raise ValueError(f"bad duration: {text!r}")
    return sum(int(n) * _UNITS[u] for n, u in parts)''',
        '''    match = _FULL.fullmatch(text)
    if not match or not any(match.groups()):
        raise ValueError(f"bad duration: {text!r}")
    return sum(int(n) * size for n, size in zip(match.groups(), _UNITS.values()) if n)'''),
}

FIELDS = '''
SEP = "@SEP@"
QUOTE = "@QUOTE_PY@"


def parse_fields(text):
    """Parse a line like @FIELDS_EXAMPLE@ into a dict of strings.

    Fields are separated by SEP. Whitespace around keys and around unquoted values is
    ignored. A value may be wrapped in QUOTE characters; inside quotes, SEP and '='
    are ordinary characters, whitespace is kept, and two QUOTE characters in a row
    stand for one QUOTE character. Empty fields, such as one after a trailing SEP,
    are skipped, so a blank line gives {}. A field without '=', an empty key, a
    quote that is never closed, or a key that appears twice raises ValueError.
    """
    fields, field, quoted = [], "", False
    for ch in text:
        if ch == QUOTE:
            quoted = not quoted
            field += ch
        elif ch == SEP and not quoted:
            fields.append(field)
            field = ""
        else:
            field += ch
    fields.append(field)
@BUG_UNCLOSED@
    result = {}
    for field in fields:
        if not field.strip():
            continue
        if "=" not in field:
            raise ValueError(f"field without '=': {field!r}")
        key, value = (part.strip() for part in field.split("=", 1))
        if not key:
            raise ValueError(f"empty key in {field!r}")
        if len(value) >= 2 and value[0] == QUOTE and value[-1] == QUOTE:
@BUG_ESCAPE@
@BUG_DUP@
        result[key] = value
    return result
'''

FIELDS_BUGS = {
    "BUG_UNCLOSED": (
        "",
        '''    if quoted:
        raise ValueError("quote never closed")'''),
    "BUG_ESCAPE": (
        "            value = value[1:-1]",
        "            value = value[1:-1].replace(QUOTE * 2, QUOTE)"),
    "BUG_DUP": (
        "",
        '''        if key in result:
            raise ValueError(f"duplicate key {key!r}")'''),
}

LEDGER = '''
from fractions import Fraction

from .allocate import @SPLIT@
from .duration import parse


def bill(entries, rate_per_hour):
    """Charge each @WHO@ for their time.

    entries is a list of (name, duration) pairs, where duration is text for
    duration.parse(), and rate_per_hour is a whole number of cents per hour.

    Names are matched ignoring case and surrounding spaces. Each @WHO@ appears once
    in the result, under the first spelling seen (with spaces trimmed), in order of
    first appearance. The total charge is worked out from everyone's exact total
    seconds and rounded to a whole cent only once,
    @ROUNDING_DOC@. It is then divided between @WHOS@ with
    @SPLIT@(), in proportion to their seconds. If the total time is zero, everyone
    is charged 0.

    Returns a list of (name, cents) pairs; no entries gives [].
    """
@BUG_BILL@
'''

ROUNDING_DOC = {
    "half_up": "with exact halves rounded up",
    "half_even": "with exact halves rounded to the even cent",
}

LEDGER_BUGS = {
    "BUG_BILL": (
        '''    totals = {}
    charge = 0
    for name, text in entries:
        seconds = parse(text)
        name = name.strip()
        totals[name] = totals.get(name, 0) + seconds
        charge += round(seconds * rate_per_hour / 3600)
    if not totals:
        return []
    names = list(totals)
    shares = @SPLIT@(charge, [totals[n] for n in names])
    return list(zip(names, shares))''',
        '''    totals, spelling = {}, {}
    for name, text in entries:
        seconds = parse(text)
        key = name.strip().casefold()
        if key not in totals:
            totals[key], spelling[key] = 0, name.strip()
        totals[key] += seconds
    keys = list(totals)
    total_seconds = sum(totals.values())
    if total_seconds == 0:
        return [(spelling[k], 0) for k in keys]
    exact = Fraction(total_seconds * rate_per_hour, 3600)
    charge = @ROUND_EXPR@
    shares = @SPLIT@(charge, [totals[k] for k in keys])
    return [(spelling[k], s) for k, s in zip(keys, shares)]'''),
}

ROUND_EXPR = {
    "half_up": "int(exact + Fraction(1, 2))",
    "half_even": "round(exact)",
}


def sources(p, fixed):
    units = p["units"]
    chars = "".join(u for u, _ in units)
    q = p["quote"]
    s = p["sep"]
    common = {
        "SPLIT": p["split"],
        "TIE": p["tie"],
        "TIEKEY": "i" if p["tie"] == "earlier" else "-i",
        "EXAMPLE": "[34, 33, 33]" if p["tie"] == "earlier" else "[33, 33, 34]",
        "SYM": p["symbol"],
        "UNITS_DICT": ", ".join(f'"{u}": {size}' for u, size in units),
        "UNIT_CHARS": chars,
        "UNIT_LIST": ", ".join(u for u, _ in units[:-1]) + " and " + units[-1][0],
        "EXAMPLES": f"'1h30m', '2{units[0][0].upper()} 5m' or '45s'",
        "FORMAT_EXAMPLE": "5400 -> '1h30m'",
        "SEP": s,
        "QUOTE_PY": '\\"' if q == '"' else q,
        "FIELDS_EXAMPLE": f"name=Ann{s} note={q}hi{s} there{q}",
        "WHO": p["who"],
        "WHOS": {"person": "people"}.get(p["who"], p["who"] + "s"),
        "ROUNDING_DOC": ROUNDING_DOC[p["rounding"]],
        "ROUND_EXPR": ROUND_EXPR[p["rounding"]],
    }
    out = {}
    for name, template, bugs in (("allocate", ALLOCATE, ALLOCATE_BUGS), ("intervals", INTERVALS, INTERVALS_BUGS),
                                 ("duration", DURATION, DURATION_BUGS), ("fields", FIELDS, FIELDS_BUGS),
                                 ("ledger", LEDGER, LEDGER_BUGS)):
        text = template
        for marker, (buggy, good) in bugs.items():
            code = good if fixed else buggy
            # An empty replacement removes the marker's whole line.
            text = text.replace(f"@{marker}@\n", "") if not code else text.replace(f"@{marker}@", code)
        out[name] = fill(text, **common)
    out["__init__"] = '"""Small helpers for billing time."""\n'
    out["schedule"], _ = schedule_task.files(p["schedule"], fixed)
    return out


# Test cases. Each is (name, kind, code): "eq" compares code to the reference answer,
# "raises" expects ValueError, "true" expects a true value.

def dur(p, *pairs):
    return " ".join(f"{n}{u}" for n, u in pairs)


def cases(p, seed):
    rng = random.Random(f"canary-cases-v{VERSION}-{seed}")
    S = f"allocate.{p['split']}"
    q, s = p["quote"], p["sep"]
    big, small = p["units"][0][0], p["units"][-1][0]
    r = lambda a, b: rng.randint(a, b)

    def lit(text):
        return repr(text)

    visible = [
        ("split_even", "eq", f"{S}(90, [1, 1, 1])"),
        ("split_thirds", "eq", f"{S}(100, [1, 1, 1])"),
        ("format_amount", "eq", "allocate.format_amount(1234)"),
        ("merge_overlap", "eq", "intervals.merge([(1, 5), (3, 8)])"),
        ("merge_touching", "eq", "intervals.merge([(1, 3), (3, 6)])"),
        ("free_slots", "eq", "intervals.free_slots([(10, 12)], 9, 17)"),
        ("parse_basic", "eq", "duration.parse('1h30m')"),
        ("parse_rejects_junk", "raises", "duration.parse('1h junk')"),
        ("fields_basic", "eq", f"fields.parse_fields({lit(f'a=1{s} b = two ')})"),
        ("fields_quoted", "eq", f"fields.parse_fields({lit(f'a={q}x{s}y{q}')})"),
        ("bill_basic", "eq", "ledger.bill([('Ann', '1h'), ('Bob', '30m')], 1200)"),
        ("bill_same_name", "eq", "ledger.bill([('Ann', '1h'), (' ann', '1h')], 1200)"),
    ]

    floats = [[r(1, 9) / 10 for _ in range(r(2, 5))] for _ in range(6)]
    hidden = [
        # allocate
        ("split_thirds", "eq", f"{S}(100, [1, 1, 1])"),
        ("split_tie", "eq", f"{S}(2, [1, 1, 1])"),
        ("split_remainders", "eq", f"{S}(10, [1, 2, 3, 4])"),
        ("split_random_a", "eq", f"{S}({r(50, 9999)}, {[r(1, 20) for _ in range(r(3, 6))]})"),
        ("split_random_b", "eq", f"{S}({r(50, 9999)}, {[r(0, 9) for _ in range(5)] + [1]})"),
        ("split_floats_sum", "true", f"all(sum({S}(t, w)) == t for t in (1, 7, 99, 12345) for w in {floats})"),
        ("split_fractions", "eq", f"{S}({r(5, 50)}, [Fraction(1, 3), Fraction(2, 3), Fraction(1, 6)])"),
        ("split_zero_weight", "eq", f"{S}(11, [0, 1, 1])"),
        ("split_negative", "eq", f"{S}(-100, [1, 1, 1])"),
        ("split_negative_random", "eq", f"{S}({-r(50, 999)}, {[r(1, 9) for _ in range(4)]})"),
        ("split_single", "eq", f"{S}({r(1, 999)}, [5])"),
        ("split_rejects_empty", "raises", f"{S}(10, [])"),
        ("split_rejects_zero", "raises", f"{S}(10, [0, 0])"),
        ("split_rejects_negative", "raises", f"{S}(10, [1, -1])"),
        ("format_negative", "eq", "allocate.format_amount(-5)"),
        ("format_large", "eq", f"allocate.format_amount({r(100000, 999999)})"),
        # intervals
        ("merge_touching", "eq", "intervals.merge([(1, 3), (3, 6)])"),
        ("merge_unsorted", "eq", "intervals.merge([(8, 9), (1, 3), (2, 4)])"),
        ("merge_chain", "eq", "intervals.merge([(5, 7), (1, 3), (3, 5)])"),
        ("merge_contained_and_empty", "eq", "intervals.merge([(5, 5), (1, 10), (2, 3)])"),
        ("merge_random", "eq", f"intervals.merge({[(a, a + r(0, 6)) for a in (r(0, 40) for _ in range(8))]})"),
        ("merge_empty_list", "eq", "intervals.merge([])"),
        ("merge_rejects_backwards", "raises", "intervals.merge([(1, 2), (5, 3)])"),
        ("free_unsorted_overhang", "eq", "intervals.free_slots([(16, 20), (7, 10), (12, 13)], 9, 17)"),
        ("free_exact_min_length", "eq", "intervals.free_slots([(10, 12)], 8, 14, min_length=2)"),
        ("free_short_gaps", "eq", "intervals.free_slots([(10, 11), (12, 15)], 9, 16, min_length=2)"),
        ("free_fully_busy", "eq", "intervals.free_slots([(0, 30)], 9, 17)"),
        ("covered_overlap", "eq", "intervals.total_covered([(4, 8), (1, 5), (20, 22)])"),
        # duration
        ("parse_every_unit", "eq", f"[duration.parse(f'2{{u}}') for u in {[u for u, _ in p['units']]}]"),
        ("parse_all_parts", "eq", f"duration.parse({lit(' '.join(f'{r(1, 9)}{u}' for u, _ in p['units']))})"),
        ("parse_spaces", "eq", f"duration.parse({lit(f'  {r(1, 59)}s ')})"),
        ("parse_upper_case", "eq", f"duration.parse({lit(f'{r(1, 9)}{big.upper()} {r(1, 59)}M')})"),
        ("parse_rejects_blank", "true", "all(_raises(duration.parse, t) for t in ('', '   '))"),
        ("parse_rejects_junk", "true", "all(_raises(duration.parse, t) for t in ('1h junk', 'junk1h', '1x', '1h-2m', '1h,2m'))"),
        ("parse_rejects_order", "true", f"all(_raises(duration.parse, t) for t in ('30m1h', '5s 2m', '1h1h'))"),
        ("parse_rejects_numbers", "true", "all(_raises(duration.parse, t) for t in ('h', '1.5h', '-2m'))"),
        ("duration_round_trip", "true", f"all(duration.parse(duration.format_duration(n)) == n for n in (0, 1, 59, 60, 3600, 5400, 86400, 90061, {r(1, 10**6)}))"),
        ("format_duration_negative", "raises", "duration.format_duration(-1)"),
        # fields
        ("fields_basic", "eq", f"fields.parse_fields({lit(f' a = 1 {s}b=two')})"),
        ("fields_quoted_separator", "eq", f"fields.parse_fields({lit(f'a={q}x{s} y{q}{s} b=2')})"),
        ("fields_quoted_equals", "eq", f"fields.parse_fields({lit(f'a={q}x=y{q}')})"),
        ("fields_doubled_quote", "eq", f"fields.parse_fields({lit(f'a={q}it{q}{q}s{q}{s} b=1')})"),
        ("fields_keeps_inner_spaces", "eq", f"fields.parse_fields({lit(f'a={q}  x {q}')})"),
        ("fields_blank", "true", f"fields.parse_fields('') == {{}} and fields.parse_fields('   ') == {{}} and fields.parse_fields({lit(f'a=1{s}{s} ')}) == {{'a': '1'}}"),
        ("fields_rejects_duplicate", "raises", f"fields.parse_fields({lit(f'a=1{s} a=2')})"),
        ("fields_rejects_missing_equals", "raises", f"fields.parse_fields({lit(f'a=1{s} b')})"),
        ("fields_rejects_empty_key", "raises", f"fields.parse_fields({lit(f' =1')})"),
        ("fields_rejects_unclosed_quote", "raises", f"fields.parse_fields({lit(f'a={q}x{s} b=2')})"),
        # ledger
        ("bill_names", "eq", "ledger.bill([('  Ann ', '1h'), ('Bob', '30m'), ('ANN', '15m'), ('bob ', '1m')], 600)"),
        ("bill_rounds_once", "eq", "ledger.bill([('A', '1m'), ('B', '1m'), ('C', '1m')], 100)"),
        ("bill_half_cent", "eq", "ledger.bill([('A', '3m')], 50)"),
        ("bill_tie", "eq", "ledger.bill([('A', '10m'), ('B', '10m')], 3)"),
        ("bill_zero_time", "eq", "ledger.bill([('A', '0s'), ('a', '0m')], 1200)"),
        ("bill_empty", "eq", "ledger.bill([], 1200)"),
        ("bill_random_a", "eq", f"ledger.bill({[(rng.choice(['Ann', 'ann', 'Bo', 'BO ', 'Cy']), f'{r(0, 3)}h {r(0, 59)}m {r(0, 59)}s') for _ in range(6)]}, {r(100, 20000)})"),
        ("bill_random_b", "eq", f"ledger.bill({[(rng.choice(['Dee', 'Eli', 'dee', 'Fay']), f'{r(1, 50)}m {r(0, 59)}s') for _ in range(7)]}, {r(100, 20000)})"),
    ]
    sched_visible, sched_hidden = schedule_task.cases(rng)
    return visible + sched_visible, hidden + sched_hidden


TEST_HEADER = '''import datetime
import datetime as dt
import time
import unittest
from fractions import Fraction

from tally import allocate, duration, fields, intervals, ledger, schedule


def _raises(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def _fast(fn, seconds):
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start < seconds


class @CLASS@(unittest.TestCase):
'''


RAISES = object()


def render_tests(case_list, answers, cls):
    lines = [fill(TEST_HEADER, CLASS=cls)]
    for name, kind, code in case_list:
        lines.append(f"    def test_{name}(self):")
        if kind == "auto" and answers[name] is RAISES:
            kind = "raises"
        if kind in ("eq", "auto"):
            lines.append(f"        self.assertEqual({code}, {answers[name]!r})")
        elif kind == "raises":
            lines.append(f"        with self.assertRaises(ValueError):\n            {code}")
        else:
            lines.append(f"        self.assertTrue({code})")
        lines.append("")
    lines.append('\nif __name__ == "__main__":\n    unittest.main()')
    return "\n".join(lines) + "\n"


def write_package(root, p, fixed):
    pkg = root / PKG
    pkg.mkdir(parents=True, exist_ok=True)
    for name, text in sources(p, fixed).items():
        (pkg / f"{name}.py").write_text(text)


def brute_check(schedule, rng):
    """Compare next_run with a minute-by-minute search over the next three days."""
    for _ in range(40):
        expr = schedule_task.random_expr(rng)
        after = eval(schedule_task.random_time(rng), {"dt": datetime})
        try:
            got = schedule.next_run(expr, after)
        except ValueError:
            continue
        t = after.replace(second=0, microsecond=0)
        want = None
        for _ in range(3 * 1440):
            t += datetime.timedelta(minutes=1)
            if schedule.matches(expr, t):
                want = t
                break
        if want is not None and got != want:
            raise AssertionError(f"next_run({expr!r}, {after}) = {got}, brute force says {want}")
        if want is None and got is not None and got <= after + datetime.timedelta(days=3):
            raise AssertionError(f"next_run({expr!r}, {after}) = {got}, brute force found nothing")


def reference_answers(p, case_lists, brute=False, seed_rng=None):
    """Evaluate every "eq" case against the fixed code for this seed."""
    with tempfile.TemporaryDirectory() as tmp:
        write_package(Path(tmp), p, fixed=True)
        sys.path.insert(0, tmp)
        for mod in [m for m in sys.modules if m == PKG or m.startswith(PKG + ".")]:
            del sys.modules[mod]
        try:
            ns = {m: importlib.import_module(f"{PKG}.{m}") for m in MODULES}
            ns.update(Fraction=Fraction, dt=datetime, datetime=datetime)
            answers = []
            for case_list in case_lists:
                for i, (name, kind, code) in enumerate(case_list):
                    hit = re.search(r"@HIT:(.*)\|(.*)@", code)
                    if hit:
                        try:
                            when = eval(f"schedule.next_run({hit[1]}, {hit[2]})", ns)
                        except ValueError:
                            when = None
                        when = (when or eval(hit[2], ns)).replace(second=45)
                        case_list[i] = (name, kind, code[:hit.start()] + repr(when) + code[hit.end():])
                found = {}
                for name, kind, code in case_list:
                    if kind == "eq":
                        found[name] = eval(code, ns)
                    elif kind == "auto":
                        try:
                            found[name] = eval(code, ns)
                        except ValueError:
                            found[name] = RAISES
                answers.append(found)
            if brute:
                brute_check(ns["schedule"], seed_rng)
            return answers
        finally:
            sys.path.remove(tmp)
            for mod in [m for m in sys.modules if m == PKG or m.startswith(PKG + ".")]:
                del sys.modules[mod]


def generate(seed, out, fixed=False, check_brute=False):
    """Write OUT/task (the repo the model gets) and OUT/hidden.py. Returns the params."""
    p = params(seed)
    visible, hidden = cases(p, seed)
    vis_answers, hid_answers = reference_answers(p, [visible, hidden], brute=check_brute,
                                                 seed_rng=random.Random(f"brute-{seed}"))
    task = Path(out) / "task"
    write_package(task, p, fixed)
    (task / "tests").mkdir(exist_ok=True)
    (task / "tests" / "__init__.py").write_text("")
    (task / "tests" / "test_tally.py").write_text(render_tests(visible, vis_answers, "TallyTest"))
    (task / ".gitignore").write_text("__pycache__/\n")
    (task / "SCHEDULE.md").write_text(schedule_task.files(p["schedule"], fixed)[1])
    (Path(out) / "hidden.py").write_text(render_tests(hidden, hid_answers, "HiddenTest"))
    return {k: v for k, v in p.items() if k != "units"} | {"units": "".join(u for u, _ in p["units"])}


HAND_CHECKS = [
    # (expression, after, expected) worked out by hand from a calendar.
    ("0 0 29 2 *", datetime.datetime(2025, 3, 1), datetime.datetime(2028, 2, 29)),
    ("0 9 * * 1#3", datetime.datetime(2026, 7, 1), datetime.datetime(2026, 7, 20, 9)),
    ("0 9 * * 5L", datetime.datetime(2026, 7, 1), datetime.datetime(2026, 7, 31, 9)),
    ("0 9 * * 1#5", datetime.datetime(2026, 7, 1), datetime.datetime(2026, 8, 31, 9)),
    ("0 8 * * 7", datetime.datetime(2026, 7, 1), datetime.datetime(2026, 7, 5, 8)),
    ("0 18 L 2 *", datetime.datetime(2028, 1, 31), datetime.datetime(2028, 2, 29, 18)),
    ("*/15 * * * *", datetime.datetime(2026, 5, 4, 10, 7), datetime.datetime(2026, 5, 4, 10, 15)),
    ("* * * * *", datetime.datetime(2026, 5, 4, 10, 0, 30), datetime.datetime(2026, 5, 4, 10, 1)),
    ("30 9 * * *", datetime.datetime(2026, 5, 4, 9, 30), datetime.datetime(2026, 5, 5, 9, 30)),
    ("10/20 * * * *", datetime.datetime(2026, 1, 2, 3, 51), datetime.datetime(2026, 1, 2, 4, 10)),
]


GRADER = r"""
import json, sys, unittest
suite = unittest.defaultTestLoader.loadTestsFromName(sys.argv[1])
result = unittest.TestResult()
suite.run(result)
failed = sorted({t.id().split('.')[-1][5:] for t, _ in result.failures + result.errors})
print(json.dumps({"total": result.testsRun, "failed": failed}))
"""


def grade_dir(task, hidden):
    """Run visible and hidden tests in task. Returns (visible_ok, total, failed)."""
    import json
    visible = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=task, capture_output=True, text=True, timeout=120)
    shutil.copy(hidden, Path(task) / "tests" / "test_hidden.py")
    out = subprocess.run([sys.executable, "-c", GRADER, "tests.test_hidden"], cwd=task, capture_output=True, text=True, timeout=120)
    try:
        res = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        res = {"total": 0, "failed": ["grader-crashed: " + out.stderr[-300:]]}
    (Path(task) / "tests" / "test_hidden.py").unlink()
    return visible.returncode == 0, res["total"], res["failed"]


def hand_check():
    """Check the reference scheduler against answers worked out by hand, for every rule."""
    problems = 0
    for rule in ("or", "and"):
        for wrap in (True, False):
            ns = {}
            exec(schedule_task.files({"rule": rule, "wrap": wrap, "years": 50}, True)[0], ns)
            checks = list(HAND_CHECKS) + [
                ("0 12 1 * MON", datetime.datetime(2026, 6, 2),
                 datetime.datetime(2026, 6, 8, 12) if rule == "or" else datetime.datetime(2027, 2, 1, 12)),
                ("0 22-2/2 * * *", datetime.datetime(2026, 6, 2, 3),
                 datetime.datetime(2026, 6, 2, 22) if wrap else ValueError),
            ]
            for expr, after, want in checks:
                try:
                    got = ns["next_run"](expr, after)
                except ValueError:
                    got = ValueError
                if got != want:
                    problems += 1
                    print(f"rule={rule} wrap={wrap}: next_run({expr!r}, {after}) = {got}, expected {want}")
    return problems


def check(n):
    buggy_scores, problems = [], hand_check()
    for seed in range(n):
        for fixed in (True, False):
            with tempfile.TemporaryDirectory() as tmp:
                p = generate(seed, tmp, fixed, check_brute=fixed)
                ok, total, failed = grade_dir(Path(tmp) / "task", Path(tmp) / "hidden.py")
                if fixed and (not ok or failed):
                    problems += 1
                    print(f"seed {seed}: reference fails {failed} visible_ok={ok}")
                if not fixed:
                    if ok:
                        problems += 1
                        print(f"seed {seed}: buggy code passes the visible tests")
                    buggy_scores.append(total - len(failed))
    print(f"{n} seeds, {problems} problems, {total} hidden tests, unfixed code scores "
          f"{min(buggy_scores)}-{max(buggy_scores)} (mean {sum(buggy_scores) / len(buggy_scores):.1f})")
    return problems == 0


if __name__ == "__main__":
    if sys.argv[1] == "check":
        sys.exit(0 if check(int(sys.argv[2]) if len(sys.argv) > 2 else 50) else 1)
    print(generate(sys.argv[1], sys.argv[2], fixed="--fixed" in sys.argv))
