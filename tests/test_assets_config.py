from pathlib import Path


START_SCRIPT = (
    Path(__file__).parents[1]
    / "comfyui_aws_stack"
    / "docker"
    / "scripts"
    / "start_comfyui.sh"
)


def test_comfyui_assets_browser_is_enabled():
    start_script = START_SCRIPT.read_text(encoding="utf-8")

    assert "--enable-assets" in start_script
    assert '--output-directory "${COMFYUI_ROOT}/output/"' in start_script


def test_comfyui_loads_generated_nvme_model_paths():
    start_script = START_SCRIPT.read_text(encoding="utf-8")

    assert "sync_model_cache.py" in start_script
    assert "--extra-model-paths-config" in start_script
    assert "COMFYUI_MODEL_CACHE_ENABLED" in start_script
