"""Layer 2: AI-search query bodies, ranking, cards and index planning (SQ1, RANK1–3, DOC1–2, IDX1–2)."""

import types
import uuid
from typing import Any, Callable, Dict, List
from unittest import mock

import pytest

from api.models import ResourceProfile, ResourceSchema, Tag
from api.services.query_engine.cards import build_cards, year_range
from api.services.query_engine.profiles import dataset_tables, save_resource_profile_if_current
from api.services.query_engine.scope import resolve_scope
from api.services.query_engine.search import build_search_filters
from api.services.query_engine.sync_steps import (
    IndexPlan,
    doc_body,
    plan_index_changes,
    stale_doc_ids,
)
from search.query_engine import index as search_index
from search.query_engine.index import DocState, IndexDimsMismatch, ensure_search_index
from search.query_engine.queries import keyword_body, search_filters, vector_body
from search.query_engine.ranking import Hit, group_by_dataset, is_weak_match, rrf_fuse

STATS: Dict[str, Any] = {
    "row_count": 4,
    "layout": "long",
    "analysable": True,
    "columns": [
        {
            "name": "District",
            "profiled": True,
            "kind": "text",
            "role": "geography_district",
            "top_values": [["Kamrup", 2], ["Nagaon", 2]],
            "geo": {
                "level": "district",
                "matched": ["Kamrup", "Nagaon"],
                "matched_count": 2,
                "parent_states": ["Assam"],
            },
        },
        {
            "name": "Round",
            "profiled": True,
            "kind": "text",
            "role": "time_fiscal_year",
            "time": {
                "kind": "fiscal_year",
                "values": ["2015-16", "2019-20"],
                "min": "2015-16",
                "max": "2019-20",
            },
        },
        {
            "name": "Anaemia (%)",
            "profiled": True,
            "kind": "numeric",
            "role": "measure",
            "min": 1.0,
            "max": 9.0,
        },
    ],
}


class TestQueryBodies:
    def test_both_legs_carry_the_same_filters(self) -> None:
        filters = search_filters(
            dataset_ids=["b", "a"], geographies=["Assam", "Kamrup"], year_from=2015, year_to=2019
        )
        keyword = keyword_body("anaemia", filters)
        vector = vector_body([0.1, 0.2], filters)
        assert keyword["query"]["bool"]["filter"] == vector["knn"]["filter"] == filters
        assert filters[0] == {"terms": {"dataset_id": ["a", "b"]}}
        assert (vector["knn"]["k"], vector["knn"]["num_candidates"], vector["size"]) == (
            50,
            200,
            50,
        )
        assert "embedding" not in keyword["_source"] and "embedding" not in vector["_source"]

    def test_the_keyword_leg_weights_titles(self) -> None:
        text = str(keyword_body("anaemia", []))
        assert "title^3" in text and "search_text" in text

    @pytest.mark.django_db
    def test_a_collaborative_scope_filters_by_its_dataset_ids(
        self, make_dataset: Callable, make_collaborative: Callable
    ) -> None:
        dataset = make_dataset()
        fem = make_collaborative(datasets=[dataset])
        filters = build_search_filters(resolve_scope(f"collaborative:{fem.public_id}"))
        assert filters == [{"terms": {"dataset_id": [str(dataset.id)]}}]

    @pytest.mark.django_db
    def test_platform_with_sectors_filters_by_their_slugs_and_sub_sectors(
        self, settings: Any, make_sector: Callable
    ) -> None:
        climate = make_sector("Climate Action")
        make_sector("Floods", parent=climate)
        make_sector("Health")
        settings.QE_PLATFORM_SECTORS = ["climate-action"]
        filters = build_search_filters(resolve_scope("platform"))
        assert filters == [{"terms": {"sectors": ["climate-action", "floods"]}}]

    @pytest.mark.django_db
    def test_places_expand_with_the_places_inside_them(self, geography: Any) -> None:
        filters = build_search_filters(resolve_scope("platform"), geographies=["Assam"])
        assert sorted(filters[0]["terms"]["geographies"]) == [
            "Assam",
            "Dibrugarh",
            "Kamrup",
            "Kamrup Metropolitan",
            "Nagaon",
        ]

    def test_platform_without_sectors_has_no_scope_filter(self) -> None:
        assert search_filters() == []


def leg(*doc_ids: str, scores: List[float] = None) -> Dict[str, Any]:
    scores = scores or [1.0] * len(doc_ids)
    return {
        "hits": {
            "hits": [
                {"_id": d, "_source": {"dataset_id": d.split(":")[-1].split("/")[0]}, "_score": s}
                for d, s in zip(doc_ids, scores)
            ]
        }
    }


class TestRanking:
    def test_fusion_matches_a_worked_example(self) -> None:
        # a: keyword 1 + vector 3 = 1/61 + 1/63; b: keyword 2 = 1/62; c: vector 1 = 1/61.
        fused = rrf_fuse(leg("d:a", "d:b"), leg("d:c", "d:x", "d:a"))
        assert [hit.doc_id for hit in fused] == ["d:a", "d:c", "d:b", "d:x"]
        assert fused[0].fused == pytest.approx(1 / 61 + 1 / 63)

    def test_ties_keep_the_order_first_seen_and_one_leg_hits_are_kept(self) -> None:
        fused = rrf_fuse(leg("d:a"), leg("d:b"))
        assert [hit.doc_id for hit in fused] == ["d:a", "d:b"]
        assert [hit.doc_id for hit in rrf_fuse(leg("d:a"), None)] == ["d:a"]

    def test_grouping_keeps_each_datasets_best_rank_and_three_tables(self) -> None:
        hits = [
            Hit(doc_id=f"r:{i}", source={"dataset_id": "one", "resource_id": str(i)})
            for i in range(5)
        ] + [Hit(doc_id="d:two", source={"dataset_id": "two"})]
        groups = group_by_dataset(hits, size=5)
        assert [g.dataset_id for g in groups] == ["one", "two"]
        assert [t.resource_id for t in groups[0].tables] == ["0", "1", "2"]
        assert group_by_dataset(hits, size=1)[0].dataset_id == "one"

    def test_weak_match_by_mode(self) -> None:
        strong = [Hit(doc_id="d:a", source={}, keyword_rank=1, vector_score=0.9, rerank_score=0.8)]
        poor = [Hit(doc_id="d:a", source={}, vector_rank=1, vector_score=0.3, rerank_score=0.05)]
        kwargs = {"rerank_threshold": 0.3, "similarity_threshold": 0.55}
        assert not is_weak_match(strong, reranked=True, vector_used=True, **kwargs)
        assert is_weak_match(poor, reranked=True, vector_used=True, **kwargs)
        assert is_weak_match(poor, reranked=False, vector_used=True, **kwargs)
        assert not is_weak_match(strong, reranked=False, vector_used=True, **kwargs)
        assert not is_weak_match(strong, reranked=False, vector_used=False, **kwargs)
        assert is_weak_match(poor, reranked=False, vector_used=False, **kwargs)
        assert is_weak_match([], reranked=True, vector_used=True, **kwargs)


@pytest.mark.django_db
class TestCards:
    def _dataset(
        self, make_dataset: Callable, make_resource: Callable, make_sector: Callable
    ) -> Any:
        climate = make_sector("Climate Action")
        floods = make_sector("Floods", parent=climate)
        dataset = make_dataset("Anaemia in Assam", sectors=[floods])
        dataset.tags.add(Tag.objects.create(value="nfhs"))
        table = make_resource(dataset, name="District indicators")
        ResourceSchema.objects.create(
            resource=table, field_name="Anaemia (%)", format="NUMBER", description="Women 15-49"
        )
        make_resource(dataset, name="Fact sheet (PDF)", with_table=False)
        save_resource_profile_if_current(table, table.resourcedatatable.id, STATS)
        return type(dataset).objects.get(pk=dataset.pk), table

    def _cards(self, dataset: Any) -> Any:
        from api.services.query_engine.corpus import sector_slugs_with_parents
        from api.services.query_engine.profiles import load_dataset_tables

        return build_cards(dataset, load_dataset_tables(dataset), sector_slugs_with_parents())

    def test_cards_carry_title_columns_coverage_places_and_sectors(
        self, make_dataset: Callable, make_resource: Callable, make_sector: Callable
    ) -> None:
        dataset, table = self._dataset(make_dataset, make_resource, make_sector)
        dataset_card, table_card = self._cards(dataset)

        assert dataset_card.doc_id == f"d:{dataset.id}"
        assert "Fact sheet (PDF)" in dataset_card.text and "nfhs" in dataset_card.text
        assert dataset_card.fields["sectors"] == ["climate-action", "floods"]
        assert table_card.doc_id == f"r:{table.id}"
        assert "Anaemia (%) — Women 15-49 — %" in table_card.text
        assert "2015-16 to 2019-20" in table_card.text and "Kamrup" in table_card.text
        assert (table_card.fields["year_min"], table_card.fields["year_max"]) == (2015, 2020)
        assert table_card.fields["geographies"] == ["Assam", "Kamrup", "Nagaon"]
        assert table_card.fields["analysable"] is True

    def test_card_hash_changes_with_summary_description_tags_and_model_only(
        self, settings: Any, make_dataset: Callable, make_resource: Callable, make_sector: Callable
    ) -> None:
        dataset, table = self._dataset(make_dataset, make_resource, make_sector)
        base = [c.card_hash for c in self._cards(dataset)]
        assert [c.card_hash for c in self._cards(dataset)] == base

        ResourceProfile.objects.filter(resource=table).update(
            facts_hash="f1", summary_facts_hash="f1", summary_text="Covers 2 districts."
        )
        with_summary = [c.card_hash for c in self._cards(type(dataset).objects.get(pk=dataset.pk))]
        assert with_summary[1] != base[1]

        ResourceSchema.objects.filter(resource=table).update(description="Children 6-59 months")
        described = [c.card_hash for c in self._cards(type(dataset).objects.get(pk=dataset.pk))]
        assert described[1] != with_summary[1]

        dataset.tags.add(Tag.objects.create(value="anaemia"))
        tagged = [c.card_hash for c in self._cards(type(dataset).objects.get(pk=dataset.pk))]
        assert tagged[0] != described[0]

        settings.QE_EMBEDDINGS_MODEL = "other/model"
        assert [c.card_hash for c in self._cards(type(dataset).objects.get(pk=dataset.pk))][
            0
        ] != tagged[0]

    def test_a_stale_summary_is_left_out(
        self, make_dataset: Callable, make_resource: Callable, make_sector: Callable
    ) -> None:
        dataset, table = self._dataset(make_dataset, make_resource, make_sector)
        ResourceProfile.objects.filter(resource=table).update(
            facts_hash="new", summary_facts_hash="old", summary_text="Written for older data."
        )
        _, table_card = self._cards(type(dataset).objects.get(pk=dataset.pk))
        assert table_card.fields["summary"] is None
        assert "older data" not in table_card.text


def test_year_range_reads_fiscal_ends() -> None:
    assert year_range(["2015-16", "2019-20"]) == (2015, 2020)
    assert year_range(["1901", "2020"]) == (1901, 2020)
    assert year_range([None]) == (None, None)


def card(doc_id: str, card_hash: str) -> Any:
    return types.SimpleNamespace(
        doc_id=doc_id, card_hash=card_hash, fields={"title": doc_id}, text=doc_id
    )


class TestIndexPlan:
    def test_new_and_changed_are_written_unchanged_skipped_missing_vectors_refilled(self) -> None:
        states = {
            "d:same": DocState("h1", True),
            "d:changed": DocState("old", True),
            "d:novector": DocState("h3", False),
            "d:gone": DocState("h4", True),
        }
        plan = IndexPlan(cap=10)
        cards = [
            card("d:same", "h1"),
            card("d:changed", "new"),
            card("d:novector", "h3"),
            card("d:new", "h5"),
        ]

        plan_index_changes(plan, cards, states, embeddings_on=True)

        assert [c.doc_id for c in plan.upserts] == ["d:changed", "d:new", "d:novector"]
        assert stale_doc_ids(plan, states) == ["d:gone"]

    def test_missing_vectors_are_not_refilled_when_embeddings_are_not_configured(self) -> None:
        plan = IndexPlan(cap=10)
        plan_index_changes(
            plan,
            [card("d:novector", "h3")],
            {"d:novector": DocState("h3", False)},
            embeddings_on=False,
        )
        assert plan.upserts == []

    def test_new_and_changed_documents_always_get_slots_before_vector_refills(self) -> None:
        # An embeddings outage left 3 documents without vectors; a new dataset arrives last.
        states = {f"d:old{i}": DocState("h", False) for i in range(3)}
        plan = IndexPlan(cap=2)
        plan_index_changes(
            plan, [card(f"d:old{i}", "h") for i in range(3)], states, embeddings_on=True
        )
        plan_index_changes(plan, [card("d:new", "h9")], states, embeddings_on=True)
        assert [c.doc_id for c in plan.upserts] == ["d:new", "d:old0"]

    def test_the_per_pass_cap_holds(self) -> None:
        plan = IndexPlan(cap=2)
        plan_index_changes(plan, [card(f"d:{i}", "h") for i in range(5)], {}, embeddings_on=True)
        assert len(plan.upserts) == 2 and plan.over_cap == 3

    def test_a_document_without_a_vector_says_so(self) -> None:
        body = doc_body(card("d:a", "h"), None)
        assert body["has_embedding"] is False and "embedding" not in body
        assert doc_body(card("d:a", "h"), [0.1])["embedding"] == [0.1]


class TestEnsureIndex:
    def fake_es(self, live: Any = "qe_catalog_v1", dims: int = 1536) -> mock.MagicMock:
        es = mock.MagicMock()
        es.indices.exists_alias.return_value = live is not None
        es.indices.get_alias.return_value = {live: {"aliases": {"qe_catalog": {}}}} if live else {}
        es.indices.get_mapping.return_value = {
            live: {
                "mappings": {"properties": {"embedding": {"type": "dense_vector", "dims": dims}}}
            }
        }
        return es

    def test_refuses_to_write_when_the_live_vector_size_differs(self, settings: Any) -> None:
        settings.QE_SEARCH_INDEX = "qe_catalog"
        with mock.patch.object(search_index, "_es", return_value=self.fake_es(dims=768)):
            with pytest.raises(IndexDimsMismatch):
                ensure_search_index(1536)

    def test_returns_the_live_index_when_sizes_match(self, settings: Any) -> None:
        settings.QE_SEARCH_INDEX = "qe_catalog"
        with mock.patch.object(
            search_index, "_es", return_value=self.fake_es(live="qe_catalog_v3")
        ):
            assert ensure_search_index(1536) == "qe_catalog_v3"

    def test_a_half_built_next_version_is_cleared_before_a_rebuild(self, settings: Any) -> None:
        settings.QE_SEARCH_INDEX = "qe_catalog"
        es = self.fake_es(live="qe_catalog_v1")
        with mock.patch.object(search_index, "_es", return_value=es):
            assert search_index.create_next_index(8) == ("qe_catalog_v2", "qe_catalog_v1")
        es.indices.delete.assert_called_once_with(index="qe_catalog_v2", ignore_unavailable=True)
        es.indices.create.assert_called_once()

    def test_creates_version_1_and_the_alias_when_missing(self, settings: Any) -> None:
        settings.QE_SEARCH_INDEX = "qe_catalog"
        es = self.fake_es(live=None)
        with mock.patch.object(search_index, "_es", return_value=es):
            assert ensure_search_index(8) == "qe_catalog_v1"
        es.indices.create.assert_called_once()
        es.indices.put_alias.assert_called_once_with(index="qe_catalog_v1", name="qe_catalog")


def test_the_ai_search_mapping_is_not_registered_with_django_elasticsearch_dsl() -> None:
    from pathlib import Path

    import search.documents as public_documents
    from django_elasticsearch_dsl.registries import registry

    names = {document.__module__ for document in registry.get_documents()}
    assert "search.documents.qe_catalog_document" not in names
    assert "qe_catalog" not in Path(public_documents.__file__).read_text()
