from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def git(repository: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repository), *args], check=True, text=True, capture_output=True).stdout


def build_manifest(repository: Path, revision: str) -> dict[str, object]:
    migration_paths = [line for line in git(repository, "ls-tree", "-r", "--name-only", revision, "src/main/resources/db/migration").splitlines() if line.endswith(".sql")]
    controller_paths = [line for line in git(repository, "ls-tree", "-r", "--name-only", revision, "src/main/java/com/enterprise/iqk").splitlines() if line.endswith("Controller.java")]
    routes: list[dict[str, str]] = []
    for path in controller_paths:
        source = git(repository, "show", f"{revision}:{path}")
        prefix_match = re.search(r'@RequestMapping\("([^"]+)"\)', source)
        prefix = prefix_match.group(1) if prefix_match else ""
        for match in re.finditer(r'@(Get|Post|Put|Delete)Mapping(?:\(\s*(?:value\s*=\s*)?"([^"\n]*)"[^\)]*\))?', source):
            method, suffix = match.group(1), match.group(2) or ""
            routes.append({"method": method.upper(), "path": f"{prefix}{suffix}".replace("//", "/")})
    schema_tables: list[str] = []
    for path in migration_paths:
        sql = git(repository, "show", f"{revision}:{path}")
        schema_tables.extend(re.findall(r"CREATE TABLE(?: IF NOT EXISTS)?\s+`?([a-zA-Z0-9_]+)`?", sql, flags=re.IGNORECASE))
    return {
        "baselineSha": revision,
        "migrations": migration_paths,
        "tables": sorted(set(schema_tables)),
        "routes": sorted(routes, key=lambda item: (item["path"], item["method"])),
        "sseEventContract": ["trace", "token", "done", "error"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the fixed Java baseline contract manifest")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.repository, args.revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
