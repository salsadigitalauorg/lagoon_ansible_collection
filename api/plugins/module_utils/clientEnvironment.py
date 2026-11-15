"""Typed environment methods, mixed into LagoonClient.

Environments are addressed by Kubernetes namespace name, which is what the
inventory keys hosts on. See clientProject for the fields/extra_fields
convention.
"""

from collections.abc import Sequence
from typing import Any, Optional

from .clientProject import sub
from .fields import (
    CLUSTER_FIELDS,
    ENVIRONMENTS_FIELDS,
    VARIABLES_FIELDS,
    resolve_fields,
)

BY_NAMESPACE = "environmentByKubernetesNamespaceName"


class EnvironmentMethods:
    def getEnvironment(
        self,
        namespace: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[dict]:
        return self.query(
            BY_NAMESPACE,
            {"kubernetesNamespaceName": namespace},
            resolve_fields(ENVIRONMENTS_FIELDS, fields, extra_fields),
        )

    def getEnvironmentCluster(
        self,
        namespace: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[dict]:
        selection = resolve_fields(CLUSTER_FIELDS, fields, extra_fields)
        return sub(
            self.query(
                BY_NAMESPACE,
                {"kubernetesNamespaceName": namespace},
                [{"kubernetes": selection}],
            ),
            "kubernetes",
        )

    def getEnvironmentVariables(
        self,
        namespace: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
    ) -> Optional[list]:
        selection = resolve_fields(VARIABLES_FIELDS, fields, extra_fields)

        # Read path: the response holds every variable value for this
        # environment, none of them known in advance, so redacting by value
        # cannot mask them - this one has to stay muted. Do not "finish the
        # migration" to key-based redaction here.
        with self.silenced():
            result = self.query(
                BY_NAMESPACE,
                {"kubernetesNamespaceName": namespace},
                [{"envVariables": selection}],
            )

        return sub(result, "envVariables")
