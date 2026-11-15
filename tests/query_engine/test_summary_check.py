"""Layer 2: the summary text rules and the number check (TXT1, N1, N2)."""

from typing import Any, Dict

import pytest

from api.services.query_engine.summary_check import check_summary_text, find_untraced_numbers

FACTS: Dict[str, Any] = {
    "level": "resource",
    "dataset": {
        "title": "NFHS-5 district fact sheets",
        "description": "Survey round 2019-21",
        "places": ["Assam"],
    },
    "table": {"name": "Anaemia by district", "description": ""},
    "row_count": 11874,
    "column_count": 4,
    "columns": [
        {"name": "District", "kind": "text", "role": "geography_district", "distinct": 33},
        {"name": "Round", "kind": "text", "role": "time_fiscal_year", "distinct": 2},
        {
            "name": "Anaemia (%)",
            "kind": "numeric",
            "role": "measure",
            "unit": "%",
            "min": 31.375,
            "max": 68.2,
        },
        {
            "name": "Population",
            "kind": "numeric_text",
            "role": "measure",
            "min": 123456.0,
            "max": 3200000.0,
        },
    ],
    "coverage": {
        "years": ["2015-16", "2019-20"],
        "year_min": "2015-16",
        "year_max": "2019-20",
        "district_count": 33,
    },
    "coverage_text": "2015-16 to 2019-20 · 33 districts in Assam",
}

PLAIN = (
    "District-level anaemia figures for Assam from two survey rounds, with population "
    "counts for each district and the share of women who are anaemic."
)


class TestTextRules:
    def test_plain_text_passes(self) -> None:
        assert check_summary_text(PLAIN) == []

    @pytest.mark.parametrize(
        "text,problem",
        [
            ("Too short.", "too_short"),
            (PLAIN * 12, "too_long"),
            (PLAIN + " See https://example.org for more.", "url"),
            (PLAIN + " Write to data@example.org.", "email"),
            (PLAIN + " [the source](http://x)", "markdown_link"),
            (PLAIN + " ```SELECT 1```", "code_fence"),
            (PLAIN + " Visit www.example.org today.", "url"),
        ],
    )
    def test_each_rule_fires(self, text: str, problem: str) -> None:
        assert problem in check_summary_text(text)


class TestNumbersAccepted:
    @pytest.mark.parametrize(
        "sentence",
        [
            "It has 11874 rows.",
            "Anaemia (%) ranges from 31.4 to 68.2 per cent.",
            "About 12,000 rows are included.",
            "Population ranges from 1,23,456 upward.",
            "Population starts near 1.2 lakh.",
            "Anaemia (%) is at most 68.2% in one district.",
            "It covers the 2015-16 and 2019-20 rounds.",
            "It covers ३३ districts.",
            "It comes from the NFHS-5 fact sheets.",
            "Population reaches 32 lakh in the largest district.",
        ],
    )
    def test_traceable_numbers_pass(self, sentence: str) -> None:
        assert find_untraced_numbers(sentence, FACTS) == []


class TestNumbersRejected:
    def test_an_invented_count(self) -> None:
        assert find_untraced_numbers("It covers 36 districts.", FACTS) == ["36"]

    def test_a_percent_not_in_the_facts(self) -> None:
        assert find_untraced_numbers("Anaemia (%) peaks at 72.5%.", FACTS) == ["72.5"]

    def test_a_year_outside_the_coverage(self) -> None:
        assert find_untraced_numbers("Data runs to 2023.", FACTS) == ["2023"]
        assert find_untraced_numbers("It covers 2021-22 too.", FACTS) == ["2021-22"]

    def test_a_years_rounding_never_stretches(self) -> None:
        assert find_untraced_numbers("It starts in 2010.", FACTS) == ["2010"]

    def test_a_minimum_swapped_from_another_column(self) -> None:
        # 123456 is Population's minimum, not Anaemia's.
        assert find_untraced_numbers("Anaemia (%) starts at 123456.", FACTS) == ["123456"]

    def test_only_the_untraced_ones_are_listed_once(self) -> None:
        text = "It has 11874 rows and 99 columns. Another 99 appear."
        assert find_untraced_numbers(text, FACTS) == ["99"]


class TestQcFixes:
    def test_a_sentence_about_districts_may_quote_the_measures_range(self) -> None:
        stunted = "Percentage of children under 5 years who are stunted (%)"
        facts = {
            **FACTS,
            "columns": FACTS["columns"]
            + [
                {
                    "name": stunted,
                    "kind": "numeric",
                    "role": "measure",
                    "unit": "%",
                    "min": 12.1,
                    "max": 59.5,
                },
                {"name": "State", "kind": "text", "role": "geography_state", "distinct": 36},
                {"name": "Year", "kind": "numeric", "role": "time_year", "min": 2015, "max": 2019},
            ],
        }
        for sentence in (
            "Stunting among young children ranges from 12.1% to 59.5% across districts.",
            "Stunting reaches 59.5% in the worst-off district.",
            "Stunting is lowest, at 12.1%, in the best state.",
            "Stunting runs from 12.1% to 59.5% between 36 states.",
            "Values run from 12.1 to 59.5 across the years covered.",
        ):
            assert find_untraced_numbers(sentence, facts) == [], sentence

    def test_lakh_and_crore_figures_copied_with_their_unit_pass(self) -> None:
        facts = {
            **FACTS,
            "columns": [
                {
                    "name": "Expenditure (Rs lakh)",
                    "kind": "numeric",
                    "role": "measure",
                    "unit": "INR lakh",
                    "min": 1234.5,
                    "max": 98765.4,
                }
            ],
        }
        sentence = "Expenditure ranges from Rs 1,234.5 lakh to Rs 98,765.4 lakh across states."
        assert find_untraced_numbers(sentence, facts) == []

    def test_a_round_number_never_stands_in_for_a_small_count(self) -> None:
        facts = {**FACTS, "coverage": {**FACTS["coverage"], "state_count": 36, "district_count": 6}}
        assert find_untraced_numbers("It covers 40 states.", facts) == ["40"]
        assert find_untraced_numbers("It covers 10 districts.", facts) == ["10"]
        assert find_untraced_numbers("It has about 12,000 rows.", FACTS) == []

    def test_year_spans_and_two_year_rounds_are_read_as_years(self) -> None:
        facts = {**FACTS, "dataset": {**FACTS["dataset"], "description": "Survey round 2019-21"}}
        assert find_untraced_numbers("The 2019-2021 round is included.", facts) == []
        assert find_untraced_numbers("It runs from 2019 to 2021.", facts) == []
        assert find_untraced_numbers("It runs from 2015-2023.", facts) == ["2015-2023"]

    def test_rupees_written_without_a_space_are_read_whole(self) -> None:
        assert find_untraced_numbers("Population starts at Rs.1,23,456 in value.", FACTS) == []

    def test_a_bare_domain_counts_as_a_link(self) -> None:
        assert "url" in check_summary_text(PLAIN + " Source: mospi.gov.in.")
