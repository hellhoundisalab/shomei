from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .music import music

from .catalog import catalog_from_items, catalog_ids, check_catalog_item, upsert_catalog

ROOT = Path(__file__).parent
RUNTIME_SOURCES = {
    p.relative_to(ROOT).as_posix(): p.read_bytes() for p in ROOT.glob("*.py")
}
EXIF_FIELDS = {"camera", "f_number", "exposure_time", "iso", "focal_length"}
ENV = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
)
ENV.filters["display_date"] = lambda value: date.fromisoformat(value).strftime(
    "%d.%m.%Y"
)


def is_dark(color):
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in channels
    ]
    return sum(x * weight for x, weight in zip(linear, (0.2126, 0.7152, 0.0722))) < 0.18


FONT_STACKS = {
    "pt_sans": "'PT Sans',sans-serif",
    "system": "system-ui,sans-serif",
    "georgia": "Georgia,serif",
    "inter": "'Inter',sans-serif",
    "playfair": "'Playfair Display',serif",
    "montserrat": "'Montserrat',sans-serif",
    "merriweather": "'Merriweather',serif",
    "roboto_mono": "'Roboto Mono',monospace",
}
FONT_FILES = {
    "inter": ("Inter", "Inter", "100 900"),
    "playfair": ("PlayfairDisplay", "Playfair Display", "400 900"),
    "montserrat": ("Montserrat", "Montserrat", "100 900"),
    "merriweather": ("Merriweather", "Merriweather", "300 900"),
    "roboto_mono": ("RobotoMono", "Roboto Mono", "100 700"),
}
ENV.filters["font_stack"] = lambda theme: FONT_STACKS[theme.get("font", "pt_sans")]
ENV.filters["title_stack"] = lambda theme: (
    "'PT Sans Narrow',sans-serif"
    if theme.get("font", "pt_sans") == "pt_sans"
    else FONT_STACKS[theme["font"]]
)


def scatter(key, index):
    seed = hashlib.sha256(f"{key}:{index}".encode()).digest()
    angle = (2, -3, 1.5)[index] + (seed[0] / 255 - 0.5) * 2.4
    x = round((seed[1] / 255 - 0.5) * 10, 2)
    y = round((seed[2] / 255 - 0.5) * 10, 2)
    return f"--photo-angle:{angle:.2f}deg;--photo-x:{x}px;--photo-y:{y}px"


ENV.globals["scatter"] = scatter
ENV.filters["music"] = music
ENV.filters["dark"] = is_dark
ENV.filters["ink"] = lambda color: "#f5f4f0" if is_dark(color) else "#15425d"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,79}", value
    ):
        raise ValueError(
            "id: expected 1–80 lowercase letters, digits, hyphens or underscores"
        )
    return value


def _text(value, name, maximum=2000):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ValueError(f"Invalid text: {name}")


def _url(value):
    _text(value, "image URL")
    if re.fullmatch(r"media/[a-z0-9_-]+/[a-z0-9_-]+\.jpg", value):
        return
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or any(c.isspace() for c in value)
        or "\\" in value
    ):
        raise ValueError(
            "Images require a public HTTP(S) URL without credentials or signed parameters"
        )


def validate_manifest(item):
    fields = {
        "schema_version",
        "id",
        "kind",
        "title",
        "author",
        "description",
        "date",
        "theme",
        "photos",
    }
    if not isinstance(item, dict) or set(item) - {"music"} != fields or item["schema_version"] != 1:
        raise ValueError("Manifest v1: missing or unknown fields")
    music(item.get("music"))
    identifier(item["id"])
    if item["kind"] not in {"author", "collective"}:
        raise ValueError("Invalid exhibition kind")
    for key in ("title", "author", "description"):
        _text(item[key], key, 10000 if key == "description" else 300)
    if not item["title"].strip():
        raise ValueError("Title is required")
    _text(item["date"], "date", 10)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["date"]):
        raise ValueError("Date must use YYYY-MM-DD")
    date.fromisoformat(item["date"])
    if (
        not isinstance(item["theme"], dict)
        or not {"background", "accent"} <= set(item["theme"])
        or set(item["theme"]) - {"background", "accent", "font"}
    ):
        raise ValueError("Invalid theme")
    if item["theme"].get("font", "pt_sans") not in FONT_STACKS:
        raise ValueError("Invalid font")
    for key in ("background", "accent"):
        value = item["theme"][key]
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Theme colors must be #RRGGBB")
    if not isinstance(item["photos"], list) or not 1 <= len(item["photos"]) <= 100:
        raise ValueError("Expected 1–100 photographs")
    seen = set()
    for photo in item["photos"]:
        if not isinstance(photo, dict) or set(photo) - {"author"} != {
            "id",
            "url",
            "preview",
            "caption",
            "alt",
            "width",
            "height",
            "exif",
        }:
            raise ValueError("Invalid photograph fields")
        if "author" in photo:
            _text(photo["author"], "photo author", 120)
        identifier(photo["id"])
        if photo["id"] in seen:
            raise ValueError("Duplicate photograph id")
        seen.add(photo["id"])
        _url(photo["url"])
        _url(photo["preview"])
        for key in ("caption", "alt"):
            _text(photo[key], key)
        for key in ("width", "height"):
            if type(photo[key]) is not int or not 1 <= photo[key] <= 100000:
                raise ValueError("Invalid image dimensions")
        if not isinstance(photo["exif"], dict) or set(photo["exif"]) - EXIF_FIELDS:
            raise ValueError("Only public technical EXIF is permitted")
        for value in photo["exif"].values():
            _text(value, "EXIF", 200)
    return item


def source_bytes(path):
    data = RUNTIME_SOURCES[path.name] if path.suffix == ".py" else path.read_bytes()
    return (
        data
        if path.suffix in {".ttf", ".woff2", ".webp"}
        else data.replace(b"\r\n", b"\n")
    )


def renderer_sources():
    return {
        path.relative_to(ROOT).as_posix(): source_bytes(path)
        for path in sorted(ROOT.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix
        in {".py", ".html", ".css", ".js", ".svg", ".ttf", ".woff2", ".webp", ".txt"}
    }


def renderer_revision():
    h = hashlib.sha256()
    for name, content in sorted(renderer_sources().items()):
        h.update(name.encode())
        h.update(content)
    return h.hexdigest()


def build(items, custom_css=None, media=None):
    """Return a complete deterministic site. Input order is the catalog order."""
    if len(items) > 50:
        raise ValueError("Local preview currently supports at most 50 exhibitions")
    for item in items:
        validate_manifest(item)
    items = sorted(items, key=lambda item: item["kind"] != "author")
    if len({x["id"] for x in items}) != len(items):
        raise ValueError("Duplicate exhibition id")
    custom_css = custom_css or {}
    media = media or {}
    for name, content in media.items():
        if (
            not re.fullmatch(r"media/[a-z0-9_-]+/[a-z0-9_-]+\.jpg", name)
            or not isinstance(content, bytes)
            or not content
        ):
            raise ValueError("Invalid bundled media")
    for item in items:
        for photo in item["photos"]:
            for key in ("url", "preview"):
                if photo[key].startswith("media/") and photo[key] not in media:
                    raise ValueError("Missing bundled media: " + photo[key])
    files = {
        "assets/" + p.relative_to(ROOT / "assets").as_posix(): source_bytes(p)
        for p in (ROOT / "assets").rglob("*")
        if p.is_file()
    }
    files.update(media)
    selected_fonts = {item["theme"].get("font", "pt_sans") for item in items}
    face_css = ""
    wanted = set()
    for key in sorted(selected_fonts & FONT_FILES.keys()):
        filename, family, weights = FONT_FILES[key]
        for suffix, style in (("", "normal"), ("-Italic", "italic")):
            name = f"fonts/{filename}{suffix}.ttf"
            wanted.add("assets/" + name)
            face_css += f"@font-face{{font-family:'{family}';src:url('{name}');font-weight:{weights};font-style:{style};font-display:swap}}\n"
    files = {
        name: content
        for name, content in files.items()
        if not name.startswith("assets/fonts/")
        or not name.endswith(".ttf")
        or name in wanted
    }
    # Font requests from an opaque sandbox omit HTTP credentials. Embed the small
    # local font set in CSS, so preview and public output use precisely the same fonts.
    css = face_css + files["assets/gallery.css"].decode()
    for name in list(files):
        if name.endswith(".ttf"):
            encoded = base64.b64encode(files.pop(name)).decode("ascii")
            css = css.replace(
                "url('" + name.removeprefix("assets/") + "')",
                f"url('data:font/ttf;base64,{encoded}')",
            )
    for name in ("back.svg", "back-mobile.svg"):
        encoded = base64.b64encode(files["assets/" + name]).decode("ascii")
        css = css.replace(
            f"url('{name}')", f"url('data:image/svg+xml;base64,{encoded}')"
        )
    files["assets/gallery.css"] = css.encode()
    views = {
        "home": {
            "html": ENV.get_template("home.html").render(items=items, prefix=""),
            "title": "Галерея",
            "background": "#f5f4f0",
            "path": "index.html",
        }
    }
    for item in items:
        views[item["id"]] = {
            "html": ENV.get_template("exhibition.html").render(item=item, prefix=""),
            "title": item["title"],
            "background": item["theme"]["background"],
            "path": f"exhibitions/{item['id']}/index.html",
        }
        files[f"assets/custom-{item['id']}.css"] = custom_css.get(
            item["id"], ""
        ).encode()
    # External JS works inside an opaque-origin sandbox without authenticated fetch.
    files["assets/views.js"] = (
        "window.GALLERY_VIEWS=" + canonical(views) + ";"
    ).encode()
    for key, view in views.items():
        prefix = "" if key == "home" else "../../"
        content = (
            ENV.get_template("home.html").render(items=items, prefix=prefix)
            if key == "home"
            else ENV.get_template("exhibition.html").render(
                item=next(x for x in items if x["id"] == key), prefix=prefix
            )
        )
        files[view["path"]] = (
            ENV.get_template("document.html")
            .render(content=content, key=key, view=view, prefix=prefix)
            .encode()
        )
    files[".nojekyll"] = b""
    return files


def load_project(root):
    root = Path(root)
    catalog = json.loads((root / "content/catalog.json").read_text(encoding="utf-8"))
    from .lifecycle import check_withdrawals, local_markers

    check_withdrawals(catalog, local_markers(root))
    items, css = [], {}
    for key in catalog_ids(catalog):
        identifier(key)
        folder = root / "content/exhibitions" / key
        items.append(
            validate_manifest(
                json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            )
        )
        if items[-1]["id"] != key:
            raise ValueError("Catalog id differs from manifest")
        check_catalog_item(catalog, items[-1])
        if (folder / "custom.css").exists():
            css[key] = (folder / "custom.css").read_text(encoding="utf-8")
    return items, css


def import_manifest(root, item):
    """Upsert only generated data; preserve custom files and an existing position."""
    validate_manifest(item)
    root = Path(root)
    catalog_path = root / "content/catalog.json"
    catalog = (
        json.loads(catalog_path.read_text(encoding="utf-8"))
        if catalog_path.exists()
        else catalog_from_items([])
    )
    if isinstance(catalog, list):
        catalog = catalog_from_items(load_project(root)[0])
    catalog = upsert_catalog(catalog, item)
    folder = root / "content/exhibitions" / item["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(canonical(item) + "\n", encoding="utf-8")
    catalog_path.write_text(canonical(catalog) + "\n", encoding="utf-8")
