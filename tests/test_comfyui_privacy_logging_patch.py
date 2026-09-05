import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
PATCH_SCRIPT = (
    ROOT
    / "comfyui_aws_stack"
    / "docker"
    / "scripts"
    / "patch_comfyui_privacy_logging.py"
)
DOCKERFILE = ROOT / "comfyui_aws_stack" / "docker" / "Dockerfile"
START_SCRIPT = (
    ROOT
    / "comfyui_aws_stack"
    / "docker"
    / "scripts"
    / "start_comfyui.sh"
)

SPEC = importlib.util.spec_from_file_location(
    "patch_comfyui_privacy_logging",
    PATCH_SCRIPT,
)
assert SPEC is not None
assert SPEC.loader is not None
PATCH_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH_MODULE)


def write_fixture(root: Path) -> None:
    (root / "comfy_api_nodes" / "util").mkdir(parents=True)
    (root / "server.py").write_text(
        "\n".join(
            replacement.old
            for replacement in PATCH_MODULE.SERVER_REPLACEMENTS
        ),
        encoding="utf-8",
    )
    (root / "execution.py").write_text(
        "\n".join(
            replacement.old
            for replacement in PATCH_MODULE.EXECUTION_REPLACEMENTS
            for _ in range(replacement.expected_count)
        ),
        encoding="utf-8",
    )
    (root / "comfy_api_nodes" / "util" / "request_logger.py").write_text(
        PATCH_MODULE.API_REQUEST_LOG_GUARD.old,
        encoding="utf-8",
    )


def test_removes_prompt_values_from_core_and_api_logs(tmp_path):
    write_fixture(tmp_path)

    result = PATCH_MODULE.patch_comfyui_privacy_logging(tmp_path)

    assert result.startswith("patched ")
    server_source = (tmp_path / "server.py").read_text(encoding="utf-8")
    execution_source = (tmp_path / "execution.py").read_text(
        encoding="utf-8"
    )
    request_logger_source = (
        tmp_path / "comfy_api_nodes" / "util" / "request_logger.py"
    ).read_text(encoding="utf-8")

    assert "valid[1]" not in server_source
    assert "traceback.format_exc()" not in server_source
    assert "{reason['details']}" not in execution_source
    assert "Exception during processing !!! {ex}" not in execution_source
    assert "COMFYUI_DISABLE_API_REQUEST_LOGGING" in request_logger_source


def test_privacy_logging_patch_is_idempotent(tmp_path):
    write_fixture(tmp_path)

    assert PATCH_MODULE.patch_comfyui_privacy_logging(tmp_path).startswith(
        "patched "
    )
    first_contents = {
        path.relative_to(tmp_path): path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*.py")
    }

    assert (
        PATCH_MODULE.patch_comfyui_privacy_logging(tmp_path)
        == "already patched"
    )
    assert {
        path.relative_to(tmp_path): path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*.py")
    } == first_contents


def test_privacy_logging_patch_rejects_unknown_layout(tmp_path):
    write_fixture(tmp_path)
    server_path = tmp_path / "server.py"
    server_path.write_text("# future implementation\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="layout not recognized"):
        PATCH_MODULE.patch_comfyui_privacy_logging(tmp_path)


def test_container_applies_privacy_patch_at_build_and_startup():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    start_script = START_SCRIPT.read_text(encoding="utf-8")

    assert (
        "scripts/patch_comfyui_privacy_logging.py "
        "/home/user/bin/patch_comfyui_privacy_logging.py"
        in dockerfile
    )
    assert (
        "RUN python /home/user/bin/patch_comfyui_privacy_logging.py "
        "/home/user/opt/ComfyUI"
        in dockerfile
    )
    assert (
        'patch_comfyui_privacy_logging.py "${COMFYUI_ROOT}"'
        in start_script
    )
