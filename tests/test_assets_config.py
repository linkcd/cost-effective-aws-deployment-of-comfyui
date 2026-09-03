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
