from __future__ import annotations

import argparse
import json
from pathlib import Path

from knowledgeops_py.scripts.java_baseline_manifest import build_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify that the committed Java baseline manifest is current")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    committed = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected = build_manifest(args.repository, str(committed["baselineSha"]))
    if committed != expected:
        raise SystemExit("Java baseline manifest is stale; regenerate it from the fixed SHA")
    print(f"java baseline manifest verified: {committed['baselineSha']}")


if __name__ == "__main__":
    main()
