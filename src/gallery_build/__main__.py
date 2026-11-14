import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .builder import build, import_manifest, load_project, validate_manifest


def main():
    parser = argparse.ArgumentParser(
        description="Build a static gallery without GitHub or S3 credentials"
    )
    parser.add_argument("command", choices=["import", "validate", "build", "serve"])
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--port", type=int, default=18100)
    args = parser.parse_args()
    if args.command == "import":
        if not args.manifest:
            parser.error("import requires --manifest")
        import_manifest(
            args.project, json.loads(args.manifest.read_text(encoding="utf-8"))
        )
        return
    if args.command == "validate" and args.manifest:
        validate_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
        print("Valid manifest")
        return
    items, css = load_project(args.project)
    media = {
        path.relative_to(args.project).as_posix(): path.read_bytes()
        for path in (args.project / "media").rglob("*.jpg")
    }
    files = build(items, css, media)
    if args.command == "validate":
        print(f"Valid project: {len(items)} exhibitions")
        return
    output = args.output or args.project / "dist"
    # Fresh output avoids stale deleted exhibitions; never recursively delete a user directory.
    if output.exists() and any(output.iterdir()):
        parser.error("Output must be empty; choose a new --output directory")
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print(f"Built {len(items)} exhibitions into {output}")
    if args.command == "serve":
        print(f"http://localhost:{args.port}")
        ThreadingHTTPServer(
            ("127.0.0.1", args.port),
            partial(SimpleHTTPRequestHandler, directory=str(output)),
        ).serve_forever()


if __name__ == "__main__":
    main()
