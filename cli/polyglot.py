"""Portable Polyglot CLI client.

The CLI calls the existing backend contracts and never embeds migration logic.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
EXIT_SUCCESS = 0
EXIT_VALIDATION = 2
EXIT_AUTH = 3
EXIT_NETWORK = 4
EXIT_UNSUPPORTED = 5


def config_path() -> Path:
    return Path(os.getenv("POLYGLOT_CONFIG", Path.home() / ".polyglot" / "config.json"))


def read_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def endpoint(args: argparse.Namespace) -> str:
    return str(getattr(args, "endpoint", None) or os.getenv("POLYGLOT_API_URL") or read_config().get("endpoint") or "http://127.0.0.1:8000").rstrip("/")


def output(args: argparse.Namespace, value: Any) -> None:
    if getattr(args, "json", False):
        print(json.dumps(value, indent=2, sort_keys=True))
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
    else:
        print(value)


def request(args: argparse.Namespace, path: str, method: str = "GET", body: Any = None) -> Any:
    payload = None if body is None else json.dumps(body).encode()
    request_object = urllib.request.Request(
        endpoint(args) + path, data=payload, method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request_object, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            raise RuntimeError(f"Authentication or authorization failed ({error.code}).") from error
        detail = error.read().decode(errors="replace")
        raise ValueError(f"API request failed ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise ConnectionError(f"Cannot reach Polyglot API at {endpoint(args)}: {error.reason}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="polyglot", description="Polyglot 2.0 backend client")
    parser.add_argument("--version", action="version", version=f"polyglot {VERSION}")
    parser.add_argument("--endpoint", help="Polyglot API URL (or POLYGLOT_API_URL)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check backend health")
    subparsers.add_parser("capabilities", help="Show verified platform capabilities")
    subparsers.add_parser("projects", help="List authorized projects")
    verify = subparsers.add_parser("verify", help="Create a Guardian verification")
    verify.add_argument("project_id")
    verify.add_argument("--mode", default="comprehensive")
    verify.add_argument("--migration-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = request(args, "/health")
        elif args.command == "capabilities":
            result = {
                "guardian": request(args, "/api/v1/guardian/capabilities"),
                "reforge": request(args, "/api/v1/reforge/capabilities"),
            }
        elif args.command == "projects":
            result = request(args, "/api/v1/projects")
        elif args.command == "verify":
            result = request(args, f"/api/v1/projects/{args.project_id}/guardian", "POST", {
                "project_id": args.project_id, "migration_id": args.migration_id,
                "mode": args.mode, "required_quality_gates": ["static_validation"],
            })
        else:
            parser.error("Unsupported command")
        output(args, result)
        return EXIT_SUCCESS
    except ConnectionError as error:
        print(json.dumps({"error": str(error)}) if args.json else str(error), file=sys.stderr)
        return EXIT_NETWORK
    except RuntimeError as error:
        print(json.dumps({"error": str(error)}) if args.json else str(error), file=sys.stderr)
        return EXIT_AUTH
    except ValueError as error:
        print(json.dumps({"error": str(error)}) if args.json else str(error), file=sys.stderr)
        return EXIT_VALIDATION


if __name__ == "__main__":
    raise SystemExit(main())
