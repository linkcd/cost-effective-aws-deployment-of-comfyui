#!/usr/bin/env python3
"""Make the frontend's Generated tab read persistent output assets."""

from __future__ import annotations

import argparse
import importlib.util
import os
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile


FUNCTION_MARKER = "function useAssetsApi("

PROPERTY_REPLACEMENTS = {
    ".historyAssets": (".flatOutputAssets", 2),
    ".historyLoading": (".flatOutputLoading", 1),
    ".historyError": (".flatOutputError", 1),
    ".updateHistory()": (".updateFlatOutputs()", 1),
    ".loadMoreHistory()": (".loadMoreFlatOutputs()", 1),
    ".hasMoreHistory": (".flatOutputHasMore", 1),
    ".isLoadingMore": (".flatOutputIsLoadingMore", 1),
}


def discover_frontend_assets_dir() -> Path:
    """Return the installed comfyui_frontend_package static assets directory."""
    package_spec = importlib.util.find_spec("comfyui_frontend_package")
    if package_spec is None:
        raise RuntimeError("comfyui_frontend_package is not installed")

    if package_spec.submodule_search_locations:
        package_root = Path(next(iter(package_spec.submodule_search_locations)))
    elif package_spec.origin:
        package_root = Path(package_spec.origin).parent
    else:
        raise RuntimeError("cannot locate comfyui_frontend_package")

    return package_root / "static" / "assets"


def find_function_end(source: str, opening_brace: int) -> int:
    """Find the closing brace for a JavaScript function."""
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening_brace

    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""

        if line_comment:
            if character == "\n":
                line_comment = False
            index += 1
            continue

        if block_comment:
            if character == "*" and following == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue

        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue

        if character in {'"', "'", "`"}:
            quote = character
        elif character == "/" and following == "/":
            line_comment = True
            index += 2
            continue
        elif character == "/" and following == "*":
            block_comment = True
            index += 2
            continue
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index + 1

        index += 1

    raise RuntimeError("unterminated useAssetsApi function")


def find_assets_api_span(source: str) -> tuple[int, int]:
    """Return the byte span of the one expected useAssetsApi function."""
    marker_count = source.count(FUNCTION_MARKER)
    if marker_count != 1:
        raise RuntimeError(
            f"expected exactly one {FUNCTION_MARKER!r}, found {marker_count}"
        )

    function_start = source.index(FUNCTION_MARKER)
    opening_brace = source.find("{", function_start)
    if opening_brace == -1:
        raise RuntimeError("useAssetsApi opening brace not found")

    return function_start, find_function_end(source, opening_brace)


def patch_frontend_generated_assets(assets_dir: Path) -> str:
    """Patch the installed frontend bundle and return the operation result."""
    bundles = sorted(assets_dir.glob("settingStore-*.js"))
    matching_bundles: list[tuple[Path, str]] = []
    for bundle_path in bundles:
        source = bundle_path.read_text(encoding="utf-8")
        if FUNCTION_MARKER in source:
            matching_bundles.append((bundle_path, source))

    if len(matching_bundles) != 1:
        raise RuntimeError(
            "expected exactly one settingStore-*.js bundle containing "
            f"{FUNCTION_MARKER!r}, found {len(matching_bundles)} "
            f"among {len(bundles)} bundles"
        )

    bundle_path, source = matching_bundles[0]
    function_start, function_end = find_assets_api_span(source)
    function_source = source[function_start:function_end]

    old_counts = {
        old: function_source.count(old)
        for old in PROPERTY_REPLACEMENTS
    }
    new_counts = {
        new: function_source.count(new)
        for new, _ in PROPERTY_REPLACEMENTS.values()
    }

    expected_old = {
        old: expected
        for old, (_, expected) in PROPERTY_REPLACEMENTS.items()
    }
    expected_new = {
        new: expected
        for new, expected in PROPERTY_REPLACEMENTS.values()
    }

    if old_counts == {old: 0 for old in expected_old} and new_counts == expected_new:
        return f"{bundle_path.name}: already fixed"

    if old_counts != expected_old or new_counts != {
        new: 0 for new in expected_new
    }:
        raise RuntimeError(
            "useAssetsApi layout not recognized; "
            f"old counts={old_counts}, new counts={new_counts}"
        )

    patched_function = function_source
    for old, (new, _) in PROPERTY_REPLACEMENTS.items():
        patched_function = patched_function.replace(old, new)

    patched_source = (
        source[:function_start]
        + patched_function
        + source[function_end:]
    )
    original_mode = stat.S_IMODE(bundle_path.stat().st_mode)

    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=bundle_path.parent,
        prefix=f".{bundle_path.name}.",
        delete=False,
    ) as temp_file:
        temp_file.write(patched_source)
        temp_path = Path(temp_file.name)

    os.chmod(temp_path, original_mode)
    os.replace(temp_path, bundle_path)
    return f"{bundle_path.name}: patched"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "assets_dir",
        nargs="?",
        type=Path,
        default=None,
        help="Override comfyui_frontend_package/static/assets",
    )
    args = parser.parse_args()

    assets_dir = args.assets_dir or discover_frontend_assets_dir()
    result = patch_frontend_generated_assets(assets_dir)
    print(f"ComfyUI Generated assets frontend: {result}")


if __name__ == "__main__":
    main()
