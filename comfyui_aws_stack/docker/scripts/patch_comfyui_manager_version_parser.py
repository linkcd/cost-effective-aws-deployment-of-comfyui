#!/usr/bin/env python3
"""Patch ComfyUI-Manager's version parser to accept semver prereleases."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile


OLD_PARSER = """\
    def parse_version_string(self):
        parts = self.version_string.split('.')
        if not parts:
            raise ValueError("Version string must not be empty")

        self.major = int(parts[0])
        self.minor = int(parts[1]) if len(parts) > 1 else 0
        self.patch = int(parts[2]) if len(parts) > 2 else 0

        # Handling pre-release versions if present
        if len(parts) > 3:
            self.pre_release = parts[3]
"""

FIXED_PARSER = """\
    def parse_version_string(self):
        # Handle semver pre-release suffix: "1.2.3-beta.1"
        core = self.version_string
        if '-' in core:
            dash_pos = core.index('-')
            self.pre_release = core[dash_pos + 1:]
            core = core[:dash_pos]

        parts = core.split('.')
        if not parts:
            raise ValueError("Version string must not be empty")

        self.major = int(parts[0])
        self.minor = int(parts[1]) if len(parts) > 1 else 0
        self.patch = int(parts[2]) if len(parts) > 2 else 0

        # Also handle legacy 4-part dot notation: "1.2.3.beta1"
        if self.pre_release is None and len(parts) > 3:
            self.pre_release = parts[3]
"""


def patch_manager_version_parser(manager_util_path: Path) -> str:
    """Apply the upstream-compatible parser fix and return the result."""
    if not manager_util_path.exists():
        return "manager file not found"

    source = manager_util_path.read_text(encoding="utf-8")
    if (
        "core = self.version_string" in source
        and "self.pre_release = core[dash_pos + 1:]" in source
    ):
        return "already fixed"

    if OLD_PARSER not in source:
        return "parser layout not recognized; skipped"

    updated_source = source.replace(OLD_PARSER, FIXED_PARSER, 1)
    original_mode = stat.S_IMODE(manager_util_path.stat().st_mode)

    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=manager_util_path.parent,
        prefix=f".{manager_util_path.name}.",
        delete=False,
    ) as temp_file:
        temp_file.write(updated_source)
        temp_path = Path(temp_file.name)

    os.chmod(temp_path, original_mode)
    os.replace(temp_path, manager_util_path)
    return "patched"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manager_util_path", type=Path)
    args = parser.parse_args()

    result = patch_manager_version_parser(args.manager_util_path)
    print(f"ComfyUI-Manager prerelease version parser: {result}")


if __name__ == "__main__":
    main()
