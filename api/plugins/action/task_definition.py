from . import LagoonMutationActionBase, MutationConfig, MutationActionConfig
from ..module_utils.gql import ProxyLookup


class ActionModule(LagoonMutationActionBase):

    actionConfig = MutationActionConfig(
        name='task_definition',

        # Configuration for adding a new task definition.
        add=MutationConfig(
            # GraphQL Mutation for adding a new task definition.
            field="addAdvancedTaskDefinition",

            # GraphQL Mutation for updating an existing task definition.
            updateField="updateAdvancedTaskDefinition",

            # Additional arguments to be allowed when calling the action
            # plugin. These arguments will not be passed to the GraphQL
            # mutation, but would instead be used to lookup a project by name
            # in one of the proxy lookups.
            inputFieldAdditionalArgs=dict(project_name=dict(type="str")),

            # Aliases for the input fields - in this case used to maintain
            # compatibility with the previous version of the plugin.
            inputFieldArgsAliases=dict(
                type=["task_type"],
                advancedTaskDefinitionArguments=["arguments"],
            ),

            # Proxy lookups to be used when looking for existing task
            # definitions. A first pass is done through the lookups in the
            # order they are provided, to find one that matches the input
            # of the plugin. The first one matched is then used to query
            # task definitions and compare them with the input, using the
            # lookupCompareFields and diffCompareFields.
            proxyLookups=[
                # Will use 'id' if provided to lookup a task definition by id.
                ProxyLookup(query="advancedTaskDefinitionById"),

                # Will use 'environment' id if provided to find all task
                # definitions by environment id, then filter by the fields
                # in lookupCompareFields.
                ProxyLookup(query="advancedTasksForEnvironment"),

                # Will use 'project_name' if provided to find all task
                # definitions for a project through projectByName, selecting
                # the fields in selectFields recursively, then filter by the
                # fields in lookupCompareFields.
                # This would be similar to the following:
                #   query {
                #     projectByName(project_name: "{{ project_name }}") {
                #       environments {
                #         advancedTasks {
                #           id
                #           ...
                #         }
                #       }
                #     }
                #   }
                ProxyLookup(query="projectByName",
                            inputArgFields={"project_name": "name"},
                            selectFields=["environments", "advancedTasks"],
                ),
            ],

            # These fields are used to determine whether the task definition
            # already exists.
            lookupCompareFields=["name"],

            # These fields are used to determine whether the task definition
            # needs to be updated. If any of the values of these fields are
            # different between the existing task definition and the input,
            # the task definition will be updated.
            diffCompareFields=[
                "permission",
                "description",
                "service",
                "advancedTaskDefinitionArguments",
                "deployTokenInjection",
                "projectKeyInjection",
            ],
        ),

        # Configuration for deleting a task definition.
        delete=MutationConfig(field="deleteAdvancedTaskDefinition"),
    )
