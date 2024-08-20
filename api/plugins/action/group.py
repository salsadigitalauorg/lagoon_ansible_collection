from . import LagoonMutationActionBase, MutationConfig, MutationActionConfig
from ..module_utils.gql import ProxyLookup


class ActionModule(LagoonMutationActionBase):

  actionConfig = MutationActionConfig(
    name="group",
    add=MutationConfig(
      field="addGroup",
      proxyLookups=[ProxyLookup(query="groupByName")],
      lookupCompareFields=["name"],
    ),
    delete=MutationConfig(field="deleteGroup"),
  )
