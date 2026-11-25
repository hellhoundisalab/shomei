import copy
import unittest

from gallery_build.builder import build, validate_manifest
from gallery_build.music import music, record
from test_builder import example


class MusicTests(unittest.TestCase):
    def test_known_urls_normalize_without_tracking_or_autoplay(self):
        cases = [
            (
                "https://music.apple.com/ru/album/abbey-road-remastered/1441164426?i=1441164589&at=123",
                "apple",
            ),
            (
                "https://mogwai.bandcamp.com/album/mogwai-young-team-remastered",
                "bandcamp",
            ),
            ("https://vk.com/music/playlist/-2089898_84_9c8e0a5941d53296f4", "vk"),
            ("https://music.yandex.ru/album/419460/track/71263", "yandex"),
            ("https://www.deezer.com/ru/track/3135556?autoplay=1", "deezer"),
            (
                "https://open.spotify.com/intl-ru/album/0Lr4kGOYn9l83EjuK6cZFQ?si=xyz",
                "spotify",
            ),
            ("https://soundcloud.com/forss/flickermood", "soundcloud"),
            ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
            ("https://music.youtube.com/playlist?list=PLabcdefgh123456", "youtube"),
            ("https://www.mixcloud.com/spartacus/party-time/", "mixcloud"),
        ]
        for url, provider in cases:
            with self.subTest(provider=provider):
                result = music(url)
                self.assertEqual(result["provider"], provider)
                self.assertNotIn("autoplay=1", result["embed"] or "")
                self.assertEqual(record(record(url)), record(url))
        bandcamp = music({"url": cases[1][0], "bandcamp_id": "3142231699"})
        self.assertIn("/album=3142231699/", bandcamp["embed"])

    def test_rejects_ssrf_html_unknown_fields_and_host_confusion(self):
        for value in [
            "http://music.apple.com/ru/album/a/123",
            "https://127.0.0.1/track/123",
            "https://music.apple.com.evil.test/ru/album/a/123",
            "https://music.apple.com@evil.test/ru/album/a/123",
            "https://evil@music.apple.com/ru/album/a/123",
            "https://music.apple.com:443/ru/album/a/123",
            "javascript:alert(1)",
            "https://music.apple.com/ru/album/a/123#secret",
            "https://soundcloud.com/a/../private",
            "https://a.bandcamp.com/album/a\\evil",
            {"url": "https://youtu.be/dQw4w9WgXcQ", "embed": "https://evil.test"},
            {"url": "https://a.bandcamp.com/track/a", "bandcamp_id": "123/evil"},
            {"url": "https://youtu.be/dQw4w9WgXcQ", "artist": []},
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                music(value)

    def test_old_new_and_empty_music_manifests_render_without_migration(self):
        old = example()
        self.assertNotIn(
            "data-music=", build([old])["exhibitions/example/index.html"].decode()
        )
        empty = copy.deepcopy(old)
        empty["music"] = None
        validate_manifest(empty)
        new = copy.deepcopy(old)
        new["music"] = {
            "url": "https://youtu.be/dQw4w9WgXcQ",
            "title": "</div><script>bad()</script>",
            "artist": "Автор",
        }
        files = build([new])
        html = files["exhibitions/example/index.html"].decode()
        self.assertIn("data-music=", html)
        self.assertNotIn("<script>bad()", html)
        self.assertIn("assets/music.js", files)
        self.assertIn("youtube.com/embed", files["assets/views.js"].decode())
        self.assertEqual(old, example())
