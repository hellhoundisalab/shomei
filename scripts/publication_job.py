"""Trusted Actions entry point. Inputs are data from the event file, never shell code."""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gallery_build.publication import (
    GitHub,
    create_pr,
    prepare_changes,
    validate_payload,
)


def main():
    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    payload = validate_payload(json.loads(event["inputs"]["publication"]))
    mode = sys.argv[1]
    if mode == "prepare":
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if head != payload["base_sha"]:
            raise ValueError("main changed before Actions started; rebuild preview")
        changes, files = prepare_changes(Path.cwd(), payload)
        output = Path("publication")
        output.mkdir()
        (output / "changes.json").write_text(json.dumps(changes), encoding="utf-8")
        for name, data in files.items():
            path = Path("preview") / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        print("Approved preview reproduced; ready to create PR")
    elif mode == "create":
        changes = json.loads(
            Path("publication/changes.json").read_text(encoding="utf-8")
        )
        github = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
        pr = create_pr(github, payload, changes)
        url = f"https://github.com/{github.repository}/pull/{int(pr['number'])}"
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(f"[Открыть PR]({url}) — merge выполняется вручную.\n")
        print(url)
    else:
        raise ValueError("Unknown job mode")


if __name__ == "__main__":
    main()
