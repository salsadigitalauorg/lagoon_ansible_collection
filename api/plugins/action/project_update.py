from ansible.errors import AnsibleError

from ..modules.project_update import ARGUMENT_SPEC
from . import LagoonClientActionBase

# openshift/kubernetes are Int in the patch but Openshift/Kubernetes objects
# on Project, so they need a sub-selection rather than a scalar.
OBJECT_PATCH_KEYS = ("openshift", "kubernetes")


def comparison_fields(patch: dict) -> list:
    """Field selection to compare a patch against the current project.

    Selects exactly the keys being patched, so the comparison works for
    every patchable key rather than a fixed subset. privateKey is never
    selected: reading a private key back into the comparison path and the
    task result is not worth doing, so a patch containing it is always
    treated as changed.
    """
    fields = []
    for key in patch:
        if key == "privateKey":
            continue
        if key in OBJECT_PATCH_KEYS:
            fields.append({key: ["id"]})
        else:
            fields.append(key)
    return fields


def current_value(project: dict, key: str):
    if key in OBJECT_PATCH_KEYS:
        return (project.get(key) or {}).get("id")
    return project.get(key)


class ActionModule(LagoonClientActionBase):
    argSpec = ARGUMENT_SPEC

    def execute(self, args, lagoon, result):
        name = args["project"]
        patch = args["values"]

        fields = ["id"] + comparison_fields(patch)
        project = lagoon.getProject(name, fields=fields)
        if project is None:
            raise AnsibleError(
                f"Unable to get details for project {name}; please make sure "
                "the project name is correct"
            )

        changed = "privateKey" in patch or any(
            str(value) != str(current_value(project, key))
            for key, value in patch.items()
            if key != "privateKey"
        )

        if not changed:
            result["update"] = project
            result["changed"] = False
            return

        result["update"] = lagoon.updateProject(project["id"], patch)
        result["changed"] = True
