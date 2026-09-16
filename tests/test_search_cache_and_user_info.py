"""Regression tests for the two 500s on /api/auth/user/info/ and /api/search/aimodel/."""

import pickle

import pytest
from elasticsearch_dsl import InnerDoc
from elasticsearch_dsl.utils import AttrDict, AttrList
from rest_framework.test import APIRequestFactory

from api.views.auth import UserInfoView
from api.views.paginated_elastic_view import as_plain_data


def nested_doc(**fields: object) -> InnerDoc:
    """Build a nested doc the way elasticsearch_dsl does for a nested field.

    The class is rebuilt per document type rather than being the module-level
    InnerDoc, which is exactly what pickle refuses to serialize.
    """
    cls = type("InnerDoc", (InnerDoc,), {})
    cls.__module__ = "elasticsearch_dsl.document"
    doc = cls()
    for name, value in fields.items():
        setattr(doc, name, value)
    return doc


@pytest.mark.django_db
def test_user_info_rejects_anonymous_request() -> None:
    """Anonymous callers get 401, not a 500 from reading .email off AnonymousUser.

    The view is called directly: routing it through the test client hides the
    bug, because the test settings drop the Keycloak middleware.
    """
    request = APIRequestFactory().get("/api/auth/user/info/")
    response = UserInfoView.as_view()(request)
    assert response.status_code == 401


def test_as_plain_data_makes_search_results_picklable() -> None:
    """Nested hits must survive cache.set, which pickles the cached value."""
    result = {
        "results": [
            {
                "all_providers": AttrList([nested_doc(provider="GPT")]),
                "name": AttrDict({"raw": "x"}),
            }
        ],
        "total": 1,
    }

    plain = as_plain_data(result)
    assert pickle.loads(pickle.dumps(plain)) == plain
    assert plain["results"][0]["all_providers"] == [{"provider": "GPT"}]
    assert plain["results"][0]["name"] == {"raw": "x"}
    assert not _holds_elastic_objects(plain)


def _holds_elastic_objects(value: object) -> bool:
    """The cache pickles what it is given, so no wrapper may survive anywhere."""
    if isinstance(value, (AttrDict, AttrList, InnerDoc)):
        return True
    if isinstance(value, dict):
        return any(_holds_elastic_objects(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_holds_elastic_objects(item) for item in value)
    return False
