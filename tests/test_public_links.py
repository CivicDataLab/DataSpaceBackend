import uuid

import pytest
from django.db import IntegrityError

from api.utils.public_links import (
    PUBLIC_ID_LENGTH,
    build_url_slug,
    generate_public_id,
    parse_public_id,
    save_with_public_id,
)


class Record:
    public_id = ""


def test_generate_public_id_format_and_randomness() -> None:
    ids = {generate_public_id() for _ in range(20000)}
    assert len(ids) == 20000
    for value in list(ids)[:500]:
        assert len(value) == PUBLIC_ID_LENGTH
        assert value.isascii() and (value.islower() or value.isdigit()) and value.isalnum()


def test_save_assigns_id_when_missing() -> None:
    record = Record()
    calls = []
    save_with_public_id(record, lambda: calls.append(record.public_id))
    assert len(calls) == 1 and calls[0] == record.public_id
    assert parse_public_id(record.public_id) == record.public_id


def test_save_keeps_existing_id() -> None:
    record = Record()
    record.public_id = "k3x9m2qa7b1z"
    save_with_public_id(record, lambda: None)
    assert record.public_id == "k3x9m2qa7b1z"


def test_save_retries_with_new_id_on_clash() -> None:
    record = Record()
    tried = []

    def save() -> None:
        tried.append(record.public_id)
        if len(tried) < 3:
            raise IntegrityError("UNIQUE constraint failed: dataset.public_id")

    save_with_public_id(record, save)
    assert len(tried) == 3 and len(set(tried)) == 3
    assert record.public_id == tried[-1]


def test_save_postgres_style_error_is_retried() -> None:
    record = Record()
    tried = []

    def save() -> None:
        tried.append(record.public_id)
        if len(tried) == 1:
            raise IntegrityError(
                'duplicate key value violates unique constraint "dataset_public_id_key"\n'
                "DETAIL:  Key (public_id)=(abc) already exists."
            )

    save_with_public_id(record, save)
    assert len(tried) == 2


def test_save_other_unique_errors_are_not_retried() -> None:
    record = Record()
    tried = []

    def save() -> None:
        tried.append(1)
        raise IntegrityError("UNIQUE constraint failed: dataset.slug")

    with pytest.raises(IntegrityError):
        save_with_public_id(record, save)
    assert len(tried) == 1


def test_save_gives_up_after_max_attempts() -> None:
    record = Record()
    tried = []

    def save() -> None:
        tried.append(1)
        raise IntegrityError("UNIQUE constraint failed: dataset.public_id")

    with pytest.raises(IntegrityError):
        save_with_public_id(record, save, max_attempts=4)
    assert len(tried) == 4


@pytest.mark.parametrize(
    "title, expected",
    [
        ("City Air Quality Index", "city-air-quality-index-k3x9m2qa7b1z"),
        ("  Rainfall: 2020–2024 (Daily)! ", "rainfall-20202024-daily-k3x9m2qa7b1z"),
        ("जनगणना डेटा 2011", "2011-k3x9m2qa7b1z"),
        ("जनगणना डेटा", "k3x9m2qa7b1z"),
        ("", "k3x9m2qa7b1z"),
        (None, "k3x9m2qa7b1z"),
        ("!!! ???", "k3x9m2qa7b1z"),
    ],
)
def test_build_url_slug(title, expected) -> None:
    assert build_url_slug(title, "k3x9m2qa7b1z") == expected


def test_build_url_slug_cuts_long_titles_between_words() -> None:
    title = "District wise monthly rainfall and temperature readings for all states of India 1990 to 2024"
    assert (
        build_url_slug(title, "k3x9m2qa7b1z")
        == "district-wise-monthly-rainfall-and-temperature-k3x9m2qa7b1z"
    )


def test_build_url_slug_exact_limit_and_one_long_word() -> None:
    exact = "a" * 20 + " " + "b" * 29  # 50 chars once slugified
    assert build_url_slug(exact, "k3x9m2qa7b1z") == f"{'a' * 20}-{'b' * 29}-k3x9m2qa7b1z"
    long_word = "x" * 80
    assert build_url_slug(long_word, "k3x9m2qa7b1z") == f"{'x' * 50}-k3x9m2qa7b1z"


@pytest.mark.parametrize(
    "link, expected",
    [
        ("city-air-quality-index-k3x9m2qa7b1z", "k3x9m2qa7b1z"),
        ("k3x9m2qa7b1z", "k3x9m2qa7b1z"),
        ("/city-air-quality-index-K3X9M2QA7B1Z/", "k3x9m2qa7b1z"),
        ("old-words-that-changed-k3x9m2qa7b1z", "k3x9m2qa7b1z"),
        (str(uuid.UUID("3f2a9c1e-7b4d-4e2a-9c1e-a1b2c3d4e5f6")), None),
        ("3f2a9c1e7b4d4e2a9c1ea1b2c3d4e5f6", None),
        ("123", None),
        ("city-air-quality-index", None),
        ("city-air-quality-k3x9m2qa7b1", None),
        ("city-air-quality-k3x9m2qa7b1z9", None),
        ("city-air-quality-k3x9m2qa7b1_", None),
        ("city-air-quality-k3x9m2qa7b1z\n/", None),
        ("k3x9m2qa7b1٣", None),
        ("k3x9m2qa7b1é", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_public_id(link, expected) -> None:
    assert parse_public_id(link) == expected


def test_build_then_parse_round_trip() -> None:
    for title in ["City Air Quality Index", "जनगणना डेटा", "", "x" * 300]:
        public_id = generate_public_id()
        assert parse_public_id(build_url_slug(title, public_id)) == public_id
