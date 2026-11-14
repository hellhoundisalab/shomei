import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gallery_build.builder import build, canonical, digest, import_manifest
from gallery_build.catalog import catalog_from_items
from gallery_build.publication import (
    PublicationError,
    branch_name,
    create_pr,
    make_payload,
    merge_catalog,
    prepare_changes,
    public_manifest,
    renderer_tree,
    receipt,
    receipt_path,
    repository_snapshot,
    validate_payload,
)
from test_builder import example

BASE = "a" * 40


class FakeGitHub:
    repository = "owner/gallery"

    def __init__(self):
        self.base = BASE
        self.prs = []
        self.ref = None
        self.calls = []
        self.commits = {BASE: {"tree": {"sha": "old-tree"}}}
        self.catalog = []
        self.manifests = {}

    def main(self):
        return self.base

    def file(self, path, ref):
        return canonical(self.manifests.get(path, self.catalog))

    def pulls(self, branch=None, state="all"):
        return [
            p
            for p in self.prs
            if (not branch or p["head"]["ref"] == branch)
            and (state == "all" or p["state"] == state)
        ]

    def api(self, method, path, data=None, missing=False):
        self.calls.append((method, path, data))
        if path.startswith("/git/trees/"):
            return {"tree": []}
        if path.startswith("/git/commits/"):
            return self.commits[path.split("/")[-1]]
        if path == "/git/trees":
            return {"sha": digest(data)}
        if path == "/git/commits":
            sha = digest(data)[:40]
            self.commits[sha] = {
                "sha": sha,
                "tree": {"sha": data["tree"]},
                "parents": [{"sha": x} for x in data["parents"]],
            }
            return self.commits[sha]
        if path.startswith("/git/ref/heads/"):
            return self.ref
        if path == "/git/refs":
            self.ref = {"object": {"sha": data["sha"]}}
            return self.ref
        if path == "/pulls":
            pr = {
                "number": 1,
                "state": "open",
                "head": {"ref": data["head"], "sha": self.ref["object"]["sha"]},
            }
            self.prs.append(pr)
            return pr
        raise AssertionError((method, path))


class PublicationTests(unittest.TestCase):
    def test_compare_endpoint_allowed_but_traversal_rejected(self):
        from gallery_build.publication import GitHub

        github = GitHub("owner/gallery", transport=lambda *args: {"behind_by": 0})
        self.assertEqual(
            github.api("GET", "/compare/" + "a" * 40 + "..." + "b" * 40),
            {"behind_by": 0},
        )
        with self.assertRaises(PublicationError):
            github.api("GET", "/contents/../secret")

    def fixture(self):
        item = example()
        payload = make_payload(BASE, item, build([item]))
        changes = {
            "content/catalog.json": canonical(catalog_from_items([item])) + "\n",
            receipt_path(item["id"]): canonical(receipt(payload)) + "\n",
            "content/exhibitions/example/manifest.json": canonical(item) + "\n",
        }
        return payload, changes

    def test_only_data_paths_and_no_main_update(self):
        github = FakeGitHub()
        payload, changes = self.fixture()
        pr = create_pr(github, payload, changes)
        self.assertEqual(pr["head"]["ref"], branch_name(payload))
        writes = [
            (path, data) for method, path, data in github.calls if method != "GET"
        ]
        self.assertEqual(
            [x[0] for x in writes],
            ["/git/trees", "/git/commits", "/git/refs", "/pulls"],
        )
        self.assertEqual({x["path"] for x in writes[0][1]["tree"]}, set(changes))
        self.assertTrue(writes[2][1]["ref"].startswith("refs/heads/publish/"))
        self.assertEqual(writes[3][1]["base"], "main")
        self.assertEqual(create_pr(github, payload, changes), pr)
        pr["state"] = "closed"
        self.assertEqual(create_pr(github, payload, changes), pr)
        self.assertEqual(len([x for x in github.calls if x[0] != "GET"]), 4)

    def test_recovery_after_branch_creation_and_manual_edits_are_preserved(self):
        github = FakeGitHub()
        payload, changes = self.fixture()
        create_pr(github, payload, changes)
        github.prs = []  # Simulate a failed PR API call after successful branch creation.
        create_pr(github, payload, changes)
        self.assertEqual(len([x for x in github.calls if x[1] == "/git/refs"]), 1)
        github.prs = []
        github.commits[github.ref["object"]["sha"]]["tree"]["sha"] = "manual-edit"
        with self.assertRaisesRegex(PublicationError, "вручную"):
            create_pr(github, payload, changes)

    def test_reject_changed_main_wrong_catalog_and_workflow_injection(self):
        payload, changes = self.fixture()
        github = FakeGitHub()
        github.base = "b" * 40
        with self.assertRaisesRegex(PublicationError, "main changed"):
            create_pr(github, payload, changes)
        self.assertFalse(any(method != "GET" for method, _, _ in github.calls))
        github.base = BASE
        for edit in (
            {**changes, ".github/workflows/evil.yml": "evil"},
            {**changes, "content/catalog.json": "[]\n"},
        ):
            with self.assertRaises(PublicationError):
                create_pr(github, payload, edit)

    def test_public_https_only_and_private_fields_rejected(self):
        for url in (
            "media/example/photo.jpg",
            "http://s3.localhost:19000/p.jpg",
            "https://127.0.0.1/p.jpg",
            "https://192.168.1.5/p.jpg",
            "https://nas.local/p.jpg",
            "https://media.example/p.jpg?X-Amz-Signature=secret",
        ):
            item = example()
            item["photos"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_manifest(item)
        item = example()
        item["telegram_id"] = 123
        with self.assertRaises(ValueError):
            public_manifest(item)

    def test_preview_is_exact_and_custom_css_and_catalog_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = example("older")
            import_manifest(root, old)
            custom = root / "content/exhibitions/older/custom.css"
            custom.write_text("h1 {opacity:.9}", encoding="utf-8")
            item = example()
            payload = make_payload(
                BASE, item, build([item, old], {"older": custom.read_text()})
            )
            changes, _ = prepare_changes(root, payload)
            self.assertEqual(
                json.loads(changes["content/catalog.json"]),
                catalog_from_items([item, old]),
            )
            self.assertEqual(custom.read_text(), "h1 {opacity:.9}")
            # Changed CSS, base content or renderer cannot silently differ from approval.
            custom.write_text("h1 {opacity:.8}", encoding="utf-8")
            with self.assertRaisesRegex(PublicationError, "differs"):
                prepare_changes(root, payload)
            self.assertEqual(
                [x["id"] for x in merge_catalog([old, item], item)],
                ["older", "example"],
            )

    def test_payload_tampering_and_size_limits(self):
        payload, _ = self.fixture()
        changed = copy.deepcopy(payload)
        changed["manifest"]["title"] = "changed"
        with self.assertRaises(PublicationError):
            validate_payload(changed)
        changed["extra"] = "secret"
        with self.assertRaises(PublicationError):
            validate_payload(changed)

    def test_remote_renderer_must_match_and_no_other_submissions_imported(self):
        class SnapshotGitHub:
            def main(self):
                return BASE

            def file(self, path, ref):
                return "[]"

            def api(self, method, path):
                if path == "/":
                    return {"private": False, "default_branch": "main"}
                tree = [
                    {"path": p, "sha": sha, "type": "blob", "mode": "100644"}
                    for p, sha in renderer_tree().items()
                ]
                tree.append(
                    {
                        "path": ".github/workflows/prepare-exhibition.yml",
                        "sha": "test",
                        "type": "blob",
                        "mode": "100644",
                    }
                )
                if self.broken:
                    tree[0]["sha"] = "bad"
                return {"tree": tree}

        github = SnapshotGitHub()
        github.broken = False
        self.assertEqual(repository_snapshot(github), (BASE, [], {}))
        github.broken = True
        with self.assertRaisesRegex(PublicationError, "Сборщик"):
            repository_snapshot(github)


if __name__ == "__main__":
    unittest.main()
