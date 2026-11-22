"""Checks that each ported module's ARGUMENT_SPEC and DOCUMENTATION.options
stay in step.

AnsibleModule would normally enforce this by being the only consumer of
either; these modules have no main(), so nothing else catches a drift.
"""

import unittest

import yaml

from .....plugins.modules import last_deploy, project_notification, project_update

MODULES = [last_deploy, project_notification, project_update]


class ArgumentSpecTester(unittest.TestCase):
    def test_every_key_is_documented_and_vice_versa(self):
        for mod in MODULES:
            doc = yaml.safe_load(mod.DOCUMENTATION)
            doc_keys = set(doc.get("options", {}).keys())
            spec_keys = set(mod.ARGUMENT_SPEC.keys())

            assert doc_keys == spec_keys, (
                f"{mod.__name__}: documented {doc_keys} vs argspec {spec_keys}"
            )

    def test_defaults_agree(self):
        for mod in MODULES:
            doc = yaml.safe_load(mod.DOCUMENTATION)
            options = doc.get("options", {})

            for name, spec in mod.ARGUMENT_SPEC.items():
                if "default" not in spec:
                    continue
                assert options[name].get("default") == spec["default"], (
                    f"{mod.__name__}.{name}: doc default "
                    f"{options[name].get('default')!r} vs argspec "
                    f"{spec['default']!r}"
                )

    def test_required_agrees(self):
        for mod in MODULES:
            doc = yaml.safe_load(mod.DOCUMENTATION)
            options = doc.get("options", {})

            for name, spec in mod.ARGUMENT_SPEC.items():
                if not spec.get("required"):
                    continue
                assert options[name].get("required") is True, (
                    f"{mod.__name__}.{name} is required in ARGUMENT_SPEC but "
                    "not documented as such"
                )


if __name__ == "__main__":
    unittest.main()
