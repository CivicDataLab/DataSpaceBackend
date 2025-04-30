"""GraphQL schema for authorization module.

This file is a thin wrapper around the schema package for backward compatibility.
"""

from authorization.schema import Mutation, Query

__all__ = ["Query", "Mutation"]
