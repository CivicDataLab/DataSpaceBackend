"""Scope strings (Q1, layer 2) and resolving them against the database (S1–S5, S7, layer 1)."""

from typing import Any, Callable

import pytest

from api.services.query_engine.corpus import get_dataset_in_scope, get_resource_in_scope
from api.services.query_engine.errors import BadScope, NotFound, ScopeNotFound
from api.services.query_engine.scope import parse_scope, resolve_scope
from api.utils.enums import (
    CollaborativeStatus,
    DatasetAccessType,
    DatasetStatus,
    UseCaseStatus,
)


class TestParseScope:
    def test_accepts_platform(self) -> None:
        ref = parse_scope("platform")
        assert (ref.kind, ref.public_id) == ("platform", None)

    def test_accepts_a_collaborative_public_id(self) -> None:
        ref = parse_scope("collaborative:ab12cd34ef56")
        assert (ref.kind, ref.public_id) == ("collaborative", "ab12cd34ef56")

    @pytest.mark.parametrize(
        "text",
        [
            None,
            "",
            "  ",
            "Platform",
            "org:ab12cd34ef56",
            "collaborative:",
            "collaborative:ab12cd34ef5",
            "collaborative:ab12cd34ef567",
            "collaborative:AB12CD34EF56",
            "collaborative:ab12cd34ef5!",
            "collaborative: ab12cd34ef56",
        ],
    )
    def test_rejects_anything_else(self, text: Any) -> None:
        with pytest.raises(BadScope):
            parse_scope(text)


@pytest.mark.django_db
class TestResolveScope:
    def test_a_collaborative_covers_only_its_attached_corpus_datasets(
        self, make_dataset: Callable, make_collaborative: Callable
    ) -> None:
        anaemia = make_dataset("Anaemia")
        private = make_dataset("Private survey", access_type=DatasetAccessType.PRIVATE)
        make_dataset("Outside")
        fem = make_collaborative("FemHealth", datasets=[anaemia, private])

        scope = resolve_scope(f"collaborative:{fem.public_id}")

        assert scope.kind == "collaborative"
        assert scope.collaborative_id == fem.id
        assert scope.title == "FemHealth"
        assert scope.dataset_ids == frozenset({anaemia.id})

    def test_a_collaborative_also_covers_the_datasets_of_its_published_use_cases(
        self, make_dataset: Callable, make_use_case: Callable, make_collaborative: Callable
    ) -> None:
        anaemia = make_dataset("Anaemia")
        tenders = make_dataset("MCH tenders")
        private = make_dataset("Private survey", access_type=DatasetAccessType.PRIVATE)
        draft = make_dataset("Draft indicators", status=DatasetStatus.DRAFT)
        mch = make_use_case("MCH gaps", datasets=[tenders, private, draft, anaemia])
        fem = make_collaborative("FemHealth", datasets=[anaemia], use_cases=[mch])

        scope = resolve_scope(f"collaborative:{fem.public_id}")

        assert scope.dataset_ids == frozenset({anaemia.id, tenders.id})
        assert get_dataset_in_scope(tenders.id, scope).id == tenders.id

    @pytest.mark.parametrize("status", [UseCaseStatus.DRAFT, UseCaseStatus.ARCHIVED])
    def test_a_use_case_that_is_not_published_adds_nothing(
        self,
        make_dataset: Callable,
        make_use_case: Callable,
        make_collaborative: Callable,
        status: str,
    ) -> None:
        tenders = make_dataset("MCH tenders")
        unpublished = make_use_case("MCH gaps", status=status, datasets=[tenders])
        fem = make_collaborative("FemHealth", use_cases=[unpublished])

        scope = resolve_scope(f"collaborative:{fem.public_id}")

        assert scope.dataset_ids == frozenset()

    def test_another_collaboratives_use_cases_add_nothing(
        self, make_dataset: Callable, make_use_case: Callable, make_collaborative: Callable
    ) -> None:
        literacy = make_dataset("Literacy")
        make_collaborative("Other", use_cases=[make_use_case("Schools", datasets=[literacy])])
        make_use_case("Not in any collaborative", datasets=[make_dataset("Loose")])
        fem = make_collaborative("FemHealth")

        scope = resolve_scope(f"collaborative:{fem.public_id}")

        assert scope.dataset_ids == frozenset()

    def test_platform_ignores_collaborative_membership(
        self, make_dataset: Callable, make_resource: Callable, make_collaborative: Callable
    ) -> None:
        outside = make_dataset("Outside")
        resource = make_resource(outside)
        make_collaborative("FemHealth", datasets=[make_dataset("Anaemia")])

        scope = resolve_scope("platform")

        assert scope.kind == "platform" and scope.dataset_ids is None
        assert get_resource_in_scope(resource.id, scope).id == resource.id
        assert get_dataset_in_scope(outside.id, scope).id == outside.id

    @pytest.mark.parametrize("status", [CollaborativeStatus.DRAFT, CollaborativeStatus.ARCHIVED])
    def test_a_collaborative_that_is_not_published_is_not_found(
        self, make_collaborative: Callable, status: str
    ) -> None:
        collaborative = make_collaborative(status=status)
        with pytest.raises(ScopeNotFound):
            resolve_scope(f"collaborative:{collaborative.public_id}")

    def test_an_unknown_collaborative_is_not_found(self) -> None:
        with pytest.raises(ScopeNotFound):
            resolve_scope("collaborative:zzzzzzzzzzzz")

    def test_a_collaborative_not_on_the_enabled_list_is_not_found(
        self, settings: Any, make_collaborative: Callable
    ) -> None:
        enabled = make_collaborative("FemHealth")
        other = make_collaborative("Other")
        settings.QE_ENABLED_COLLABORATIVES = [enabled.public_id]

        assert resolve_scope(f"collaborative:{enabled.public_id}").collaborative_id == enabled.id
        with pytest.raises(ScopeNotFound):
            resolve_scope(f"collaborative:{other.public_id}")


@pytest.mark.django_db
class TestItemsInScope:
    def test_an_analysable_resource_outside_the_collaborative_is_not_found(
        self, make_dataset: Callable, make_resource: Callable, make_collaborative: Callable
    ) -> None:
        inside = make_resource(make_dataset("Anaemia"))
        outside_dataset = make_dataset("Outside")
        outside = make_resource(outside_dataset)
        fem = make_collaborative("FemHealth", datasets=[inside.dataset])
        scope = resolve_scope(f"collaborative:{fem.public_id}")

        assert get_resource_in_scope(inside.id, scope).id == inside.id
        with pytest.raises(NotFound):
            get_resource_in_scope(outside.id, scope)
        with pytest.raises(NotFound):
            get_dataset_in_scope(outside_dataset.id, scope)

    def test_a_private_dataset_attached_to_the_collaborative_stays_out(
        self, make_dataset: Callable, make_resource: Callable, make_collaborative: Callable
    ) -> None:
        private = make_dataset("Private", access_type=DatasetAccessType.PRIVATE)
        resource = make_resource(private)
        fem = make_collaborative("FemHealth", datasets=[private])
        scope = resolve_scope(f"collaborative:{fem.public_id}")

        with pytest.raises(NotFound):
            get_resource_in_scope(resource.id, scope)
        with pytest.raises(NotFound):
            get_dataset_in_scope(private.id, scope)

    def test_a_resource_without_a_table_is_not_found(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset(), with_table=False)
        with pytest.raises(NotFound):
            get_resource_in_scope(resource.id, resolve_scope("platform"))

    def test_the_single_resource_check_runs_one_query(
        self,
        make_dataset: Callable,
        make_resource: Callable,
        make_collaborative: Callable,
        django_assert_num_queries: Any,
    ) -> None:
        resource = make_resource(make_dataset("Anaemia"))
        fem = make_collaborative("FemHealth", datasets=[resource.dataset])
        scope = resolve_scope(f"collaborative:{fem.public_id}")

        with django_assert_num_queries(1):
            found = get_resource_in_scope(resource.id, scope)
            # The dataset and the data table come with it, no extra query.
            _ = (found.dataset.title, found.resourcedatatable.table_name)

    def test_platform_scope_with_sectors_leaves_out_other_sectors(
        self, settings: Any, make_dataset: Callable, make_resource: Callable, make_sector: Callable
    ) -> None:
        climate = make_sector("Climate Action")
        kept = make_resource(make_dataset("Rainfall", sectors=[climate]))
        other = make_resource(make_dataset("Anaemia"))
        settings.QE_PLATFORM_SECTORS = ["climate-action"]
        scope = resolve_scope("platform")

        assert get_resource_in_scope(kept.id, scope).id == kept.id
        with pytest.raises(NotFound):
            get_resource_in_scope(other.id, scope)
