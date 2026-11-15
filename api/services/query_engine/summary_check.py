"""Checking a model-written summary before it is stored: plain text, and every number traceable.

- ``check_summary_text``: 80–1,200 characters of plain text — no links, email
  addresses, markdown links or code fences (dataset content can carry
  instructions; a summary that grew a link is refused).
- ``find_untraced_numbers``: every number the summary states must be in the
  facts the backend recomputed itself (never facts the caller sent), or in the
  dataset's or table's title and description. Numbers are read the way Indian
  data writes them: Devanagari digits, "1,23,456" and "123,456" grouping,
  "1.2 lakh" / "3 crore" scaled, "%" dropped, fiscal labels such as "2015-16"
  kept whole. A number passes when it equals an allowed number, or is within
  the rounding its own shown decimals imply ("31.4" for 31.375), or within the
  rounding its trailing zeros imply ("about 12,000" for 11,874). Years
  (1900–2100 without grouping) must match exactly.
- Years and spans: "2019-2021" and "2019-21" are the same span; a span passes
  when it is in the facts or both its years are.
- A number in a sentence that names exactly one measure column (by its whole
  name) must not be another measure's own min or max (a figure swapped
  between columns), unless it is also a table-wide figure. Place, time and
  category columns' figures are table-wide.
- A lakh or crore figure passes as the scaled number or as the bare one (a
  column may already be in lakh). Rounding at trailing zeros applies only
  from four digits up, so "40 states" can't stand in for 36.

Returns the offending numbers as written, so the writer can be told which.

Docs: api/views/query_engine/architecture.md
"""

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

MIN_CHARS = 80
MAX_CHARS = 1200

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_FISCAL = re.compile(r"(?<![\d.])((?:19|20)\d{2})\s*[-–/]\s*(\d{2}|\d{4})(?![\d])")
# A number not glued to letters or another number ("Rs.12,345" is read whole; "COVID19" is not a number).
_NUMBER = re.compile(
    r"(?<![A-Za-z\d,])(?<!\d\.)(-?\d[\d,]*(?:\.\d+)?)(\s*(?:lakhs?|lacs?|crores?|लाख|करोड़))?",
    re.IGNORECASE,
)
# Rounding at trailing zeros ("about 12,000") only for numbers of at least this many digits.
MIN_DIGITS_FOR_ROUNDING = 4
_SCALES = {"lakh": Decimal(100_000), "lac": Decimal(100_000), "crore": Decimal(10_000_000)}
_SENTENCE = re.compile(r"(?<=[.!?।])\s+")

_URL = re.compile(
    r"https?://|www\.|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|in|gov|edu|io|info|co|int)\b",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
_CODE_FENCE = re.compile(r"```|~~~")


@dataclass(frozen=True)
class StatedNumber:
    """A number as a summary wrote it, with the values it may stand for and their tolerance."""

    text: str
    readings: Tuple[Tuple[Decimal, Decimal], ...]  # (value, tolerance), first is the main one
    is_year: bool

    @property
    def value(self) -> Decimal:
        return self.readings[0][0]


@dataclass
class AllowedNumbers:
    """What a summary may say: table-wide numbers, fiscal labels, and each column's own figures."""

    common: Set[Decimal] = field(default_factory=set)
    labels: Set[str] = field(default_factory=set)
    by_column: Dict[str, Set[Decimal]] = field(default_factory=dict)

    def all_numbers(self) -> Set[Decimal]:
        found = set(self.common)
        for numbers in self.by_column.values():
            found |= numbers
        return found


def check_summary_text(text: str) -> List[str]:
    """What is wrong with the text as a summary (empty list: it is fine)."""
    problems: List[str] = []
    length = len(text.strip())
    if length < MIN_CHARS:
        problems.append("too_short")
    if length > MAX_CHARS:
        problems.append("too_long")
    if _URL.search(text):
        problems.append("url")
    if _EMAIL.search(text):
        problems.append("email")
    if _MARKDOWN_LINK.search(text):
        problems.append("markdown_link")
    if _CODE_FENCE.search(text):
        problems.append("code_fence")
    return problems


def _label(start: str, end: str) -> str:
    """One spelling for a year span: "2019-2021" and "2019-21" are both "2019-21"."""
    if len(end) == 4 and end[:2] == start[:2]:
        end = end[2:]
    return f"{start}-{end}"


def _span_years(label: str) -> Tuple[int, int]:
    """The first and last calendar year of a span label ("2019-21" → 2019, 2021)."""
    start, end = label.split("-")
    if len(end) == 4:
        return int(start), int(end)
    last = int(start[:2] + end)
    return int(start), last if last >= int(start) else last + 100


def _numbers_in(text: str) -> Tuple[List[StatedNumber], List[Tuple[str, str]]]:
    """The plain numbers and the year spans (as written, and in one spelling) in a text."""
    normalised = str(text).translate(_DEVANAGARI_DIGITS)
    labels = [
        (m.group(0).strip(), _label(m.group(1), m.group(2))) for m in _FISCAL.finditer(normalised)
    ]
    without_labels = _FISCAL.sub(" ", normalised)
    found: List[StatedNumber] = []
    for match in _NUMBER.finditer(without_labels):
        written, scale_word = match.group(1), (match.group(2) or "").strip().lower()
        digits = written.replace(",", "")
        try:
            value = Decimal(digits)
        except InvalidOperation:
            continue
        scale = next((v for k, v in _SCALES.items() if scale_word.startswith(k)), None)
        if scale_word == "लाख":
            scale = _SCALES["lakh"]
        if scale_word == "करोड़":
            scale = _SCALES["crore"]
        whole = digits.lstrip("-").split(".")[0]
        if "." in digits:
            decimals = len(digits.split(".")[1])
            tolerance = Decimal(5) / Decimal(10) ** (decimals + 1)
        else:
            trailing = len(whole) - len(whole.rstrip("0")) if whole.strip("0") else 0
            if len(whole) < MIN_DIGITS_FOR_ROUNDING:
                trailing = 0
            tolerance = Decimal(5) * Decimal(10) ** trailing / 10
        is_year = (
            scale is None and "," not in written and "." not in digits and 1900 <= value <= 2100
        )
        if is_year:
            tolerance = Decimal(0)
        readings: List[Tuple[Decimal, Decimal]] = []
        if scale is not None:
            readings.append((value * scale, tolerance * scale))
        # The bare number too: a column may already be in lakh ("Rs 1,234.5 lakh").
        readings.append((value, tolerance))
        found.append(
            StatedNumber(
                text=(written + (" " + scale_word if scale_word else "")).strip(),
                readings=tuple(readings),
                is_year=is_year,
            )
        )
    return found, labels


def _walk(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def _collect(values: Iterable[Any], numbers: Set[Decimal], labels: Set[str]) -> None:
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float, Decimal)):
            try:
                numbers.add(Decimal(str(value)))
            except InvalidOperation:
                continue
        elif isinstance(value, str):
            stated, found_labels = _numbers_in(value)
            for number in stated:
                numbers.update(reading for reading, _ in number.readings)
            for _, label in found_labels:
                labels.add(label)
                first, last = _span_years(label)
                numbers.update({Decimal(first), Decimal(last)})


def allowed_numbers(facts: Dict[str, Any], extra_texts: Iterable[str] = ()) -> AllowedNumbers:
    """Every number in the facts and the extra texts; measure columns' own figures kept apart.

    A place, time or category column's figures (distinct counts, year ranges)
    are table-wide: any sentence may use them.
    """
    allowed = AllowedNumbers()
    rest = {key: value for key, value in facts.items() if key != "columns"}
    _collect(_walk(rest), allowed.common, allowed.labels)
    _collect(extra_texts, allowed.common, allowed.labels)
    for column in facts.get("columns", []):
        name = str(column.get("name", ""))
        _collect([name, column.get("description")], allowed.common, allowed.labels)
        figures = [column.get(key) for key in ("min", "max", "distinct")]
        if column.get("role") == "measure":
            own: Set[Decimal] = set()
            _collect(figures, own, allowed.labels)
            allowed.by_column[name] = own
        else:
            _collect(figures, allowed.common, allowed.labels)
    return allowed


def _traced(number: StatedNumber, candidates: Set[Decimal]) -> bool:
    for value, tolerance in number.readings:
        if value in candidates or any(abs(value - c) <= tolerance for c in candidates):
            return True
    return False


def _column_named(sentence: str, columns: Iterable[str]) -> Optional[str]:
    """The one measure column a sentence names by its whole name (units in brackets ignored)."""
    lowered = sentence.lower()
    named = []
    for column in columns:
        base = re.sub(r"\s*\(.*?\)", "", column).strip().lower()
        if len(base) >= 3 and re.search(rf"(?<!\w){re.escape(base)}(?!\w)", lowered):
            named.append(column)
    return named[0] if len(named) == 1 else None


def find_untraced_numbers(
    text: str, facts: Dict[str, Any], extra_texts: Iterable[str] = ()
) -> List[str]:
    """The numbers (as written) in a summary that the facts can't account for."""
    allowed = allowed_numbers(facts, extra_texts)
    everything = allowed.all_numbers()
    untraced: List[str] = []
    for sentence in _SENTENCE.split(text):
        stated, labels = _numbers_in(sentence)
        for written, label in labels:
            first, last = _span_years(label)
            if label not in allowed.labels and not (
                Decimal(first) in everything and Decimal(last) in everything
            ):
                untraced.append(written)
        column = _column_named(sentence, allowed.by_column)
        for number in stated:
            if not _traced(number, everything):
                untraced.append(number.text)
            elif column is not None and not (
                _traced(number, allowed.by_column[column]) or _traced(number, allowed.common)
            ):
                untraced.append(number.text)
    return list(dict.fromkeys(untraced))


def facts_text_size(facts: Dict[str, Any]) -> int:
    """How long the facts are as JSON (what the pending endpoint caps)."""
    return len(json.dumps(facts, ensure_ascii=False, default=str))
