import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gallery_build import build, import_manifest, load_project, validate_manifest


def example(key="example"):
    return {
        "schema_version": 1,
        "id": key,
        "kind": "author",
        "title": "Между делом",
        "author": "Автор",
        "description": "Описание",
        "date": "2026-11-14",
        "theme": {"background": "#d6f0e8", "accent": "#15425d"},
        "photos": [
            {
                "id": "photo-1",
                "url": "https://media.example/photo.jpg",
                "preview": "https://media.example/preview.jpg",
                "width": 1200,
                "height": 800,
                "caption": "Подпись",
                "alt": "Описание фото",
                "exif": {"iso": "400"},
            }
        ],
    }


class BuilderTests(unittest.TestCase):
    def test_collective_photo_authors_are_optional_public_and_escaped(self):
        item = example()
        item["kind"] = "collective"
        item["author"] = ""
        item["photos"][0]["author"] = "<b>Автор фото</b>"
        page = build([item])["exhibitions/example/index.html"].decode()
        self.assertIn("&lt;b&gt;Автор фото&lt;/b&gt;", page)
        self.assertNotIn('<span aria-hidden="true">·</span>', page)
        item["photos"][0].pop("author")
        build([item])
        item["photos"][0]["telegram_id"] = 123
        with self.assertRaises(ValueError):
            validate_manifest(item)

    def test_selected_font_and_stable_card_scatter(self):
        from gallery_build.builder import scatter

        item = example()
        item["theme"]["font"] = "roboto_mono"
        files = build([item])
        self.assertIn(b"Roboto Mono", files["exhibitions/example/index.html"])
        self.assertIn(b"font-family:'Roboto Mono'", files["assets/gallery.css"])
        self.assertNotIn(b"font-family:'Merriweather'", files["assets/gallery.css"])
        self.assertEqual(scatter("example", 0), scatter("example", 0))
        self.assertNotEqual(scatter("example", 0), scatter("another", 0))
        item["theme"]["font"] = "url(evil)"
        with self.assertRaises(ValueError):
            build([item])

    def test_bundled_media_requires_safe_existing_paths(self):
        item = example()
        item["photos"][0]["url"] = "media/example/photo-1.jpg"
        item["photos"][0]["preview"] = item["photos"][0]["url"]
        with self.assertRaises(ValueError):
            build([item])
        files = build([item], media={"media/example/photo-1.jpg": b"jpeg fixture"})
        self.assertEqual(files["media/example/photo-1.jpg"], b"jpeg fixture")
        self.assertIn(
            b"../../media/example/photo-1.jpg", files["exhibitions/example/index.html"]
        )
        item["photos"][0]["url"] = "media/example/../../secret.jpg"
        with self.assertRaises(ValueError):
            validate_manifest(item)

    def test_import_preserves_manual_files_and_catalog_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import_manifest(root, example("first"))
            custom = root / "content/exhibitions/first/custom.css"
            custom.write_text("h1 { letter-spacing: .1em; }", encoding="utf-8")
            import_manifest(root, example("second"))
            changed = example("first")
            changed["title"] = "Правка"
            import_manifest(root, changed)
            items, css = load_project(root)
            self.assertEqual([x["id"] for x in items], ["second", "first"])
            self.assertEqual(css["first"], custom.read_text())
            self.assertEqual(items[1]["title"], "Правка")

    def test_render_is_deterministic_escaped_and_theme_is_shared(self):
        item = example()
        item["title"] = '<script>alert("x")</script>'
        item["photos"][0]["caption"] = "<img src=x onerror=alert(1)>"
        files = build([item])
        self.assertEqual(files, build([item]))
        for key in ["index.html", "exhibitions/example/index.html"]:
            html = files[key].decode()
            self.assertNotIn("<script>alert", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("#d6f0e8", html)
        self.assertIn(b"data-view-link", files["index.html"])
        self.assertNotIn(b"onerror=alert(1)>", files["exhibitions/example/index.html"])

    def test_reject_private_fields_signed_urls_and_traversal(self):
        cases = []
        item = example()
        item["telegram_id"] = 123
        cases.append(item)
        item = example()
        item["id"] = "../escape"
        cases.append(item)
        item = example()
        item["photos"][0]["url"] = "javascript:alert(1)"
        cases.append(item)
        item = example()
        item["photos"][0]["url"] += "?X-Amz-Signature=secret"
        cases.append(item)
        item = example()
        item["theme"]["background"] = "red; background:url(https://evil)"
        cases.append(item)
        item = example()
        item["photos"][0]["exif"]["gps"] = "private"
        cases.append(item)
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_manifest(item)

    def test_no_photos_duplicates_and_invalid_dates(self):
        item = example()
        item["photos"] = []
        with self.assertRaises(ValueError):
            build([item])
        with self.assertRaises(ValueError):
            build([example(), example()])
        item = example()
        item["date"] = "2026-99-99"
        with self.assertRaises(ValueError):
            build([item])

    def test_relative_asset_paths_work_under_pages_subpaths(self):
        files = build([example()])
        page = files["exhibitions/example/index.html"].decode()
        self.assertIn('href="../../index.html"', page)
        self.assertIn('src="../../assets/gallery.js"', page)
        self.assertNotIn('href="/assets', page)
        self.assertIn(b"prefers-reduced-motion", files["assets/gallery.js"])


if __name__ == "__main__":
    unittest.main()
