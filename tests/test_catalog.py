import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gallery_build.builder import build, canonical, import_manifest, load_project
from gallery_build.catalog import catalog_from_items, catalog_ids
from gallery_build.publication import (
    create_pr,
    make_payload,
    merge_catalog,
    prepare_changes,
)
from test_builder import example
from test_publication import BASE, FakeGitHub


class CatalogTests(unittest.TestCase):
    def test_independent_order_legacy_migration_and_kind_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            author, collective = example("author-old"), example("collective-old")
            collective["kind"] = "collective"
            import_manifest(root, author)
            import_manifest(root, collective)
            path = root / "content/catalog.json"
            # Reading a previous archive keeps working; the next import migrates it.
            path.write_text(
                canonical([collective["id"], author["id"]]), encoding="utf-8"
            )
            self.assertEqual(len(load_project(root)[0]), 2)
            newest = example("author-new")
            import_manifest(root, newest)
            import_manifest(root, collective)
            catalog = json.loads(path.read_text())
            self.assertEqual(
                catalog,
                {
                    "schema_version": 1,
                    "author": ["author-new", "author-old"],
                    "collective": ["collective-old"],
                },
            )
            items, _ = load_project(root)
            html = build(items)["index.html"].decode()
            self.assertIn('data-kind="collective"', html)
            self.assertIn('data-kind="author"', html)
            catalog["author"].append(catalog["collective"].pop())
            path.write_text(canonical(catalog), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "kind"):
                load_project(root)

    def test_collective_pr_preserves_authors_and_matches_approved_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            author, old, new = example("author"), example("older"), example("newest")
            old["kind"] = new["kind"] = "collective"
            for item in (author, old):
                import_manifest(root, item)
            github = FakeGitHub()
            github.catalog = catalog_from_items([author, old])
            payload = make_payload(BASE, new, build(merge_catalog([author, old], new)))
            changes, _ = prepare_changes(root, payload)
            self.assertEqual(
                json.loads(changes["content/catalog.json"]),
                {
                    "schema_version": 1,
                    "author": ["author"],
                    "collective": ["newest", "older"],
                },
            )
            create_pr(github, payload, changes)
            # Changing kind moves only the selected entry, to the front of its new section.
            new = {**old, "kind": "author"}
            github.ref = None
            payload = make_payload(BASE, new, build(merge_catalog([author, old], new)))
            changes, _ = prepare_changes(root, payload)
            self.assertEqual(
                json.loads(changes["content/catalog.json"]),
                {"schema_version": 1, "author": ["older", "author"], "collective": []},
            )
            create_pr(github, payload, changes)

    def test_reject_ambiguous_or_unsafe_catalogs(self):
        for value in (
            {"schema_version": 1, "author": ["same"], "collective": ["same"]},
            {"schema_version": 1, "author": []},
            {"schema_version": 2, "author": [], "collective": []},
            {"schema_version": 1, "author": ["../secret"], "collective": []},
            {"schema_version": 1, "author": [], "collective": {}},
            [None],
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                catalog_ids(value)
