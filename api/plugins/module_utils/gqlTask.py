from .gql import GqlClient
from .gqlResourceBase import ResourceBase

from gql.dsl import DSLFragment, DSLQuery
from typing import List


TASK_DEFINITION_FIELDS_COMMON = [
    'project',
    'environment',
    'id',
    'name',
    'description',
    'permission',
    'type',
    'service',
    'confirmationText',
]

TASK_DEFINITION_FIELDS_COMMAND = [
    'command',
]

TASK_DEFINITION_FIELDS_IMAGE = [
    'image',
]

class Task(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def get_definitions(self, project_ids: List[int] = [], environment_ids: List[int] = [], fields: List[str] = None) -> dict:
        if len(project_ids) > 0 and len(environment_ids) > 0:
            raise Exception("Only one of project_ids or environment_ids should be provided")

        if not fields or not len(fields):
            fields = TASK_DEFINITION_FIELDS_COMMON

        image_fields = fields + TASK_DEFINITION_FIELDS_IMAGE
        command_fields = fields + TASK_DEFINITION_FIELDS_COMMAND

        items = {}
        with self.client as (_, ds):
            # Build the fragments.
            image_fragment = DSLFragment("Image")
            image_fragment.on(ds.AdvancedTaskDefinitionImage)
            image_fragment.select(
                getattr(ds.AdvancedTaskDefinitionImage, image_fields[0]))
            if len(image_fields) > 1:
                for f in image_fields[1:]:
                    image_fragment.select(
                        getattr(ds.AdvancedTaskDefinitionImage, f))

            command_fragment = DSLFragment("Command")
            command_fragment.on(ds.AdvancedTaskDefinitionCommand)
            command_fragment.select(
                getattr(ds.AdvancedTaskDefinitionCommand, command_fields[0]))
            if len(command_fields) > 1:
                for f in command_fields[1:]:
                    command_fragment.select(
                        getattr(ds.AdvancedTaskDefinitionCommand, f))

            items = self.queryResources(
                image_fragment,
                command_fragment,
                DSLQuery(
                    ds.Query.allAdvancedTaskDefinitions.select(
                        image_fragment).select(command_fragment)))

        return items

