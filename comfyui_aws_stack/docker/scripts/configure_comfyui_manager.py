#!/usr/bin/env python3
"""Apply explicitly requested ComfyUI-Manager settings."""

from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


INSTALL_FLAGS = {
    "allow_git_url_install": "true",
    "allow_pip_install": "true",
    "file_logging": "false",
}


def configure_manager(config_path: Path) -> bool:
    """Merge installation flags into Manager config and report if it changed."""
    config = configparser.ConfigParser(strict=False)

    if config_path.exists():
        with config_path.open(encoding="utf-8") as config_file:
            config.read_file(config_file)

    if not config.has_section("default"):
        config.add_section("default")

    changed = False
    for key, value in INSTALL_FLAGS.items():
        if config.get("default", key, fallback="").lower() != value:
            config.set("default", key, value)
            changed = True

    if not changed:
        return False

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=config_path.parent,
        prefix=f".{config_path.name}.",
        delete=False,
    ) as temp_file:
        config.write(temp_file)
        temp_path = Path(temp_file.name)

    os.replace(temp_path, config_path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config_path", type=Path)
    args = parser.parse_args()

    changed = configure_manager(args.config_path)
    state = "updated" if changed else "already configured"
    print(f"ComfyUI-Manager install permissions: {state}")


if __name__ == "__main__":
    main()
