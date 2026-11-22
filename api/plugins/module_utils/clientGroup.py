"""Typed group methods, mixed into LagoonClient.

See clientProject for the fields/extra_fields convention.
"""

from collections.abc import Sequence
from typing import Any, Optional

from .fields import GROUPS_FIELDS, resolve_fields


class GroupMethods:
    def getGroup(
        self,
        name: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[dict]:
        """One group, by name. Defaults to id, name and type.

        groupByName returns GroupInterface, which declares id, name and type
        on the interface itself, so no inline fragments are needed. Unlike
        projectByName, a missing group errors rather than returning null;
        execute() already collapses an all-"not found" error list to null
        data, so this still returns None for a missing group with nothing on
        client.errors.
        """

        return self.query(
            "groupByName",
            {"name": name},
            resolve_fields(GROUPS_FIELDS, fields, extra_fields),
        )
