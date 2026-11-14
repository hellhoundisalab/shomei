import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1] / "src"),
    str(Path(__file__).resolve().parents[1] / "scripts"),
]
from gallery_build.builder import build, canonical, import_manifest, load_project
from gallery_build.lifecycle import (
    check_withdrawals,
    local_markers,
    marker,
    marker_path,
)
from gallery_build.publication import create_pr, make_payload, prepare_changes
from publication_guard import check
from test_builder import example
from test_publication import BASE, FakeGitHub


class LifecycleTests(unittest.TestCase):
    def test_withdrawal_preview_pr_and_permanent_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            item = example()
            other = example("other")
            import_manifest(root, item)
            import_manifest(root, other)
            payload = make_payload(
                BASE, {"id": "example"}, build([other]), "withdraw", previous=item
            )
            changes, files = prepare_changes(root, payload)
            self.assertNotIn("exhibitions/example/index.html", files)
            self.assertIn("exhibitions/other/index.html", files)
            github = FakeGitHub()
            github.manifests["content/exhibitions/example/manifest.json"] = item
            github.catalog = {
                "schema_version": 1,
                "author": ["other", "example"],
                "collective": [],
            }
            # Withdrawal may supersede an already open publication PR.
            github.prs = [{"head": {"ref": "publish/example/old"}, "state": "open"}]
            create_pr(github, payload, changes)
            for name, text in changes.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            self.assertEqual([x["id"] for x in load_project(root)[0]], ["other"])
            self.assertIn("example", local_markers(root))
            old_pr = make_payload(BASE, item, build([item, other]))
            with self.assertRaisesRegex(ValueError, "Withdrawn"):
                prepare_changes(root, old_pr)
            # Even a manually edited catalog cannot silently restore the page.
            (root / "content/catalog.json").write_text(canonical(github.catalog))
            with self.assertRaisesRegex(ValueError, "Withdrawn"):
                load_project(root)

    def test_current_main_markers_cannot_be_erased_by_old_pr(self):
        old = {"example": marker("example")}
        with self.assertRaisesRegex(ValueError, "removed"):
            check_withdrawals([], {}, old)
        with self.assertRaisesRegex(ValueError, "return"):
            check_withdrawals(["example"], old, old)
        check_withdrawals([], old, old)
        changed = copy.deepcopy(old)
        changed["example"]["schema_version"] = 2
        with self.assertRaises(ValueError):
            check_withdrawals([], changed, old)

    def test_trusted_guard_rejects_old_head_and_marker_removal(self):
        github = FakeGitHub()
        original = github.api
        github.api = lambda method, path, *args: (
            {"behind_by": 1}
            if path.startswith("/compare/")
            else original(method, path, *args)
        )
        with self.assertRaisesRegex(ValueError, "behind"):
            check(github, "b" * 40)
        github.api = lambda *args: {"behind_by": 0}
        with (
            patch(
                "publication_guard.remote_markers",
                side_effect=[{"example": marker("example")}, {}],
            ),
            self.assertRaisesRegex(ValueError, "removed"),
        ):
            check(github, "b" * 40)

    def test_new_update_keeps_other_exhibitions_and_matches_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a, b = example(), example("other")
            import_manifest(root, a)
            import_manifest(root, b)
            revised = copy.deepcopy(a)
            revised["title"] = "Updated"
            payload = make_payload(BASE, revised, build([b, revised]), previous=a)
            changes, _ = prepare_changes(root, payload)
            self.assertEqual(
                json.loads(changes["content/catalog.json"])["author"],
                ["other", "example"],
            )
            self.assertEqual(
                json.loads(changes["content/exhibitions/example/manifest.json"])[
                    "title"
                ],
                "Updated",
            )
            self.assertNotIn(marker_path("example"), changes)

    def test_rebased_old_update_cannot_restore_removed_photo(self):
        from gallery_build.builder import digest
        from gallery_build.publication import receipt_path

        before = example()
        before["title"] = "Current selection"
        stale = example()
        old_receipt = {
            "schema_version": 1,
            "operation": "upsert",
            "previous": "0" * 64,
            "current": digest(stale),
        }
        github = FakeGitHub()
        github.api = lambda *args: {"behind_by": 0}

        def file(path, ref):
            if path == "content/catalog.json":
                return '["example"]'
            if path == receipt_path("example"):
                return canonical(old_receipt)
            return canonical(before if ref == BASE else stale)

        github.file = file
        with patch("publication_guard.remote_markers", return_value={}):
            with self.assertRaisesRegex(ValueError, "another revision"):
                check(github, "b" * 40)
            old_receipt["previous"] = digest(before)
            check(github, "b" * 40)
