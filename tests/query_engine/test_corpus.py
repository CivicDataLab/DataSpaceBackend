"""Layer 1: which datasets and tables the query engine may see (E1–E3, S6, S8, C-LOAD)."""

from typing import Any, Callable, List

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from api.models import Dataset, Resource, Tag
from api.services.query_engine.corpus import (
    analysable_resource_q,
    load_corpus,
    platform_scope_q,
    processing_set_q,
)
from api.utils.dataset_access import public_published_datasets_q
from api.utils.enums import (
    CollaborativeStatus,
    DatasetAccessType,
    DatasetStatus,
    DatasetType,
    UseCaseStatus,
)


def corpus_ids() -> set:
    return set(Dataset.objects.filter(public_published_datasets_q()).values_list("id", flat=True))


def analysable_ids() -> set:
    return set(Resource.objects.filter(analysable_resource_q()).values_list("id", flat=True))


@pytest.mark.django_db
class TestCorpus:
    def test_includes_a_published_public_data_dataset_and_its_active_table(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        dataset = make_dataset()
        resource = make_resource(dataset)

        assert corpus_ids() == {dataset.id}
        assert analysable_ids() == {resource.id}

    @pytest.mark.parametrize(
        "changes",
        [
            {"status": DatasetStatus.DRAFT},
            {"status": DatasetStatus.ARCHIVED},
            {"access_type": DatasetAccessType.PRIVATE},
            {"access_type": DatasetAccessType.RESTRICTED},
            {"dataset_type": DatasetType.PROMPT},
        ],
        ids=["draft", "archived", "private", "restricted", "prompt"],
    )
    def test_leaves_out_datasets_that_are_not_published_public_data(
        self, make_dataset: Callable, make_resource: Callable, changes: dict
    ) -> None:
        dataset = make_dataset(**changes)
        make_resource(dataset)

        assert corpus_ids() == set()
        assert analysable_ids() == set()

    def test_leaves_out_an_inactive_resource(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        make_resource(make_dataset(), is_active=False)
        assert analysable_ids() == set()

    def test_leaves_out_a_resource_without_a_data_table(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        # A PDF, a failed index and a platform-import link all look like this: no table row.
        make_resource(make_dataset(), name="Report (PDF)", with_table=False)
        assert analysable_ids() == set()

    def test_a_dataset_without_tables_is_in_the_corpus_but_has_nothing_analysable(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        dataset = make_dataset()
        make_resource(dataset, name="Report (PDF)", with_table=False)

        assert corpus_ids() == {dataset.id}
        assert analysable_ids() == set()


@pytest.mark.django_db
class TestPlatformScope:
    def test_with_no_sectors_configured_platform_scope_is_the_whole_corpus(
        self, make_dataset: Callable, make_sector: Callable
    ) -> None:
        climate = make_sector("Climate Action")
        inside = make_dataset("Rainfall", sectors=[climate])
        no_sector = make_dataset("Literacy")

        found = set(Dataset.objects.filter(platform_scope_q()).values_list("id", flat=True))
        assert found == {inside.id, no_sector.id}

    def test_sector_setting_keeps_its_datasets_and_sub_sectors_only(
        self, settings: Any, make_dataset: Callable, make_sector: Callable
    ) -> None:
        climate = make_sector("Climate Action")
        floods = make_sector("Floods", parent=climate)
        health = make_sector("Health")
        in_sector = make_dataset("Rainfall", sectors=[climate])
        in_sub_sector = make_dataset("Flood damage", sectors=[floods])
        both = make_dataset("Heat and health", sectors=[health, climate])
        make_dataset("Anaemia", sectors=[health])
        make_dataset("Draft rainfall", status=DatasetStatus.DRAFT, sectors=[climate])
        settings.QE_PLATFORM_SECTORS = ["climate-action"]

        found = list(Dataset.objects.filter(platform_scope_q()).values_list("id", flat=True))
        assert sorted(found) == sorted([in_sector.id, in_sub_sector.id, both.id])

    def test_reaches_resources_through_a_prefix(
        self, settings: Any, make_dataset: Callable, make_resource: Callable, make_sector: Callable
    ) -> None:
        climate = make_sector("Climate Action")
        kept = make_resource(make_dataset("Rainfall", sectors=[climate]))
        make_resource(make_dataset("Anaemia"))
        settings.QE_PLATFORM_SECTORS = ["climate-action"]

        found = Resource.objects.filter(platform_scope_q(prefix="dataset__"))
        assert list(found.values_list("id", flat=True)) == [kept.id]


@pytest.mark.django_db
class TestProcessingSet:
    def test_is_platform_scope_plus_enabled_collaboratives_without_duplicates(
        self,
        settings: Any,
        make_dataset: Callable,
        make_sector: Callable,
        make_collaborative: Callable,
    ) -> None:
        climate = make_sector("Climate Action")
        rainfall = make_dataset("Rainfall", sectors=[climate])
        anaemia = make_dataset("Anaemia")
        literacy = make_dataset("Literacy")
        private = make_dataset("Private survey", access_type=DatasetAccessType.PRIVATE)
        fem = make_collaborative("FemHealth", datasets=[anaemia, rainfall, private])
        make_collaborative("Other", datasets=[literacy])
        settings.QE_PLATFORM_SECTORS = ["climate-action"]
        settings.QE_ENABLED_COLLABORATIVES = [fem.public_id]

        found = list(Dataset.objects.filter(processing_set_q()).values_list("id", flat=True))
        assert sorted(found) == sorted([rainfall.id, anaemia.id])

    def test_includes_the_datasets_of_enabled_collaboratives_published_use_cases(
        self,
        settings: Any,
        make_dataset: Callable,
        make_sector: Callable,
        make_use_case: Callable,
        make_collaborative: Callable,
    ) -> None:
        make_sector("Climate Action")
        tenders = make_dataset("MCH tenders")
        drafted = make_dataset("Draft use case data")
        literacy = make_dataset("Literacy")
        fem = make_collaborative(
            "FemHealth",
            use_cases=[
                make_use_case("MCH gaps", datasets=[tenders]),
                make_use_case("Drafted", status=UseCaseStatus.DRAFT, datasets=[drafted]),
            ],
        )
        make_collaborative("Other", use_cases=[make_use_case("Schools", datasets=[literacy])])
        settings.QE_PLATFORM_SECTORS = ["climate-action"]
        settings.QE_ENABLED_COLLABORATIVES = [fem.public_id]

        found = list(Dataset.objects.filter(processing_set_q()).values_list("id", flat=True))
        assert found == [tenders.id]

    def test_with_no_collaboratives_listed_every_published_collaborative_counts(
        self,
        settings: Any,
        make_dataset: Callable,
        make_sector: Callable,
        make_collaborative: Callable,
    ) -> None:
        make_sector("Climate Action")
        anaemia = make_dataset("Anaemia")
        literacy = make_dataset("Literacy")
        make_collaborative("FemHealth", datasets=[anaemia])
        make_collaborative("Draft one", status=CollaborativeStatus.DRAFT, datasets=[literacy])
        settings.QE_PLATFORM_SECTORS = ["climate-action"]

        found = list(Dataset.objects.filter(processing_set_q()).values_list("id", flat=True))
        assert found == [anaemia.id]


@pytest.mark.django_db
class TestLoadCorpus:
    def _seed(self, count: int, make_dataset: Callable, make_resource: Callable) -> None:
        tag = Tag.objects.create(value="health")
        for index in range(count):
            dataset = make_dataset(f"Dataset {index}")
            dataset.tags.add(tag)
            make_resource(dataset, name=f"Table {index}")
            make_resource(dataset, name=f"Report {index}", with_table=False)

    def _queries_per_chunk(self, chunk_size: int) -> List[int]:
        counts = []
        chunks = load_corpus(chunk_size=chunk_size)
        while True:
            with CaptureQueriesContext(connection) as captured:
                try:
                    chunk = next(chunks)
                except StopIteration:
                    break
                # Touch everything the sync pass reads, so a missing prefetch shows up here.
                for dataset in chunk:
                    _ = dataset.organization and dataset.organization.name
                    _ = [t.value for t in dataset.tags.all()]
                    _ = [s.name for s in dataset.sectors.all()]
                    _ = [g.name for g in dataset.geographies.all()]
                    for resource in dataset.resources.all():
                        _ = getattr(resource, "resourcedatatable", None)
                        _ = [c.field_name for c in resource.resourceschema_set.all()]
            counts.append(len(captured))
        return counts

    def test_runs_the_same_number_of_queries_per_chunk_whatever_its_size(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        self._seed(6, make_dataset, make_resource)

        small = self._queries_per_chunk(chunk_size=2)
        large = self._queries_per_chunk(chunk_size=6)

        assert len(small) == 3
        assert len(set(small)) == 1
        assert small[0] == large[0]

    def test_yields_every_dataset_in_the_processing_set_once(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        self._seed(5, make_dataset, make_resource)
        make_dataset("Draft", status=DatasetStatus.DRAFT)

        seen = [dataset.title for chunk in load_corpus(chunk_size=2) for dataset in chunk]
        assert sorted(seen) == [f"Dataset {i}" for i in range(5)]
