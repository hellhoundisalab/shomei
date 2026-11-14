"""Public-data publication contract; never accepts executable files from review."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .builder import (
    build,
    canonical,
    digest,
    renderer_revision,
    renderer_sources,
    validate_manifest,
)
from .catalog import catalog_from_items, catalog_ids, check_catalog_item, upsert_catalog
from .lifecycle import assert_not_withdrawn, marker, marker_path, local_markers

WORKFLOW = "prepare-exhibition.yml"
MAX_PAYLOAD = 48000
SHA = re.compile(r"[0-9a-f]{40}")


class PublicationError(ValueError):
    pass


class GitHub:
    """Fixed GitHub origin; errors never include credentials or response bodies."""

    def __init__(self, repository, token="", transport=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise PublicationError("Задайте репозиторий галереи в формате owner/repo")
        self.repository = repository
        self.token = token
        self.transport = transport

    def api(self, method, path, data=None, missing=False):
        if not path.startswith("/") or ".." in path:
            raise PublicationError("Invalid GitHub API path")
        if self.transport:
            return self.transport(method, path, data, missing)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        raw = None if data is None else json.dumps(data).encode()
        if raw:
            headers["Content-Type"] = "application/json"
        request = Request(
            "https://api.github.com/repos/"
            + self.repository
            + ("" if path == "/" else path),
            data=raw,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise PublicationError("Ответ GitHub превышает лимит")
                return json.loads(body) if body else None
        except HTTPError as error:
            if missing and error.code == 404:
                return None
            raise PublicationError(
                f"GitHub HTTP {error.code}: проверьте доступ и состояние workflow"
            ) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise PublicationError(
                "GitHub недоступен или вернул некорректный ответ"
            ) from None

    def main(self):
        return self.api("GET", "/git/ref/heads/main")["object"]["sha"]

    def file(self, path, ref):
        item = self.api("GET", "/contents/" + path + "?" + urlencode({"ref": ref}))
        if (
            item.get("type") != "file"
            or item.get("encoding") != "base64"
            or item.get("size", 0) > 512000
        ):
            raise PublicationError("Неподдерживаемый файл в каталоге GitHub")
        return base64.b64decode(item["content"]).decode("utf-8")

    def pulls(self, branch=None, state="all"):
        params = {"state": state, "base": "main", "per_page": 100}
        if branch:
            params["head"] = self.repository.split("/")[0] + ":" + branch
        return self.api("GET", "/pulls?" + urlencode(params))

    def dispatch(self, payload):
        if not self.token:
            raise PublicationError("Не настроен токен запуска GitHub Actions")
        self.api(
            "POST",
            f"/actions/workflows/{WORKFLOW}/dispatches",
            {"ref": "main", "inputs": {"publication": canonical(payload)}},
        )


def public_manifest(item):
    validate_manifest(item)
    for photo in item["photos"]:
        for key in ("url", "preview"):
            parsed = urlsplit(photo[key])
            host = (parsed.hostname or "").lower()
            if (
                parsed.scheme != "https"
                or not host
                or "." not in host
                or host.endswith(
                    (".localhost", ".local", ".internal", ".test", ".invalid")
                )
                or host == "localhost"
            ):
                raise PublicationError(
                    "Для PR нужны публичные HTTPS-ссылки на S3, не локальные фотографии"
                )
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                if not ip.is_global:
                    raise PublicationError(
                        "Приватные адреса фотографий нельзя публиковать"
                    )
    return item


def merge_catalog(items, item):
    public_manifest(item)
    existing = [x["id"] for x in items]
    if item["id"] in existing:
        if items[existing.index(item["id"])]["kind"] != item["kind"]:
            return [item, *[x for x in items if x["id"] != item["id"]]]
        return [item if x["id"] == item["id"] else x for x in items]
    return [item, *items]


def site_digest(files):
    return digest(
        {path: hashlib.sha256(data).hexdigest() for path, data in sorted(files.items())}
    )


def renderer_tree():
    return {
        "src/gallery_build/" + name: hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest()
        for name, data in renderer_sources().items()
    }


def repository_snapshot(github):
    metadata = github.api("GET", "/")
    if metadata.get("private") or metadata.get("default_branch") != "main":
        raise PublicationError(
            "Нужен публичный репозиторий галереи с основной веткой main"
        )
    sha = github.main()
    tree = github.api("GET", f"/git/trees/{sha}?recursive=1")
    if tree.get("truncated"):
        raise PublicationError("Дерево репозитория превышает лимит")
    nodes = {x["path"]: x for x in tree["tree"]}
    expected = renderer_tree()
    actual = {
        path: node["sha"]
        for path, node in nodes.items()
        if path.startswith("src/gallery_build/")
        and node["type"] == "blob"
        and path.rsplit(".", 1)[-1]
        in {"py", "html", "css", "js", "svg", "ttf", "woff2", "txt"}
    }
    if actual != expected or any(
        nodes[p]["mode"] not in {"100644", "100755"} for p in expected
    ):
        raise PublicationError(
            "Сборщик админки отличается от main галереи. Сначала синхронизируйте версии"
        )
    if f".github/workflows/{WORKFLOW}" not in nodes:
        raise PublicationError("В main галереи отсутствует workflow подготовки PR")
    catalog = json.loads(github.file("content/catalog.json", sha))
    ids = catalog_ids(catalog)
    items, css = [], {}
    for key in ids:
        path = f"content/exhibitions/{key}/manifest.json"
        if nodes.get(path, {}).get("mode") != "100644":
            raise PublicationError("Manifest должен быть обычным файлом")
        item = public_manifest(json.loads(github.file(path, sha)))
        if item["id"] != key:
            raise PublicationError("ID manifest не совпадает с каталогом")
        check_catalog_item(catalog, item)
        items.append(item)
        path = f"content/exhibitions/{key}/custom.css"
        if path in nodes:
            if nodes[path]["mode"] != "100644":
                raise PublicationError("custom.css должен быть обычным файлом")
            css[key] = github.file(path, sha)
    return sha, items, css


def make_payload(base, manifest, files, operation="upsert", previous=None):
    payload = {
        "schema_version": 2,
        "operation": operation,
        "previous_manifest": digest(previous) if previous is not None else None,
        "base_sha": base,
        "manifest": public_manifest(manifest) if operation == "upsert" else manifest,
        "renderer_revision": renderer_revision(),
        "site_sha256": site_digest(files),
    }
    payload["job_id"] = digest(payload)
    validate_payload(payload)
    return payload


def validate_payload(payload):
    fields = {
        "schema_version",
        "base_sha",
        "manifest",
        "renderer_revision",
        "site_sha256",
        "job_id",
    }
    if isinstance(payload, dict) and payload.get("schema_version") == 2:
        fields.update({"operation", "previous_manifest"})
    if (
        not isinstance(payload, dict)
        or set(payload) != fields
        or payload["schema_version"] not in (1, 2)
        or payload.get("operation", "upsert") not in ("upsert", "withdraw")
    ):
        raise PublicationError("Invalid publication payload")
    if len(canonical(payload).encode()) > MAX_PAYLOAD:
        raise PublicationError("Данные выставки превышают лимит отправки 48 КБ")
    if not isinstance(payload["base_sha"], str) or not SHA.fullmatch(
        payload["base_sha"]
    ):
        raise PublicationError("Invalid base SHA")
    previous = payload.get("previous_manifest")
    if previous is not None and (
        not isinstance(previous, str) or not re.fullmatch(r"[a-f0-9]{64}", previous)
    ):
        raise PublicationError("Invalid previous manifest digest")
    for key in ("renderer_revision", "site_sha256", "job_id"):
        if not isinstance(payload[key], str) or not re.fullmatch(
            r"[0-9a-f]{64}", payload[key]
        ):
            raise PublicationError("Invalid publication digest")
    if payload.get("operation") == "withdraw":
        if not isinstance(payload["manifest"], dict) or set(payload["manifest"]) != {
            "id"
        }:
            raise PublicationError("Invalid withdrawal target")
        marker_path(payload["manifest"]["id"])
    else:
        public_manifest(payload["manifest"])
    if digest({k: v for k, v in payload.items() if k != "job_id"}) != payload["job_id"]:
        raise PublicationError("Publication payload changed")
    return payload


def branch_name(payload):
    validate_payload(payload)
    return f"publish/{payload['manifest']['id']}/{payload['job_id'][:24]}"


def receipt_path(key):
    marker_path(key)
    return f"content/publications/{key}.json"


def receipt(payload):
    return {
        "schema_version": 1,
        "operation": payload.get("operation", "upsert"),
        "previous": payload.get("previous_manifest"),
        "current": None
        if payload.get("operation") == "withdraw"
        else digest(payload["manifest"]),
    }


def check_previous(payload, previous):
    if payload.get("schema_version") != 2:
        raise PublicationError("Old publication format; prepare a new preview")
    if payload["previous_manifest"] != (
        digest(previous) if previous is not None else None
    ):
        raise PublicationError(
            "Previous exhibition revision changed; prepare a new preview"
        )


def prepare_changes(root, payload):
    """Runs in a read-only Actions job; output must match the approved preview."""
    from .builder import load_project

    validate_payload(payload)
    if payload["renderer_revision"] != renderer_revision():
        raise PublicationError("Renderer changed; rebuild preview")
    items, css = load_project(root)
    for item in items:
        public_manifest(item)
    key = payload["manifest"]["id"]
    check_previous(payload, next((item for item in items if item["id"] == key), None))
    if payload.get("operation") == "withdraw":
        items = [x for x in items if x["id"] != key]
        css.pop(key, None)
    else:
        if key in local_markers(root):
            raise PublicationError("Withdrawn exhibition cannot be published")
        items = merge_catalog(items, payload["manifest"])
    files = build(items, css)
    if site_digest(files) != payload["site_sha256"]:
        raise PublicationError("Build differs from approved preview")
    key = payload["manifest"]["id"]
    if payload.get("operation") == "withdraw":
        return {
            "content/catalog.json": canonical(catalog_from_items(items)) + "\n",
            marker_path(key): canonical(marker(key)) + "\n",
            receipt_path(key): canonical(receipt(payload)) + "\n",
        }, files
    return {
        "content/catalog.json": canonical(catalog_from_items(items)) + "\n",
        receipt_path(key): canonical(receipt(payload)) + "\n",
        f"content/exhibitions/{key}/manifest.json": canonical(payload["manifest"])
        + "\n",
    }, files


def create_pr(github, payload, changes):
    """Only three generated data paths; no ref updates, force push or merge API."""
    validate_payload(payload)
    branch = branch_name(payload)
    existing = github.pulls(branch)
    if existing:
        return existing[
            0
        ]  # Closed/merged and manually edited PRs are never overwritten.
    key = payload["manifest"]["id"]
    withdrawing = payload.get("operation") == "withdraw"
    manifest_path = (
        marker_path(key) if withdrawing else f"content/exhibitions/{key}/manifest.json"
    )
    expected_data = marker(key) if withdrawing else payload["manifest"]
    if (
        set(changes) != {"content/catalog.json", manifest_path, receipt_path(key)}
        or changes[receipt_path(key)] != canonical(receipt(payload)) + "\n"
        or changes[manifest_path] != canonical(expected_data) + "\n"
    ):
        raise PublicationError("Unexpected publication files")
    catalog = json.loads(github.file("content/catalog.json", payload["base_sha"]))
    ids = catalog_ids(catalog)
    previous_item = (
        json.loads(
            github.file(f"content/exhibitions/{key}/manifest.json", payload["base_sha"])
        )
        if key in ids
        else None
    )
    check_previous(payload, previous_item)
    if isinstance(catalog, list):
        previous = []
        for sid in ids:
            old = public_manifest(
                json.loads(
                    github.file(
                        f"content/exhibitions/{sid}/manifest.json", payload["base_sha"]
                    )
                )
            )
            if old["id"] != sid:
                raise PublicationError("ID manifest не совпадает с каталогом")
            previous.append(old)
        catalog = catalog_from_items(previous)
    if withdrawing:
        catalog = {
            **catalog,
            **{
                kind: [sid for sid in catalog[kind] if sid != key]
                for kind in ("author", "collective")
            },
        }
    else:
        assert_not_withdrawn(github, payload["base_sha"], key)
        catalog = upsert_catalog(catalog, payload["manifest"])
    if changes["content/catalog.json"] != canonical(catalog) + "\n":
        raise PublicationError("Unexpected catalog changes")
    for pr in github.pulls(state="open"):
        if not withdrawing and pr["head"]["ref"].startswith(f"publish/{key}/"):
            raise PublicationError(
                "Для выставки уже открыт другой PR; завершите его вручную"
            )
    if github.main() != payload["base_sha"]:
        raise PublicationError("main changed; rebuild preview")
    base = github.api("GET", "/git/commits/" + payload["base_sha"])
    tree = github.api(
        "POST",
        "/git/trees",
        {
            "base_tree": base["tree"]["sha"],
            "tree": [
                {"path": p, "mode": "100644", "type": "blob", "content": text}
                for p, text in sorted(changes.items())
            ],
        },
    )
    if tree["sha"] == base["tree"]["sha"]:
        raise PublicationError("Эта версия уже есть в main; изменений для PR нет")
    ref = github.api("GET", "/git/ref/heads/" + branch, missing=True)
    if ref:
        commit = github.api("GET", "/git/commits/" + ref["object"]["sha"])
        if commit["tree"]["sha"] != tree["sha"] or [
            x["sha"] for x in commit["parents"]
        ] != [payload["base_sha"]]:
            raise PublicationError(
                "Ветка изменена вручную; автоматическая перезапись запрещена"
            )
    else:
        commit = github.api(
            "POST",
            "/git/commits",
            {
                "message": f"{'Withdraw' if withdrawing else 'Update'} gallery exhibition {key}",
                "tree": tree["sha"],
                "parents": [payload["base_sha"]],
            },
        )
        # Recheck after preparing Git objects; a later merge conflict still requires human review.
        if github.main() != payload["base_sha"]:
            raise PublicationError("main changed; rebuild preview")
        github.api(
            "POST", "/git/refs", {"ref": "refs/heads/" + branch, "sha": commit["sha"]}
        )
    return github.api(
        "POST",
        "/pulls",
        {
            "title": f"{'Снять выставку' if withdrawing else 'Выставка'}: {payload['manifest'].get('title', key)}"[
                :200
            ],
            "head": branch,
            "base": "main",
            "body": (
                "Снимает выставку с сайта и навсегда запрещает повторную публикацию этого ID. Файлы S3 пока сохраняются.\n\n"
                if withdrawing
                else "Добавляет или обновляет выставку и ссылку на неё в каталоге. Ручные файлы сохраняются.\n\n"
            )
            + f"Проверена сборка согласованного предпросмотра `{payload['site_sha256']}`.\n"
            + f"База: `{payload['base_sha']}`. Задание: `{payload['job_id']}`.\n\n"
            + "Проверьте изменения и объедините PR вручную. Публикация Pages запускается только после merge в main. "
            + "Если GitHub показывает Approve workflows to run, разрешите запуск CI. После ручных правок проверяйте новый artifact CI.",
        },
    )
