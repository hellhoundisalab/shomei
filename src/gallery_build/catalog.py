"""Ordered home-page collections; legacy flat catalogs remain readable."""

import re

KINDS = ("author", "collective")


def catalog_ids(value):
    if isinstance(value, dict):
        if (
            set(value) != {"schema_version", *KINDS}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
        ):
            raise ValueError("Invalid catalog schema")
        if any(not isinstance(value[kind], list) for kind in KINDS):
            raise ValueError("Catalog sections must be ordered lists")
        ids = [key for kind in KINDS for key in value[kind]]
    elif isinstance(value, list):
        ids = list(value)
    else:
        raise ValueError("Invalid catalog")  # noqa: TRY004 - malformed JSON uses the validation error contract
    if (
        len(ids) > 50
        or any(
            not isinstance(key, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", key)
            for key in ids
        )
        or len(set(ids)) != len(ids)
    ):
        raise ValueError(
            "Catalog must contain unique valid exhibition ids (at most 50)"
        )
    return ids


def catalog_from_items(items):
    result = {"schema_version": 1, **{kind: [] for kind in KINDS}}
    for item in items:
        if item["kind"] not in KINDS:
            raise ValueError("Invalid exhibition kind")
        result[item["kind"]].append(item["id"])
    catalog_ids(result)
    return result


def check_catalog_item(catalog, item):
    if isinstance(catalog, dict) and item["id"] not in catalog[item["kind"]]:
        raise ValueError("Catalog section differs from manifest kind")


def upsert_catalog(catalog, item):
    """Existing positions survive edits; new/moved items lead their section."""
    catalog_ids(catalog)
    if not isinstance(catalog, dict) or item["kind"] not in KINDS:
        raise ValueError("Upsert requires a structured catalog and a valid kind")
    result = {"schema_version": 1, **{kind: list(catalog[kind]) for kind in KINDS}}
    key, kind = item["id"], item["kind"]
    for other in KINDS:
        if other != kind and key in result[other]:
            result[other].remove(key)
    if key not in result[kind]:
        result[kind].insert(0, key)
    catalog_ids(result)
    return result
