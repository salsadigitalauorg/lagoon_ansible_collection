from . import LagoonMutationActionBase, MutationConfig, MutationActionConfig
from ..module_utils.gql import ProxyLookup


class ActionModule(LagoonMutationActionBase):

    actionConfig = MutationActionConfig(
        name="task_invoke",
        # Configuration for invoking a registered task.
        add=MutationConfig(
            # GraphQL Mutation for invoking a registered task.
            field="invokeRegisteredTask",
            # Additional arguments to be allowed when calling the action
            # plugin.
            inputFieldArgsAliases=dict(
                argumentValues=["arguments"],
                environment=["project"],
                taskRegistration=["task"]
            )
        ),
        delete=None
    )
