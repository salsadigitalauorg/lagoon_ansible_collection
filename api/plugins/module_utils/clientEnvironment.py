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
    DEPLOYMENTS_FIELDS,
    ENVIRONMENTS_FIELDS,
    VARIABLES_FIELDS,
    check_name,
    render_fields,
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

    def getEnvironmentDeployments(
        self,
        namespace: str,
        fields: Optional[Sequence[Any]] = None,
        extra_fields: Optional[Sequence[Any]] = None,
        limit: Optional[int] = None,
        raise_on_error: Optional[bool] = None,
    ) -> Optional[list]:
        """An environment's deployments, newest first.

        Environment.deployments(limit: Int) takes an argument, which a field
        spec cannot express - see render_fields' documented limitation - so
        this writes its own document rather than going through query().
        limit=None serialises as a JSON null, which GraphQL treats as
        "argument not supplied", so one code path covers both. Returns None
        when the environment itself does not exist, distinct from [] for one
        with no deployments.
        """

        selection = resolve_fields(DEPLOYMENTS_FIELDS, fields, extra_fields)
        check_name(BY_NAMESPACE)
        document = (
            "query environmentDeployments"
            "($kubernetesNamespaceName: String!, $limit: Int) "
            f"{{ {BY_NAMESPACE}(kubernetesNamespaceName: $kubernetesNamespaceName) "
            f"{{ deployments(limit: $limit) {{ {render_fields(selection)} }} }} }}"
        )
        data = self.execute(
            document,
            {"kubernetesNamespaceName": namespace, "limit": limit},
            raise_on_error,
        )
        return sub((data or {}).get(BY_NAMESPACE), "deployments")
