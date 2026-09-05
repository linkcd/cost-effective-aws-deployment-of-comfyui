#!/usr/bin/env python3
"""Remove prompt-bearing data from ComfyUI core and API-node logs."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import NamedTuple


class Replacement(NamedTuple):
    old: str
    new: str
    expected_count: int = 1


SERVER_REPLACEMENTS = (
    Replacement(
        old='                    logging.warning("invalid prompt: {}".format(valid[1]))',
        new='                    logging.warning("invalid prompt rejected")',
    ),
    Replacement(
        old="""\
            except Exception:
                logging.warning("[ERROR] An error occurred during the on_prompt_handler processing")
                logging.warning(traceback.format_exc())
""",
        new="""\
            except Exception as ex:
                logging.warning(
                    "[ERROR] An error occurred during on_prompt_handler processing; "
                    "exception=%s",
                    type(ex).__name__,
                )
""",
    ),
)

EXECUTION_REPLACEMENTS = (
    Replacement(
        old="""\
        logging.error(f"!!! Exception during processing !!! {ex}")
        logging.error(traceback.format_exc())
""",
        new="""\
        logging.error(
            "!!! Exception during processing !!! node=%s class=%s exception=%s",
            real_node_id,
            class_type,
            exception_type,
        )
""",
    ),
    Replacement(
        old='                    logging.error(f"  - {reason[\'message\']}: {reason[\'details\']}")',
        new='                    logging.error("  - validation error type=%s", reason.get("type", "unknown"))',
        expected_count=2,
    ),
)

API_REQUEST_LOG_GUARD = Replacement(
    old="""\
    If we still fail to write, we fall back to appending into api.log.
    \"\"\"
    try:
""",
    new="""\
    If we still fail to write, we fall back to appending into api.log.
    \"\"\"
    if os.environ.get("COMFYUI_DISABLE_API_REQUEST_LOGGING") == "1":
        return

    try:
""",
)


def patch_file(path: Path, replacements: tuple[Replacement, ...]) -> bool:
    """Apply guarded replacements and report whether the file changed."""
    if not path.is_file():
        raise RuntimeError(f"required ComfyUI file not found: {path}")

    source = path.read_text(encoding="utf-8")
    updated = source

    for replacement in replacements:
        old_count = updated.count(replacement.old)
        new_count = updated.count(replacement.new)

        if old_count == replacement.expected_count and new_count == 0:
            updated = updated.replace(
                replacement.old,
                replacement.new,
                replacement.expected_count,
            )
            continue

        if old_count == 0 and new_count == replacement.expected_count:
            continue

        raise RuntimeError(
            f"privacy logging layout not recognized in {path}: "
            f"old_count={old_count}, new_count={new_count}, "
            f"expected={replacement.expected_count}"
        )

    if updated == source:
        return False

    original_mode = stat.S_IMODE(path.stat().st_mode)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temp_file:
        temp_file.write(updated)
        temp_path = Path(temp_file.name)

    os.chmod(temp_path, original_mode)
    os.replace(temp_path, path)
    return True


def patch_comfyui_privacy_logging(comfyui_root: Path) -> str:
    """Patch all known prompt-bearing ComfyUI log paths."""
    targets = (
        (comfyui_root / "server.py", SERVER_REPLACEMENTS),
        (comfyui_root / "execution.py", EXECUTION_REPLACEMENTS),
        (
            comfyui_root / "comfy_api_nodes" / "util" / "request_logger.py",
            (API_REQUEST_LOG_GUARD,),
        ),
    )

    changed = [
        path.relative_to(comfyui_root).as_posix()
        for path, replacements in targets
        if patch_file(path, replacements)
    ]
    if not changed:
        return "already patched"
    return "patched " + ", ".join(changed)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comfyui_root", type=Path)
    args = parser.parse_args()

    result = patch_comfyui_privacy_logging(args.comfyui_root)
    print(f"ComfyUI privacy logging: {result}")


if __name__ == "__main__":
    main()
