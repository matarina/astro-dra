"""Install the repository overlays into the active Python environment."""

import argparse
import ast
import importlib.util
import json
from pathlib import Path
import shutil
import sysconfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.find_spec("local_deep_research")
    if spec is None or not spec.submodule_search_locations:
        parser.error("local_deep_research must be installed first")
    package = Path(next(iter(spec.submodule_search_locations)))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    # Validate every source and target before changing the installed package.
    for source, target in manifest.items():
        ast.parse((args.source / source).read_text(encoding="utf-8"), filename=source)
        if not (package / target).is_file():
            parser.error(f"incompatible base image: missing {target}")
    verify_source = args.source / "research_verify"
    for source in verify_source.rglob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for source, target in manifest.items():
        shutil.copy2(args.source / source, package / target)
        print(f"overlay: {source} -> {target}")
    shutil.copytree(
        verify_source,
        Path(sysconfig.get_path("purelib")) / "research_verify",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


if __name__ == "__main__":
    main()
