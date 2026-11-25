"""Optional music contract. Only known HTTPS provider URLs, never arbitrary embeds."""

import re
from urllib.parse import parse_qs, quote, urlsplit

PROVIDERS = {
    "apple": "Apple Music",
    "bandcamp": "Bandcamp",
    "vk": "VK Музыка",
    "yandex": "Яндекс Музыка",
    "deezer": "Deezer",
    "spotify": "Spotify",
    "soundcloud": "SoundCloud",
    "youtube": "YouTube",
    "mixcloud": "Mixcloud",
}
FRAME_ORIGINS = (
    "https://embed.music.apple.com https://bandcamp.com https://vk.com "
    "https://music.yandex.ru https://widget.deezer.com https://open.spotify.com "
    "https://w.soundcloud.com https://www.youtube.com https://www.mixcloud.com "
    "https://player-widget.mixcloud.com"
)


def music(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = {"url": value.strip()}
    if (
        not isinstance(value, dict)
        or "url" not in value
        or set(value) - {"url", "title", "artist", "bandcamp_id"}
    ):
        raise ValueError("Неверные поля музыки")
    url = value["url"]
    if (
        not isinstance(url, str)
        or len(url) > 1500
        or re.search(r"[\s\\\x00-\x1f]", url)
    ):
        raise ValueError("Вставьте HTTPS-ссылку на музыку")
    p = urlsplit(url)
    if p.scheme != "https" or p.username or p.password or p.port or p.fragment:
        raise ValueError("Нужна HTTPS-ссылка без пароля, порта и фрагмента")
    host, path, query = p.hostname, p.path.rstrip("/"), parse_qs(p.query)
    provider = embed = kind = None
    if host == "music.apple.com" and re.fullmatch(
        r"/[a-z]{2}/(album|playlist|song)/[\w%.-]+/(?:\d+|pl\.[\w-]+)", path
    ):
        provider, kind = "apple", path.split("/")[2]
        suffix = (
            "?i=" + query["i"][0]
            if re.fullmatch(r"\d+", query.get("i", [""])[0])
            else ""
        )
        url = "https://music.apple.com" + path + suffix
        embed = "https://embed.music.apple.com" + path + suffix
    elif (
        host
        and re.fullmatch(r"[a-z0-9-]+\.bandcamp\.com", host)
        and re.fullmatch(r"/(album|track)/[a-zA-Z0-9_-]+", path)
    ):
        provider, kind = "bandcamp", path.split("/")[1]
        url = "https://" + host + path
        ident = value.get("bandcamp_id")
        if ident is not None:
            if not isinstance(ident, str) or not re.fullmatch(
                r"[1-9][0-9]{0,14}", ident
            ):
                raise ValueError("Неверный идентификатор Bandcamp")
            embed = f"https://bandcamp.com/EmbeddedPlayer/{kind}={ident}/size=large/bgcol=ffffff/linkcol=315d4e/artwork=small/transparent=true/"
    elif host in {"vk.com", "vk.ru"} and (
        m := re.fullmatch(r"/music/playlist/(-?\d+)_(\d+)_([a-fA-F0-9]+)", path)
    ):
        provider, kind = "vk", "playlist"
        url = "https://vk.com" + path
        embed = f"https://vk.com/widget_playlist.php?app=0&width=100%25&_ver=1&oid={m[1]}&pid={m[2]}&hash={m[3]}"
    elif host in {"music.yandex.ru", "music.yandex.com"} and (
        m := re.fullmatch(r"/album/(\d+)(?:/track/(\d+))?", path)
    ):
        provider, kind = "yandex", "track" if m[2] else "album"
        url = "https://music.yandex.ru" + path
        embed = "https://music.yandex.ru/iframe/#" + (
            f"track/{m[2]}/{m[1]}" if m[2] else f"album/{m[1]}"
        )
    elif host in {"www.deezer.com", "deezer.com"} and (
        m := re.fullmatch(r"/(?:[a-z]{2}/)?(track|album|playlist)/(\d+)", path)
    ):
        provider, kind = "deezer", m[1]
        url = f"https://www.deezer.com/{kind}/{m[2]}"
        embed = f"https://widget.deezer.com/widget/dark/{kind}/{m[2]}"
    elif host == "open.spotify.com" and (
        m := re.fullmatch(
            r"/(?:intl-[a-z]{2}/)?(track|album|playlist)/([a-zA-Z0-9]{22})", path
        )
    ):
        provider, kind = "spotify", m[1]
        url = f"https://open.spotify.com/{kind}/{m[2]}"
        embed = f"https://open.spotify.com/embed/{kind}/{m[2]}"
    elif host in {"soundcloud.com", "www.soundcloud.com"} and re.fullmatch(
        r"/[\w-]+/(?:sets/)?[\w-]+", path
    ):
        provider, kind = "soundcloud", "playlist" if "/sets/" in path else "track"
        url = "https://soundcloud.com" + path
        embed = (
            "https://w.soundcloud.com/player/?url="
            + quote(url, safe="")
            + "&auto_play=false&visual=true"
        )
    elif host in {"www.youtube.com", "youtube.com", "music.youtube.com", "youtu.be"}:
        ident = path[1:] if host == "youtu.be" else query.get("v", [""])[0]
        playlist = query.get("list", [""])[0]
        if re.fullmatch(r"[\w-]{11}", ident) and (
            host == "youtu.be" or path == "/watch"
        ):
            provider, kind = "youtube", "track"
            url = "https://www.youtube.com/watch?v=" + ident
            embed = "https://www.youtube.com/embed/" + ident + "?autoplay=0"
        elif path == "/playlist" and re.fullmatch(r"[\w-]{10,100}", playlist):
            provider, kind = "youtube", "playlist"
            url = "https://www.youtube.com/playlist?list=" + playlist
            embed = "https://www.youtube.com/embed/videoseries?list=" + playlist
    elif host in {"mixcloud.com", "www.mixcloud.com"} and re.fullmatch(
        r"/[\w-]+/[\w-]+", path
    ):
        provider, kind = "mixcloud", "track"
        url = "https://www.mixcloud.com" + path + "/"
        embed = "https://www.mixcloud.com/widget/iframe/?hide_cover=1&feed=" + quote(
            url, safe=""
        )
    if not provider:
        raise ValueError(
            "Ссылка не поддерживается. Нужна полная ссылка на трек, альбом или плейлист поддерживаемого сервиса (для VK — плейлист)."
        )
    if "bandcamp_id" in value and provider != "bandcamp":
        raise ValueError("Идентификатор Bandcamp не соответствует сервису")
    for field in ("title", "artist"):
        text = value.get(field, "")
        if (
            not isinstance(text, str)
            or len(text) > 150
            or any(ord(c) < 32 for c in text)
        ):
            raise ValueError("Название и исполнитель: не более 150 символов")
    return {
        "url": url,
        "provider": provider,
        "name": PROVIDERS[provider],
        "kind": kind,
        "embed": embed,
        "title": value.get("title", ""),
        "artist": value.get("artist", ""),
    }


def record(value):
    parsed = music(value)
    if not parsed:
        return None
    result = {
        "url": parsed["url"],
        "title": parsed["title"],
        "artist": parsed["artist"],
    }
    if isinstance(value, dict) and value.get("bandcamp_id"):
        result["bandcamp_id"] = value["bandcamp_id"]
    return result
