"""Permanent withdrawal markers. Publication cannot reuse a withdrawn identity."""

import json
import re
from pathlib import Path

from .catalog import catalog_ids


def marker_path(key):
    if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", key):
        raise ValueError("Invalid exhibition id")
    return f"content/withdrawn/{key}.json"


def marker(key):
    marker_path(key)
    return {"schema_version": 1, "id": key}


def local_markers(root):
    result = {}
    for path in (Path(root) / "content/withdrawn").glob("*.json"):
        key = path.stem
        value = json.loads(path.read_text(encoding="utf-8"))
        if value != marker(key) or path.is_symlink():
            raise ValueError("Invalid withdrawal marker")
        result[key] = value
    return result


def check_withdrawals(catalog, withdrawn, previous=None):
    if previous is not None and any(withdrawn.get(k) != v for k, v in previous.items()):
        raise ValueError("Withdrawal markers cannot be removed or changed")
    if set(catalog_ids(catalog)) & set(withdrawn):
        raise ValueError("Withdrawn exhibition cannot return to the catalog")


def remote_markers(github, ref):
    tree = github.api("GET", f"/git/trees/{ref}?recursive=1")
    if tree.get("truncated"):
        raise ValueError("Truncated repository tree")
    result = {}
    for node in tree["tree"]:
        path = node["path"]
        if not path.startswith("content/withdrawn/") or node["type"] != "blob":
            continue
        key = path.removeprefix("content/withdrawn/").removesuffix(".json")
        if path != marker_path(key) or node["mode"] != "100644":
            raise ValueError("Invalid withdrawal path")
        value = json.loads(github.file(path, ref))
        if value != marker(key):
            raise ValueError("Invalid withdrawal marker")
        result[key] = value
    return result


def assert_not_withdrawn(github, ref, key):
    if key in remote_markers(github, ref):
        raise ValueError("Выставка снята. Повторная публикация этого ID запрещена")
