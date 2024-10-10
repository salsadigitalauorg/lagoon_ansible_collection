from .gql import GqlClient
from .gqlResourceBase import ResourceBase

from gql.dsl import DSLFragment, DSLQuery
from typing import List


TASK_DEFINITION_FIELDS_COMMON = [
    'id',
    'type',
    'permission',
    'project',
    'environment',
    'name',
    'description',
    'service',
    'confirmationText',
    'groupName',
    'advancedTaskDefinitionArguments',
    'deployTokenInjection',
    'projectKeyInjection',
    'systemWide',
]

TASK_DEFINITION_FIELDS_COMMAND = [
    'command',
]

TASK_DEFINITION_FIELDS_IMAGE = [
    'image',
]

class TaskDefinition(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def get_definitions(self, project_id: int = None,
                        environment_id: int = None,
                        fields: List[str] = None) -> dict:

        if not fields or not len(fields):
            fields = TASK_DEFINITION_FIELDS_COMMON

        image_fields = fields + TASK_DEFINITION_FIELDS_IMAGE
        command_fields = fields + TASK_DEFINITION_FIELDS_COMMAND

        items = []
        with self.client as (_, ds):
            # Build the fragments.
            image_fragment = DSLFragment("Image")
            image_fragment.on(ds.AdvancedTaskDefinitionImage)
            image_fragment.select(
                getattr(ds.AdvancedTaskDefinitionImage, image_fields[0]))
            if len(image_fields) > 1:
                for f in image_fields[1:]:
                    if f == 'advancedTaskDefinitionArguments':
                        image_fragment.select(ds.AdvancedTaskDefinitionImage.advancedTaskDefinitionArguments.select(
                            ds.AdvancedTaskDefinitionArgument.id,
                            ds.AdvancedTaskDefinitionArgument.name,
                            ds.AdvancedTaskDefinitionArgument.displayName,
                            ds.AdvancedTaskDefinitionArgument.type,
                            ds.AdvancedTaskDefinitionArgument.range,
                        ))
                        continue
                    image_fragment.select(
                        getattr(ds.AdvancedTaskDefinitionImage, f))

            command_fragment = DSLFragment("Command")
            command_fragment.on(ds.AdvancedTaskDefinitionCommand)
            command_fragment.select(
                getattr(ds.AdvancedTaskDefinitionCommand, command_fields[0]))
            if len(command_fields) > 1:
                for f in command_fields[1:]:
                    if f == 'advancedTaskDefinitionArguments':
                        command_fragment.select(ds.AdvancedTaskDefinitionCommand.advancedTaskDefinitionArguments.select(
                            ds.AdvancedTaskDefinitionArgument.id,
                            ds.AdvancedTaskDefinitionArgument.name,
                            ds.AdvancedTaskDefinitionArgument.displayName,
                            ds.AdvancedTaskDefinitionArgument.type,
                            ds.AdvancedTaskDefinitionArgument.range,
                        ))
                        continue
                    command_fragment.select(
                        getattr(ds.AdvancedTaskDefinitionCommand, f))

            if (not project_id and not environment_id) or (
                project_id and not environment_id):
                dsl_query = ds.Query.allAdvancedTaskDefinitions.select(
                    image_fragment).select(command_fragment)
            else:
                dsl_query = ds.Query.advancedTasksForEnvironment(
                    environment=environment_id).select(
                        image_fragment).select(command_fragment)

            res = self.queryResources(
                image_fragment,
                command_fragment,
                DSLQuery(dsl_query))

            if not project_id and not environment_id:
                items = res["allAdvancedTaskDefinitions"]
            elif project_id and not environment_id:
                for td in res["allAdvancedTaskDefinitions"]:
                    if td["project"] == project_id:
                        items.append(td)
            else:
                items = res["advancedTasksForEnvironment"]

        return items

    def add_update_variables(self, task_type: str, permission: str,
                             project_id: int, environment_id: int, name: str,
                             description: str, service: str, image: str,
                             command: str, arguments: list,
                             deploy_token_injection: bool,
                             project_key_injection: bool,
                             system_wide: bool):
        variables = """
            $type: AdvancedTaskDefinitionTypes
            $permission: TaskPermission
            $name: String
            $description: String
            $service: String
            $arguments: [AdvancedTaskDefinitionArgumentInput]
            $deployTokenInjection: Boolean
            $projectKeyInjection: Boolean
            $systemWide: Boolean
        """
        variables_input = """
            type: $type
            permission: $permission
            name: $name
            description: $description
            service: $service
            advancedTaskDefinitionArguments: $arguments
            deployTokenInjection: $deployTokenInjection
            projectKeyInjection: $projectKeyInjection
            systemWide: $systemWide
        """
        variables_dict = {
            "type": task_type,
            "permission": permission,
            "name": name,
            "description": description,
            "service": service,
            "arguments": arguments,
            "deployTokenInjection": deploy_token_injection,
            "projectKeyInjection": project_key_injection,
            "systemWide": system_wide,
        }

        if project_id:
            variables += "    $project: Int\n"
            variables_input += "    project: $project\n"
            variables_dict["project"] = project_id

        if environment_id:
            variables += "    $environment: Int\n"
            variables_input += "    environment: $environment\n"
            variables_dict["environment"] = environment_id

        if task_type == "COMMAND":
            variables += "    $command: String\n"
            variables_input += "    command: $command\n"
            variables_dict["command"] = command
        elif task_type == "IMAGE":
            variables += "    $image: String\n"
            variables_input += "    image: $image\n"
            variables_dict["image"] = image

        return variables, variables_input, variables_dict

    def add(self, task_type: str, permission: str, project_id: int,
            environment_id: int, name: str, description: str, service: str,
            image: str, command: str, arguments: list,
            deploy_token_injection: bool, project_key_injection: bool,
            system_wide: bool) -> dict:

        variables, variables_input, variables_dict = self.add_update_variables(
            task_type, permission, project_id, environment_id, name,
            description, service, image, command, arguments,
            deploy_token_injection, project_key_injection, system_wide)

        res = self.client.execute_query(
            f"""
            mutation addAdvancedTaskDefinition(
                {variables}
            ) {{
                addAdvancedTaskDefinition(input: {{
                    {variables_input}
                }}) {{
                    ... on AdvancedTaskDefinitionCommand {{
                        id
                    }}
                    ... on AdvancedTaskDefinitionImage {{
                        id
                    }}
                }}
            }}""",
            variables_dict
        )
        return res['addAdvancedTaskDefinition']

    def update(self, id: int, task_type: str, permission: str, project_id: int,
            environment_id: int, name: str, description: str, service: str,
            image: str, command: str, arguments: list,
            deploy_token_injection: bool, project_key_injection: bool,
            system_wide: bool) -> dict:

        variables, variables_input, variables_dict = self.add_update_variables(
            task_type, permission, project_id, environment_id, name,
            description, service, image, command, arguments,
            deploy_token_injection, project_key_injection, system_wide)

        res = self.client.execute_query(
            f"""
            mutation updateAdvancedTaskDefinition(
                {variables}
            ) {{
                updateAdvancedTaskDefinition(input: {{
                    id: {id},
                    patch: {{
                        {variables_input}
                    }}
                }}) {{
                    ... on AdvancedTaskDefinitionCommand {{
                        id
                    }}
                    ... on AdvancedTaskDefinitionImage {{
                        id
                    }}
                }}
            }}""",
            variables_dict
        )
        return res['updateAdvancedTaskDefinition']

    def delete(self, definition_id: int) -> bool:
        res = self.client.execute_query(
            """
            mutation delete($id: Int!) {
                deleteAdvancedTaskDefinition(advancedTaskDefinition: $id)
            }""",
            {
                "id": definition_id,
            }
        )

        try:
            return res["deleteAdvancedTaskDefinition"] == "success"
        except KeyError:
            return False

