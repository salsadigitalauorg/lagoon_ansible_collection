import unittest

from .....plugins.module_utils.fields import (
    PROJECT_FIELDS,
    PROJECT_FIELDS_NO_METADATA,
    PROJECT_LIST_FIELDS,
    merge_fields,
    render_fields,
    resolve_fields,
)


class RenderFieldsTester(unittest.TestCase):
    def test_flat_spec(self):
        assert render_fields(["id", "name"]) == "id name"

    def test_nested_spec(self):
        assert (
            render_fields(["id", "name", {"kubernetes": ["id", "name"]}])
            == "id name kubernetes { id name }"
        )

    def test_deeply_nested_spec(self):
        spec = [
            "id",
            {"environments": ["name", {"kubernetes": ["id", {"group": ["name"]}]}]},
        ]
        assert (
            render_fields(spec)
            == "id environments { name kubernetes { id group { name } } }"
        )

    def test_multiple_keys_in_one_dict(self):
        spec = [{"groups": ["id"], "envVariables": ["name"]}]
        assert render_fields(spec) == "groups { id } envVariables { name }"

    def test_empty_spec_raises(self):
        for spec in ([], None, ()):
            with self.assertRaises(ValueError):
                render_fields(spec)

    def test_empty_nested_spec_raises(self):
        with self.assertRaises(ValueError):
            render_fields(["id", {"kubernetes": []}])

    def test_rejects_a_non_name_field(self):
        """Field names are interpolated into the document, so they are checked.

        Nothing that could terminate a selection set or introduce an argument
        may pass through.
        """

        for bad in [
            'id } mutation { deleteProject(input: {project: "x"})',
            "id name",
            "kubernetes { id }",
            "1nvalid",
            "has-a-hyphen",
            'name: "x"',
            "",
        ]:
            with self.assertRaises(ValueError, msg=f"accepted {bad!r}"):
                render_fields([bad])

    def test_rejects_a_non_name_nested_key(self):
        with self.assertRaises(ValueError):
            render_fields([{'kubernetes(x: "y")': ["id"]}])

    def test_rejects_a_non_spec_entry(self):
        with self.assertRaises(TypeError):
            render_fields([1])


class MergeFieldsTester(unittest.TestCase):
    def test_extra_scalars_are_added(self):
        assert merge_fields(["id", "name"], ["gitUrl"]) == ["id", "name", "gitUrl"]

    def test_scalars_are_de_duplicated(self):
        assert merge_fields(["id", "name"], ["name", "gitUrl"]) == [
            "id",
            "name",
            "gitUrl",
        ]

    def test_nested_keys_merge_rather_than_replace(self):
        """The defaults for a subtree survive adding one field to it.

        Replacing instead would silently drop them, which surfaces as a
        KeyError several layers from the call site.
        """

        merged = merge_fields(
            ["id", {"kubernetes": ["id", "name"]}],
            [{"kubernetes": ["consoleUrl"]}],
        )
        assert merged == ["id", {"kubernetes": ["id", "name", "consoleUrl"]}]
        assert render_fields(merged) == "id kubernetes { id name consoleUrl }"

    def test_nested_merge_recurses(self):
        merged = merge_fields(
            [{"environments": ["id", {"kubernetes": ["id"]}]}],
            [{"environments": ["name", {"kubernetes": ["name"]}]}],
        )
        assert merged == [
            {"environments": ["id", {"kubernetes": ["id", "name"]}, "name"]}
        ]

    def test_a_nested_selection_supersedes_the_scalar_form(self):
        assert merge_fields(["kubernetes"], [{"kubernetes": ["id"]}]) == [
            {"kubernetes": ["id"]}
        ]
        assert merge_fields([{"kubernetes": ["id"]}], ["kubernetes"]) == [
            {"kubernetes": ["id"]}
        ]

    def test_merge_does_not_mutate_its_arguments(self):
        base = ["id", {"kubernetes": ["id"]}]
        extra = [{"kubernetes": ["name"]}]
        merge_fields(base, extra)
        assert base == ["id", {"kubernetes": ["id"]}]
        assert extra == [{"kubernetes": ["name"]}]


class ResolveFieldsTester(unittest.TestCase):
    def test_default_when_neither_given(self):
        assert resolve_fields(["id", "name"]) == ["id", "name"]

    def test_fields_replaces_the_default(self):
        assert resolve_fields(["id", "name"], fields=["gitUrl"]) == ["gitUrl"]

    def test_extra_fields_adds_to_the_default(self):
        assert resolve_fields(["id"], extra_fields=["gitUrl"]) == ["id", "gitUrl"]

    def test_both_raises(self):
        with self.assertRaises(ValueError):
            resolve_fields(["id"], fields=["a"], extra_fields=["b"])

    def test_returns_a_copy_of_the_default(self):
        default = ["id", "name"]
        resolved = resolve_fields(default)
        resolved.append("gitUrl")
        assert default == ["id", "name"]


class DefaultFieldListsTester(unittest.TestCase):
    def test_project_list_fields_is_name_only(self):
        """The list query's only job is to enumerate names.

        A wide selection across every project on the estate is the shape that
        degrades and then fails on a large Lagoon.
        """
        assert PROJECT_LIST_FIELDS == ["name"]

    def test_project_default_is_project_fields_less_metadata(self):
        assert "metadata" in PROJECT_FIELDS
        assert "metadata" not in PROJECT_FIELDS_NO_METADATA
        assert set(PROJECT_FIELDS_NO_METADATA) == set(PROJECT_FIELDS) - {"metadata"}
        assert len(PROJECT_FIELDS_NO_METADATA) == 21
