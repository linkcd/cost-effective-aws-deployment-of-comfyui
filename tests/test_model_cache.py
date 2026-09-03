import importlib.util
import json
from pathlib import Path

import pytest


CACHE_SCRIPT = (
    Path(__file__).parents[1]
    / "comfyui_aws_stack"
    / "docker"
    / "scripts"
    / "sync_model_cache.py"
)

SPEC = importlib.util.spec_from_file_location("sync_model_cache", CACHE_SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
CACHE_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHE_MODULE)


MODEL_PATH = Path("diffusion_models/test-model.safetensors")


def write_manifest(path: Path, models=None) -> Path:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "models": models or [MODEL_PATH.as_posix()],
            }
        ),
        encoding="utf-8",
    )
    return path


def prepare_paths(tmp_path: Path):
    comfyui_root = tmp_path / "ComfyUI"
    cache_root = tmp_path / "cache"
    manifest_path = write_manifest(tmp_path / "manifest.json")
    config_output = tmp_path / "extra-model-paths.yaml"
    default_model = comfyui_root / "models" / MODEL_PATH
    default_model.parent.mkdir(parents=True)
    return (
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
        default_model,
    )


def run_prepare(
    comfyui_root: Path,
    cache_root: Path,
    manifest_path: Path,
    config_output: Path,
    enabled: bool = True,
):
    return CACHE_MODULE.prepare_model_cache(
        comfyui_root=comfyui_root,
        cache_root=cache_root,
        manifest_path=manifest_path,
        config_output=config_output,
        enabled=enabled,
    )


def test_imports_ebs_source_and_populates_nvme_cache(tmp_path):
    (
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
        default_model,
    ) = prepare_paths(tmp_path)
    default_model.write_bytes(b"model-v1")
    cache_root.mkdir()
    (cache_root / CACHE_MODULE.CACHE_MARKER).touch()

    result = run_prepare(
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
    )

    store_model = comfyui_root / "model_store" / "h3" / MODEL_PATH
    cached_model = cache_root / "models" / MODEL_PATH
    assert not default_model.exists()
    assert store_model.read_bytes() == b"model-v1"
    assert cached_model.read_bytes() == b"model-v1"
    assert result["migration"]["imported"] == 1
    assert result["cache"]["copied"] == 1
    assert result["cache_ready"] is True

    config = config_output.read_text(encoding="utf-8")
    assert config.index("h3_nvme_cache:") < config.index("h3_ebs_fallback:")
    assert "is_default" not in config
    assert str(cache_root / "models") in config
    assert str(comfyui_root / "model_store" / "h3") in config


def test_cache_hit_does_not_recopy_model(tmp_path):
    (
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
        default_model,
    ) = prepare_paths(tmp_path)
    default_model.write_bytes(b"model-v1")
    cache_root.mkdir()
    (cache_root / CACHE_MODULE.CACHE_MARKER).touch()

    run_prepare(comfyui_root, cache_root, manifest_path, config_output)
    result = run_prepare(comfyui_root, cache_root, manifest_path, config_output)

    assert result["cache"]["copied"] == 0
    assert result["cache"]["hits"] == 1


def test_new_default_model_replaces_store_and_refreshes_cache(tmp_path):
    (
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
        default_model,
    ) = prepare_paths(tmp_path)
    default_model.write_bytes(b"model-v1")
    cache_root.mkdir()
    (cache_root / CACHE_MODULE.CACHE_MARKER).touch()
    run_prepare(comfyui_root, cache_root, manifest_path, config_output)

    default_model.parent.mkdir(parents=True, exist_ok=True)
    default_model.write_bytes(b"model-v2-updated")
    result = run_prepare(
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
    )

    store_model = comfyui_root / "model_store" / "h3" / MODEL_PATH
    cached_model = cache_root / "models" / MODEL_PATH
    history_models = list(
        (comfyui_root / "model_store" / "h3" / ".history").glob(
            f"*/{MODEL_PATH.as_posix()}"
        )
    )
    assert store_model.read_bytes() == b"model-v2-updated"
    assert cached_model.read_bytes() == b"model-v2-updated"
    assert len(history_models) == 1
    assert history_models[0].read_bytes() == b"model-v1"
    assert result["migration"]["replaced"] == 1
    assert result["cache"]["copied"] == 1


def test_missing_instance_store_marker_uses_ebs_fallback(tmp_path):
    (
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
        default_model,
    ) = prepare_paths(tmp_path)
    default_model.write_bytes(b"model-v1")
    cache_root.mkdir()

    result = run_prepare(
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
    )

    assert result["cache_ready"] is False
    assert not (cache_root / "models" / MODEL_PATH).exists()
    config = config_output.read_text(encoding="utf-8")
    assert "h3_nvme_cache:" not in config
    assert "h3_ebs_fallback:" in config


def test_disabled_cache_keeps_new_models_in_default_ebs_path(tmp_path):
    (
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
        default_model,
    ) = prepare_paths(tmp_path)
    default_model.write_bytes(b"model-v1")

    result = run_prepare(
        comfyui_root,
        cache_root,
        manifest_path,
        config_output,
        enabled=False,
    )

    assert default_model.read_bytes() == b"model-v1"
    assert result["enabled"] is False
    assert result["migration"]["imported"] == 0
    assert "h3_ebs_fallback:" in config_output.read_text(encoding="utf-8")


def test_cli_failure_still_exposes_prior_ebs_model_store(tmp_path):
    comfyui_root = tmp_path / "ComfyUI"
    config_output = tmp_path / "extra-model-paths.yaml"
    invalid_manifest = tmp_path / "invalid-manifest.json"
    invalid_manifest.write_text("{not-json", encoding="utf-8")

    exit_code = CACHE_MODULE.main(
        [
            "--comfyui-root",
            str(comfyui_root),
            "--cache-root",
            str(tmp_path / "cache"),
            "--manifest",
            str(invalid_manifest),
            "--config-output",
            str(config_output),
        ]
    )

    assert exit_code == 0
    config = config_output.read_text(encoding="utf-8")
    assert "h3_nvme_cache:" not in config
    assert "h3_ebs_fallback:" in config
    assert str(comfyui_root / "model_store" / "h3") in config


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.safetensors",
        "/absolute/model.safetensors",
        "checkpoints/not-cache-managed.safetensors",
    ],
)
def test_manifest_rejects_unsafe_or_unsupported_paths(tmp_path, unsafe_path):
    manifest = write_manifest(tmp_path / "manifest.json", [unsafe_path])

    with pytest.raises(ValueError):
        CACHE_MODULE.load_manifest(manifest)
