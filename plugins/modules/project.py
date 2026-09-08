#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
module: project
short_description: Manage a Lagoon project
description:
  - Creates, updates and deletes a Lagoon project.
  - >-
    Options are the union of Lagoon's C(AddProjectInput) and
    C(UpdateProjectPatchInput) types, so one task shape serves create,
    update and delete. Options accepted only when creating, or only when
    updating, are marked as such below.
  - >-
    Only O(name) is always required. O(git_url) and O(production_environment)
    are required by Lagoon when creating a project and are checked on that
    path only, so an update touching one unrelated option does not have to
    repeat them.
  - Supports check mode and diff mode.
version_added: "3.0.0"
options:
  state:
    description:
    - V(present) creates the project if absent, or updates it to match the
      supplied options.
    - V(absent) deletes the project if it exists.
    type: str
    default: present
    choices: [present, absent]
  name:
    description:
    - Name of the project. Used to look the project up and to delete it.
    type: str
    required: true
  git_url:
    description:
    - Git URL of the project, which must be an SSH Git URL, for example
      V(git@github.com:example/repo.git) or
      V(ssh://git@github.com:2222/example/repo.git).
    - Required by Lagoon when creating a project.
    type: str
  subfolder:
    description:
    - Set if the C(.lagoon.yml) is in a subfolder of the repository, which
      is useful when one repository holds multiple Lagoon projects.
    type: str
  router_pattern:
    description:
    - Set if the project should use a router pattern that differs from the
      deploy target default.
    type: str
  openshift:
    description:
    - ID of the deploy target (Kubernetes or OpenShift cluster) the project
      should be deployed to.
    type: int
  openshift_project_pattern:
    description:
    - Pattern of the OpenShift project/namespace to generate.
    - Deprecated by Lagoon and no longer in use, but still accepted by the
      API.
    type: str
  kubernetes:
    description:
    - ID of the deploy target (Kubernetes cluster) the project should be
      deployed to.
    type: int
  kubernetes_namespace_pattern:
    description:
    - Pattern of the Kubernetes namespace to generate.
    - Deprecated by Lagoon and no longer in use, but still accepted by the
      API.
    type: str
  active_systems_deploy:
    description:
    - Name of the system handling deploy actions for the project.
    - Deprecated by Lagoon and no longer in use, but still accepted by the
      API.
    type: str
  active_systems_promote:
    description:
    - Name of the system handling promote actions for the project.
    - Deprecated by Lagoon and no longer in use, but still accepted by the
      API.
    type: str
  active_systems_remove:
    description:
    - Name of the system handling remove actions for the project.
    - Deprecated by Lagoon and no longer in use, but still accepted by the
      API.
    type: str
  active_systems_task:
    description:
    - Name of the system handling task actions for the project.
    - Deprecated by Lagoon and no longer in use, but still accepted by the
      API.
    type: str
  active_systems_misc:
    description:
    - Name of the system handling miscellaneous actions for the project.
    - Deprecated by Lagoon and no longer in use, but still accepted by the
      API.
    type: str
  branches:
    description:
    - Which branches should be deployed. V(true) deploys all branches,
      V(false) deploys none, or supply a regular expression matching the
      branches to deploy, for example V(^(main|staging)$).
    type: str
  pullrequests:
    description:
    - Which pull requests should be deployed. V(true) deploys all pull
      requests, V(false) deploys none, or supply a regular expression
      matching the pull request titles to deploy, for example V([BUILD]).
    type: str
  production_environment:
    description:
    - Name of the environment to mark as the production environment.
    - Required by Lagoon when creating a project.
    - Changing this requires deploying both the current and the previous
      production environment for the change to propagate correctly.
    type: str
  production_routes:
    description:
    - Routes attached to the active environment.
    type: str
  production_alias:
    description:
    - Drush alias of the active production environment.
    type: str
  standby_production_environment:
    description:
    - Name of the environment to mark as the standby production
      environment.
    type: str
  standby_routes:
    description:
    - Routes attached to the standby environment.
    type: str
  standby_alias:
    description:
    - Drush alias of the standby production environment.
    type: str
  availability:
    description:
    - Availability level of the project.
    type: str
    choices: [STANDARD, HIGH, POLYSITE]
  auto_idle:
    description:
    - Whether the project should have auto idling enabled. V(1) enables it,
      V(0) disables it.
    type: int
  storage_calc:
    description:
    - Whether storage for the project should be calculated. V(1) enables
      calculation, V(0) disables it.
    type: int
  development_environments_limit:
    description:
    - How many development environments may be deployed at one time.
    type: int
  private_key:
    description:
    - SSH private key used to authenticate against the project's Git
      repository. Sensitive.
    - >-
      Write only. This module never reads the stored key back, so it
      cannot detect drift in a key already held by Lagoon. Supplying this
      option reports a change without either value appearing in diff
      output.
    - Lagoon generates a key pair server-side when none is supplied.
    type: str
  problems_ui:
    description:
    - Whether the Problems UI should be available for the project. V(1)
      enables it, V(0) disables it.
    type: int
  facts_ui:
    description:
    - Whether the Facts UI should be available for the project. V(1)
      enables it, V(0) disables it.
    type: int
  production_build_priority:
    description:
    - Build priority of the production environment, V(0) through V(10).
    type: int
  development_build_priority:
    description:
    - Build priority of development environments, V(0) through V(10).
    type: int
  deployments_disabled:
    description:
    - Whether deploying environments is disabled for the project. V(1)
      disables deployments, V(0) allows them.
    - Deprecated by Lagoon in favour of O(restrictions), but still
      accepted by the API.
    type: int
  organization:
    description:
    - ID of the organization the project belongs to.
    - >-
      Accepted only when creating a project. Supplying it for an existing
      project succeeds when it already matches, and fails otherwise --
      this module never moves a project between organizations, because the
      only mutations that could are deprecated or destructive beyond this
      one field.
    type: int
  add_org_owner:
    description:
    - Whether to add the requesting user as an owner of the project within
      its organization.
    - >-
      Accepted only when creating a project. Lagoon exposes no readable
      counterpart, so this module cannot confirm it already applies and
      fails rather than guess when it is supplied for an existing project.
    type: bool
  build_image:
    description:
    - Build image the project should use.
    type: str
  shared_baas_bucket:
    description:
    - Whether the project should use a shared backup bucket rather than a
      dedicated one.
    type: bool
  autogenerated_routes:
    description:
    - Whether autogenerated routes are enabled for the project.
    - Applied only when updating an existing project.
    type: bool
  autogenerated_routes_pullrequests:
    description:
    - Whether autogenerated routes are created for pull request
      environments.
    - Applied only when updating an existing project.
    type: bool
  autogenerated_route_prefixes:
    description:
    - Prefixes to add to the project's autogenerated routes.
    - Applied only when updating an existing project.
    type: list
    elements: str
  autogenerated_path_routes:
    description:
    - Path-based routes to add to the project's autogenerated routes.
    - Applied only when updating an existing project.
    type: list
    elements: dict
    suboptions:
      from_service:
        description: Service the request is routed from.
        type: str
      to_service:
        description: Service the request is routed to.
        type: str
      path:
        description: Path to route, for example V(/api).
        type: str
  disable_request_verification:
    description:
    - Whether to disable request verification on the project's
      autogenerated routes.
    - >-
      Request verification can stop an idling environment from waking on
      requests that do not come from a browser. Disabling it lets any
      request wake the environment.
    - Applied only when updating an existing project.
    type: bool
  restrictions:
    description:
    - Actions to restrict for the project.
    - Applied only when updating an existing project.
    type: list
    elements: str
    choices:
    - NO_PROJECT_VARIABLES
    - NO_ENVIRONMENT_VARIABLES
    - NO_TASKS
    - NO_DEPLOYMENTS
    - NO_WEBHOOK_DEPLOYMENTS
extends_documentation_fragment:
  - salsadigitalauorg.lagoon.auth
author:
  - Salsa Digital (@salsadigitalauorg)
'''

EXAMPLES = r'''
- name: Create a project.
  salsadigitalauorg.lagoon.project:
    name: my-project
    git_url: git@github.com:example/my-project.git
    production_environment: main
    branches: ^(main|staging)$

- name: Update a project's idling and environment limit.
  salsadigitalauorg.lagoon.project:
    name: my-project
    auto_idle: 1
    development_environments_limit: 5

- name: Set a project's deploy target.
  salsadigitalauorg.lagoon.project:
    name: my-project
    openshift: 2

- name: Add path routes to a project's autogenerated routes.
  salsadigitalauorg.lagoon.project:
    name: my-project
    autogenerated_path_routes:
      - from_service: nginx
        to_service: api
        path: /api

- name: Restrict a project from running tasks.
  salsadigitalauorg.lagoon.project:
    name: my-project
    restrictions:
      - NO_TASKS

- name: Preview a change without applying it.
  salsadigitalauorg.lagoon.project:
    name: my-project
    auto_idle: 0
  check_mode: true
  diff: true

- name: Delete a project.
  salsadigitalauorg.lagoon.project:
    name: my-project
    state: absent
'''

RETURN = r'''
project:
  description:
  - The project's state after the task ran.
  - V(none) after the project is deleted.
  - >-
    C(privateKey) is never included. This module does not read stored key
    material back from Lagoon.
  returned: success
  type: dict
  sample:
    id: 42
    name: my-project
    gitUrl: git@github.com:example/my-project.git
    productionEnvironment: main
    autoIdle: 1
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    import auth
from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    .client import LagoonClient
from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    import errors
from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    .resource import LagoonResourceModule, camel_to_snake

# Wire (camelCase) field names participating in read/diff/report: the
# union of AddProjectInput and UpdateProjectPatchInput. One flat argspec
# serves create, update and delete, so this union -- not either input
# type alone -- is what the user sees.
_FIELDS = (
    'id', 'name', 'gitUrl', 'subfolder', 'routerPattern', 'openshift',
    'openshiftProjectPattern', 'kubernetes', 'kubernetesNamespacePattern',
    'activeSystemsDeploy', 'activeSystemsPromote', 'activeSystemsRemove',
    'activeSystemsTask', 'activeSystemsMisc', 'branches', 'pullrequests',
    'productionEnvironment', 'productionRoutes', 'productionAlias',
    'standbyProductionEnvironment', 'standbyRoutes', 'standbyAlias',
    'availability', 'autoIdle', 'storageCalc',
    'developmentEnvironmentsLimit', 'privateKey', 'problemsUi', 'factsUi',
    'productionBuildPriority', 'developmentBuildPriority',
    'deploymentsDisabled', 'organization', 'addOrgOwner', 'buildImage',
    'sharedBaasBucket', 'autogeneratedRoutes',
    'autogeneratedRoutesPullrequests', 'autogeneratedRoutePrefixes',
    'autogeneratedPathRoutes', 'disableRequestVerification', 'restrictions',
)

# id is UpdateProjectInput's own update key (`id: Int!`, wrapping
# UpdateProjectPatchInput), not a field on either input's flat payload --
# it is read from the current state for _update()/_delete() to use, never
# supplied by a caller, and never diffed.
_DIFF_IGNORE = ('id',)

# privateKey is readable on Project but deliberately never selected --
# see _READ_SELECTION. Kept here so its diff reports the changed/unchanged
# fact without either side's value.
_NO_LOG_FIELDS = ('privateKey',)

# Present on AddProjectInput but not UpdateProjectPatchInput. Supplying one
# against an existing project is enforced by _check_create_only(). Derived
# against UpdateProjectInput's *patch* type deliberately excludes id: id
# lives on the update wrapper, not the patch, so it is the update key
# rather than a create-only field and never belongs in this tuple.
_CREATE_ONLY = ('organization', 'addOrgOwner')

# Present on UpdateProjectPatchInput only.
_UPDATE_ONLY = (
    'autogeneratedRoutes', 'autogeneratedRoutesPullrequests',
    'autogeneratedRoutePrefixes', 'autogeneratedPathRoutes',
    'disableRequestVerification', 'restrictions',
)

# AddProjectInput's NonNull fields other than `name`. Enforced on the
# create path only: `name` is the read/delete key and is argspec-required,
# but requiring these two in the argspec would also require them for
# state=absent and for an update touching one unrelated field.
_CREATE_REQUIRED = ('gitUrl', 'productionEnvironment')

# Create-only fields with no readable counterpart anywhere on Project, so
# convergence can never be proven. Always an error against an existing
# project, never a silent no-op.
_UNREADABLE_CREATE_ONLY = ('addOrgOwner',)

# Read selection. The 33 plain scalar leaves plus three bounded hops.
#
# privateKey is absent deliberately: re-fetching SSH key material every
# run merely to diff it is an unjustified secret-handling cost, and Lagoon
# generates a key pair server-side when none is supplied, so diffing it
# would mostly detect server-generated churn rather than caller intent.
_READ_SELECTION = [
    'id', 'name', 'gitUrl', 'subfolder', 'routerPattern',
    'openshiftProjectPattern', 'kubernetesNamespacePattern',
    'activeSystemsDeploy', 'activeSystemsPromote', 'activeSystemsRemove',
    'activeSystemsTask', 'activeSystemsMisc', 'branches', 'pullrequests',
    'productionEnvironment', 'productionRoutes', 'productionAlias',
    'standbyProductionEnvironment', 'standbyRoutes', 'standbyAlias',
    'availability', 'autoIdle', 'storageCalc',
    'developmentEnvironmentsLimit', 'problemsUi', 'factsUi',
    'productionBuildPriority', 'developmentBuildPriority',
    'deploymentsDisabled', 'organization', 'buildImage',
    'sharedBaasBucket', 'restrictions',
    {'openshift': ['id']},
    {'kubernetes': ['id']},
    {'autogeneratedRouteConfig': [
        'enabled', 'allowPullRequests', 'prefixes',
        'disableRequestVerification',
        {'pathRoutes': ['fromService', 'toService', 'path']},
    ]},
]

# Flattening of the read's bounded hops back into the flat wire-field
# namespace the input types use, since e.g. AddProjectInput.openshift is
# an Int while Project.openshift is an Openshift object.
#
# Declarative rather than a sequence of hop-specific statements: the same
# shape has to be derivable from allowlist data for every other resource,
# not just the three hops project happens to have.
#
# Each entry maps a read hop's field name to (scalar_leaf_map,
# list_leaf_map):
#   scalar_leaf_map -- {leaf name on the hop: flat wire field name}
#   list_leaf_map   -- {leaf name on the hop: (flat wire field name,
#                       {inner leaf: dict key})}
_HOP_FLATTENING = {
    'openshift': ({'id': 'openshift'}, {}),
    'kubernetes': ({'id': 'kubernetes'}, {}),
    'autogeneratedRouteConfig': (
        {
            'enabled': 'autogeneratedRoutes',
            'allowPullRequests': 'autogeneratedRoutesPullrequests',
            'prefixes': 'autogeneratedRoutePrefixes',
            'disableRequestVerification': 'disableRequestVerification',
        },
        {
            'pathRoutes': ('autogeneratedPathRoutes', {
                'fromService': 'from_service',
                'toService': 'to_service',
                'path': 'path',
            }),
        },
    ),
}

# Operation names, not documents. Deliberately not named *_QUERY or
# *_MUTATION: the flat-query sweep collects any module-level string
# constant whose name matches that pattern and checks it as a GraphQL
# document, which a bare operation name is not.
_READ_OPERATION = 'projectByName'
_READ_ARG = 'name'
_CREATE_OPERATION = 'addProject'
_UPDATE_OPERATION = 'updateProject'
_DELETE_OPERATION = 'deleteProject'


_AVAILABILITY_CHOICES = ['STANDARD', 'HIGH', 'POLYSITE']

_RESTRICTION_CHOICES = [
    'NO_PROJECT_VARIABLES', 'NO_ENVIRONMENT_VARIABLES', 'NO_TASKS',
    'NO_DEPLOYMENTS', 'NO_WEBHOOK_DEPLOYMENTS',
]


def argument_spec():
    """The flat argspec for the AddProjectInput/UpdateProjectPatchInput
    union.

    Public so a test can assert every wire field in :data:`_FIELDS` has a
    matching option: ``resource.py`` reads each field from the param named
    ``camel_to_snake(field)``, so an option spelled differently here is
    accepted from the user and then silently dropped before it reaches the
    diff. ``id`` is the one exception: it is in :data:`_FIELDS` and
    :data:`_DIFF_IGNORE` (the update key, read from current state) but
    deliberately has no option here, since a caller can never legitimately
    supply it.

    Only ``name`` is ``required``: it is the resource's own read and
    delete key, needed for every state. The create mutation's other
    NonNull fields are enforced by :func:`_check_create_required` on the
    create path alone -- see :data:`_CREATE_REQUIRED`.
    """
    return dict(
        state=dict(type='str', default='present',
                   choices=['present', 'absent']),
        name=dict(type='str', required=True),
        git_url=dict(type='str'),
        subfolder=dict(type='str'),
        router_pattern=dict(type='str'),
        openshift=dict(type='int'),
        openshift_project_pattern=dict(type='str'),
        kubernetes=dict(type='int'),
        kubernetes_namespace_pattern=dict(type='str'),
        active_systems_deploy=dict(type='str'),
        active_systems_promote=dict(type='str'),
        active_systems_remove=dict(type='str'),
        active_systems_task=dict(type='str'),
        active_systems_misc=dict(type='str'),
        branches=dict(type='str'),
        pullrequests=dict(type='str'),
        production_environment=dict(type='str'),
        production_routes=dict(type='str'),
        production_alias=dict(type='str'),
        standby_production_environment=dict(type='str'),
        standby_routes=dict(type='str'),
        standby_alias=dict(type='str'),
        availability=dict(type='str', choices=_AVAILABILITY_CHOICES),
        auto_idle=dict(type='int'),
        storage_calc=dict(type='int'),
        development_environments_limit=dict(type='int'),
        private_key=dict(type='str', no_log=True),
        problems_ui=dict(type='int'),
        facts_ui=dict(type='int'),
        production_build_priority=dict(type='int'),
        development_build_priority=dict(type='int'),
        deployments_disabled=dict(type='int'),
        organization=dict(type='int'),
        add_org_owner=dict(type='bool'),
        build_image=dict(type='str'),
        shared_baas_bucket=dict(type='bool'),
        autogenerated_routes=dict(type='bool'),
        autogenerated_routes_pullrequests=dict(type='bool'),
        autogenerated_route_prefixes=dict(type='list', elements='str'),
        autogenerated_path_routes=dict(
            type='list', elements='dict',
            options=dict(
                from_service=dict(type='str'),
                to_service=dict(type='str'),
                path=dict(type='str'),
            )),
        disable_request_verification=dict(type='bool'),
        restrictions=dict(type='list', elements='str',
                          choices=_RESTRICTION_CHOICES),
    )


def _option_name(wire_field):
    """The argspec option name a wire field maps to, for error messages
    that name the option the user actually wrote.

    Shares ``resource.py``'s transform rather than re-deriving it: that
    function is also what decides which param a wire field reads from, so
    a second implementation here could name an option that does not exist.
    """
    return camel_to_snake(wire_field)


def _flatten_hops(record):
    """Rewrite the bounded hops in a read result into the flat wire-field
    namespace the input types use, per :data:`_HOP_FLATTENING`.

    A hop that came back null contributes nothing rather than a null for
    each of its flattened fields: absent and explicitly-null are the same
    thing to the diff, and inventing keys here would make an unset deploy
    target look like a change on every run.
    """
    flattened = {
        field: value for field, value in record.items()
        if field not in _HOP_FLATTENING
    }

    for hop, (scalar_leaves, list_leaves) in _HOP_FLATTENING.items():
        hop_value = record.get(hop)
        if not isinstance(hop_value, dict):
            continue

        for leaf, wire_field in scalar_leaves.items():
            if leaf in hop_value:
                flattened[wire_field] = hop_value[leaf]

        for leaf, (wire_field, key_map) in list_leaves.items():
            rows = hop_value.get(leaf)
            if rows is None:
                continue
            flattened[wire_field] = [
                {
                    key: row.get(inner_leaf)
                    for inner_leaf, key in key_map.items()
                }
                for row in rows
            ]

    return flattened


def _read(client, name):
    """Fetch current state, or ``None`` when the project does not exist."""
    document = LagoonClient.build_query(
        _READ_OPERATION, fields=_READ_SELECTION,
        args={_READ_ARG: 'String!'})
    data = client.execute(document, variables={_READ_ARG: name})

    record = data.get(_READ_OPERATION)
    if record is None:
        return None
    return _flatten_hops(record)


def _check_create_required(desired):
    """Raise if a field AddProjectInput declares NonNull is missing.

    A create-time check rather than argspec ``required``: the same argspec
    also serves update and delete, where requiring these would be wrong.
    """
    missing = [
        _option_name(field) for field in _CREATE_REQUIRED
        if desired.get(field) is None
    ]
    if missing:
        raise errors.LagoonConfigError(
            "creating a project requires %s" % ', '.join(sorted(missing)))


def _check_create_only(current, desired):
    """Raise if a create-only field is supplied against an existing
    project and cannot be shown to already match.

    Three cases, keyed only on whether the field is readable:

      - readable and equal to current state -> no-op, so a create
        playbook re-run stays idempotent;
      - readable and different -> error naming both values, since no
        mutation converges it without collateral damage;
      - unreadable -> error unconditionally, because there is no state
        against which convergence could be proven.
    """
    for field in _CREATE_ONLY:
        if field not in desired:
            continue

        if field in _UNREADABLE_CREATE_ONLY:
            raise errors.LagoonConfigError(
                "%s can only be set when creating a project, and has no "
                "readable state to compare against on an existing one -- "
                "remove it from this task" % _option_name(field))

        requested = desired[field]
        existing = current.get(field)
        if existing == requested:
            continue

        message = (
            "%s can only be set when creating a project (current: %r, "
            "requested: %r)" % (_option_name(field), existing, requested))
        if field == 'organization':
            message += (
                " -- move a project between organizations with "
                "removeProjectFromOrganization or "
                "bulkImportProjectsAndGroupsToOrganization")
        raise errors.LagoonConfigError(message)


def _create(client, desired):
    _check_create_required(desired)
    payload = {
        field: value for field, value in desired.items()
        if field not in _UPDATE_ONLY
    }
    document = LagoonClient.build_query(
        _CREATE_OPERATION, fields=['id'],
        args={'input': 'AddProjectInput!'},
        operation_type='mutation')
    client.execute(document, variables={'input': payload})


def _update(client, current, desired, changed_fields):
    _check_create_only(current, desired)
    patch = {
        field: value for field, value in desired.items()
        if field in changed_fields and field not in _CREATE_ONLY
    }
    # Never read, so never in changed_fields -- send it whenever supplied
    # and let the server decide whether it is a change.
    if desired.get('privateKey') is not None:
        patch['privateKey'] = desired['privateKey']
    if not patch:
        return
    document = LagoonClient.build_query(
        _UPDATE_OPERATION, fields=['id'],
        args={'input': 'UpdateProjectInput!'},
        operation_type='mutation')
    client.execute(document, variables={
        'input': {'id': current['id'], 'patch': patch}})


def _delete(client, current):
    document = LagoonClient.build_query(
        _DELETE_OPERATION, fields=[],
        args={'input': 'DeleteProjectInput!'},
        operation_type='mutation')
    client.execute(
        document, variables={'input': {'project': current['name']}})


def run_module(module):
    """Execute the read/diff/mutate flow and return LagoonResourceModule's
    result dict.

    Takes an already-constructed ``AnsibleModule`` (or any object exposing
    the same ``.params`` mapping and ``.check_mode``) so this can be
    exercised directly in unit tests with no action shim involved,
    proving the module is fully functional when handed an explicit
    ``lagoon_api_token``.
    """
    client = LagoonClient(
        endpoint=module.params['lagoon_api_endpoint'],
        token=module.params['lagoon_api_token'],
        module=module,
        validate_certs=module.params['validate_certs'],
    )
    name = module.params['name']

    resource = LagoonResourceModule(
        fields=_FIELDS,
        diff_ignore=_DIFF_IGNORE,
        no_log_fields=_NO_LOG_FIELDS,
        read=lambda client: _read(client, name),
        create=_create,
        update=_update,
        delete=_delete,
    )
    return resource.run(module, client)


def main():
    module = AnsibleModule(
        argument_spec=auth.auth_argument_spec(argument_spec()),
        supports_check_mode=True,
    )

    try:
        result = run_module(module)
    except errors.LagoonError as e:
        module.fail_json(msg=str(e))
        return

    module.exit_json(
        changed=result['changed'],
        diff=result['diff'],
        project=result['resource'],
    )


if __name__ == '__main__':
    main()
