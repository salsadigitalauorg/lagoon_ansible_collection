"""Typed project methods, mixed into LagoonClient.

A mixin so the call surface stays flat - lagoon.getProject(...) - without one
module growing unmanageable. Every method returns plain data: no fluent
chaining, no accumulated instance state.

Each takes fields and extra_fields. fields replaces the method's default
selection; extra_fields adds to it, merging nested selections rather than
replacing them. Passing both raises ValueError.
"""

from collections.abc import Sequence
from typing import Any, Optional

from .fields import (
    CLUSTER_FIELDS,
    ENVIRONMENTS_FIELDS,
    GROUPS_FIELDS,
    PROJECT_FIELDS_NO_METADATA,
    PROJECT_LIST_FIELDS,
    VARIABLES_FIELDS,
    resolve_fields,
)


def sub(result: Any, key: str) -> Any:
    """result[key], or None if the result is absent or not a mapping."""
    try:
        return result[key]
    except (KeyError, TypeError):
        return None


class ProjectMethods:
    def listProjects(
        self,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[list]:
        """Enumerate projects. Selects name only unless told otherwise.

        The default is deliberately narrow: this is the one query that spans
        every project on the estate, and widening its selection is what makes
        it slow and then makes it fail. Everything else is fetched per project,
        where a wide selection on a single record is cheap.
        """

        return self.query(
            "allProjects",
            fields=resolve_fields(PROJECT_LIST_FIELDS, fields, extra_fields),
        )

    def listProjectsInGroup(
        self,
        group: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[list]:
        """Enumerate the projects in a group. Selects name only by default."""

        return self.query(
            "allProjectsInGroup",
            {"input": {"name": group}},
            resolve_fields(PROJECT_LIST_FIELDS, fields, extra_fields),
        )

    def getProject(
        self,
        name: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[dict]:
        """One project. Defaults to every scalar field except metadata."""

        return self.query(
            "projectByName",
            {"name": name},
            resolve_fields(PROJECT_FIELDS_NO_METADATA, fields, extra_fields),
        )

    def getProjectMetadata(self, name: str) -> Any:
        """A project's metadata, fetched on its own.

        metadata is a JSON scalar and so the one field on Project with no size
        bound. Keeping it off the main project request keeps that request
        predictable; merging the two results back together gives a project dict
        with the same keys as a single wide query would.
        """

        return sub(
            self.query("projectByName", {"name": name}, ["metadata"]), "metadata"
        )

    def getProjectEnvironments(
        self,
        name: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[list]:
        selection = resolve_fields(ENVIRONMENTS_FIELDS, fields, extra_fields)
        return sub(
            self.query("projectByName", {"name": name}, [{"environments": selection}]),
            "environments",
        )

    def getProjectGroups(
        self,
        name: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[list]:
        selection = resolve_fields(GROUPS_FIELDS, fields, extra_fields)
        return sub(
            self.query("projectByName", {"name": name}, [{"groups": selection}]),
            "groups",
        )

    def getProjectVariables(
        self,
        name: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[list]:
        selection = resolve_fields(VARIABLES_FIELDS, fields, extra_fields)

        # Read path: the response holds every variable value for this project,
        # none of them known in advance, so redacting by value cannot mask them
        # - this one has to stay muted. Do not "finish the migration" to
        # key-based redaction here.
        with self.silenced():
            result = self.query(
                "projectByName", {"name": name}, [{"envVariables": selection}]
            )

        return sub(result, "envVariables")

    def getProjectCluster(
        self,
        name: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[dict]:
        selection = resolve_fields(CLUSTER_FIELDS, fields, extra_fields)
        return sub(
            self.query("projectByName", {"name": name}, [{"kubernetes": selection}]),
            "kubernetes",
        )
