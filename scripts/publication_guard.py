"""Read PR data with trusted main code. Never check out or execute PR code."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gallery_build.lifecycle import check_withdrawals, remote_markers
from gallery_build.publication import GitHub, receipt_path
from gallery_build.builder import digest
from gallery_build.catalog import catalog_ids


def check(github, head):
    base = github.main()
    if github.api("GET", f"/compare/{base}...{head}").get("behind_by", 1):
        raise ValueError("Branch is behind main; update it and rerun checks")
    old = remote_markers(github, base)
    new = remote_markers(github, head)
    catalog = json.loads(github.file("content/catalog.json", head))
    check_withdrawals(catalog, new, old)
    before_ids = set(catalog_ids(json.loads(github.file("content/catalog.json", base))))
    after_ids = set(catalog_ids(catalog))
    for key in before_ids | after_ids | (set(new) - set(old)):
        before = (
            json.loads(github.file(f"content/exhibitions/{key}/manifest.json", base))
            if key in before_ids
            else None
        )
        after = (
            json.loads(github.file(f"content/exhibitions/{key}/manifest.json", head))
            if key in after_ids
            else None
        )
        if before == after and key not in set(new) - set(old):
            continue
        actual = json.loads(github.file(receipt_path(key), head))
        expected = {
            "schema_version": 1,
            "operation": "upsert" if after is not None else "withdraw",
            "previous": digest(before) if before is not None else None,
            "current": digest(after) if after is not None else None,
        }
        if actual != expected:
            raise ValueError(
                "Publication was prepared for another revision; rebuild preview"
            )
        if after is None and key not in new:
            raise ValueError(
                "Removing an exhibition requires a permanent withdrawal marker"
            )
    if github.main() != base:
        raise ValueError("main changed during validation; rerun checks")


def report(github, number, expected_sha):
    """Report the trusted guard result for this exact PR revision, never PR code."""
    path = f"/pulls/{int(number)}"
    pr = github.api("GET", path)
    if pr["state"] != "open" or pr["base"]["ref"] != "main":
        raise ValueError("Expected an open PR targeting main")
    if pr["head"]["sha"] != expected_sha:
        raise ValueError("PR changed while check was queued")
    sha = pr["head"]["sha"]

    def status(state, description):
        github.api(
            "POST",
            f"/statuses/{sha}",
            {
                "state": state,
                "context": "publication-safety",
                "description": description,
            },
        )

    status("pending", "Checking withdrawal history against current main")
    try:
        check(github, sha)
        current = github.api("GET", path)
        if current["head"]["sha"] != sha or current["state"] != "open":
            raise ValueError("PR changed during validation")
    except Exception:
        status("failure", "Unsafe publication or outdated branch; inspect the workflow")
        raise
    status("success", "Withdrawal history preserved")
    print("Withdrawal history preserved; no removed exhibition can return")


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    github = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
    report(github, event["number"], event["pull_request"]["head"]["sha"])
