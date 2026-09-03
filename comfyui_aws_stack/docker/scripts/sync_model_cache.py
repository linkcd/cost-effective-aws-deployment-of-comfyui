#!/usr/bin/env python3
"""Prepare the disposable NVMe model cache while preserving an EBS fallback."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional, Union


MODEL_CATEGORIES = (
    "diffusion_models",
    "text_encoders",
    "vae",
    "loras",
)
CACHE_MARKER = ".comfyui-instance-store"
CACHE_STATE = ".comfyui-model-cache-state.json"
CACHE_LOCK = ".comfyui-model-cache.lock"


def log(message: str) -> None:
    print(f"[model-cache] {message}", flush=True)


def parse_bool(value: Union[str, bool, None]) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_model_path(value: str) -> Path:
    posix_path = PurePosixPath(value)
    if posix_path.is_absolute():
        raise ValueError(f"model path must be relative: {value}")
    if not posix_path.parts or any(part in {"", ".", ".."} for part in posix_path.parts):
        raise ValueError(f"unsafe model path: {value}")
    if posix_path.parts[0] not in MODEL_CATEGORIES:
        raise ValueError(
            f"unsupported model category {posix_path.parts[0]!r}: {value}"
        )
    return Path(*posix_path.parts)


def load_manifest(manifest_path: Path) -> tuple[Path, ...]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError("model-cache manifest version must be 1")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError("model-cache manifest models must be a list")

    result: list[Path] = []
    seen: set[Path] = set()
    for value in models:
        if not isinstance(value, str):
            raise ValueError("model-cache manifest entries must be strings")
        model_path = validate_model_path(value)
        if model_path not in seen:
            result.append(model_path)
            seen.add(model_path)
    return tuple(result)


def archive_path(history_root: Path, relative_path: Path) -> Path:
    generation = f"{time.time_ns()}"
    return history_root / generation / relative_path


def migrate_models_to_store(
    default_models_root: Path,
    store_root: Path,
    model_paths: Iterable[Path],
) -> dict[str, int]:
    """Move cache-managed files into a persistent, non-indexed EBS store."""

    stats = {"imported": 0, "replaced": 0, "available": 0, "missing": 0}
    history_root = store_root / ".history"

    for relative_path in model_paths:
        default_path = default_models_root / relative_path
        store_path = store_root / relative_path

        if default_path.is_symlink():
            log(f"ignoring unexpected symlink at {default_path}")
        elif default_path.exists():
            if not default_path.is_file():
                log(f"ignoring non-file model path {default_path}")
            else:
                store_path.parent.mkdir(parents=True, exist_ok=True)
                if store_path.exists():
                    archived_path = archive_path(history_root, relative_path)
                    archived_path.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(store_path, archived_path)
                    stats["replaced"] += 1
                    log(
                        f"archived prior EBS source {relative_path} "
                        f"at {archived_path}"
                    )
                os.replace(default_path, store_path)
                stats["imported"] += 1
                log(f"imported EBS model source {relative_path}")

        if store_path.is_file():
            stats["available"] += 1
        else:
            stats["missing"] += 1

    return stats


def same_file_metadata(source: Path, destination: Path) -> bool:
    if not destination.is_file():
        return False
    source_stat = source.stat()
    destination_stat = destination.stat()
    return (
        source_stat.st_size == destination_stat.st_size
        and source_stat.st_mtime_ns == destination_stat.st_mtime_ns
    )


def copy_file_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_name(
        f".{destination.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    try:
        shutil.copy2(source, temporary_path)
        if source.stat().st_size != temporary_path.stat().st_size:
            raise OSError(f"incomplete cache copy for {source}")
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def sync_cache(
    store_root: Path,
    cache_root: Path,
    model_paths: Iterable[Path],
) -> dict[str, int]:
    """Refresh cache-managed files under an exclusive host-level lock."""

    stats = {"copied": 0, "hits": 0, "removed": 0}
    cache_models_root = cache_root / "models"
    cache_models_root.mkdir(parents=True, exist_ok=True)

    lock_path = cache_root / CACHE_LOCK
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        state_entries: dict[str, dict[str, int]] = {}

        for relative_path in model_paths:
            source_path = store_root / relative_path
            cache_path = cache_models_root / relative_path

            for temporary_path in cache_path.parent.glob(
                f".{cache_path.name}.tmp-*"
            ):
                temporary_path.unlink(missing_ok=True)

            if not source_path.is_file():
                if cache_path.exists():
                    cache_path.unlink()
                    stats["removed"] += 1
                    log(f"removed stale cached model {relative_path}")
                continue

            if same_file_metadata(source_path, cache_path):
                stats["hits"] += 1
            else:
                log(f"copying {relative_path} to NVMe")
                copy_file_atomic(source_path, cache_path)
                stats["copied"] += 1

            cache_stat = cache_path.stat()
            state_entries[relative_path.as_posix()] = {
                "size": cache_stat.st_size,
                "mtime_ns": cache_stat.st_mtime_ns,
            }

        write_json_atomic(
            cache_root / CACHE_STATE,
            {
                "version": 1,
                "updated_at_unix_ns": time.time_ns(),
                "models": state_entries,
            },
        )

    return stats


def render_extra_model_paths(
    store_root: Path,
    cache_models_root: Optional[Path],
) -> str:
    lines: list[str] = []

    def add_section(name: str, base_path: Path) -> None:
        lines.extend(
            [
                f"{name}:",
                f"    base_path: {base_path}",
                "    diffusion_models: diffusion_models/",
                "    text_encoders: text_encoders/",
                "    vae: vae/",
                "    loras: loras/",
            ]
        )

    if cache_models_root is not None:
        add_section("h3_nvme_cache", cache_models_root)
    add_section("h3_ebs_fallback", store_root)
    return "\n".join(lines) + "\n"


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary_path.write_text(content, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def prepare_model_cache(
    *,
    comfyui_root: Path,
    cache_root: Path,
    manifest_path: Path,
    config_output: Path,
    enabled: bool,
) -> dict:
    model_paths = load_manifest(manifest_path)
    default_models_root = comfyui_root / "models"
    store_root = comfyui_root / "model_store" / "h3"
    store_root.mkdir(parents=True, exist_ok=True)

    migration_stats = {
        "imported": 0,
        "replaced": 0,
        "available": 0,
        "missing": len(model_paths),
    }
    if enabled:
        migration_stats = migrate_models_to_store(
            default_models_root,
            store_root,
            model_paths,
        )

    cache_ready = False
    cache_stats = {"copied": 0, "hits": 0, "removed": 0}
    if enabled and (cache_root / CACHE_MARKER).is_file():
        try:
            cache_stats = sync_cache(store_root, cache_root, model_paths)
            cache_ready = True
        except Exception as error:  # noqa: BLE001 - availability wins over cache
            log(f"WARNING: NVMe cache refresh failed; using EBS: {error}")
    elif enabled:
        log("NVMe instance-store marker not found; using EBS")

    cache_models_root = cache_root / "models" if cache_ready else None
    write_text_atomic(
        config_output,
        render_extra_model_paths(store_root, cache_models_root),
    )

    result = {
        "enabled": enabled,
        "cache_ready": cache_ready,
        "migration": migration_stats,
        "cache": cache_stats,
    }
    log(json.dumps(result, sort_keys=True))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--comfyui-root",
        type=Path,
        default=Path(os.environ.get("COMFYUI_ROOT", "/home/user/opt/ComfyUI")),
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(
            os.environ.get("COMFYUI_MODEL_CACHE_ROOT", "/mnt/comfy-cache")
        ),
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config-output", type=Path, required=True)
    parser.add_argument(
        "--enabled",
        default=os.environ.get("COMFYUI_MODEL_CACHE_ENABLED", "1"),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        prepare_model_cache(
            comfyui_root=args.comfyui_root,
            cache_root=args.cache_root,
            manifest_path=args.manifest,
            config_output=args.config_output,
            enabled=parse_bool(args.enabled),
        )
    except Exception as error:  # noqa: BLE001 - keep ComfyUI available
        log(f"WARNING: cache preparation failed; continuing without cache: {error}")
        try:
            store_root = args.comfyui_root / "model_store" / "h3"
            write_text_atomic(
                args.config_output,
                render_extra_model_paths(store_root, None),
            )
        except Exception as fallback_error:  # noqa: BLE001 - diagnostics only
            log(
                "WARNING: unable to expose the EBS cache fallback: "
                f"{fallback_error}"
            )
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
