"""Authorization GraphQL schema package."""

from authorization.schema.mutation import Mutation
from authorization.schema.query import Query

__all__ = ["Query", "Mutation"]
