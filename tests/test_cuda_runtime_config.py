import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
DOCKERFILE = ROOT / "comfyui_aws_stack" / "docker" / "Dockerfile"
REPORT_SCRIPT = (
    ROOT
    / "comfyui_aws_stack"
    / "docker"
    / "scripts"
    / "report_runtime.py"
)

SPEC = importlib.util.spec_from_file_location("report_runtime", REPORT_SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
REPORT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT_MODULE)


def test_dockerfile_pins_cuda_13_runtime_and_live_revisions():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "nvcr.io/nvidia/cuda:13.0.3-runtime-ubuntu22.04" in dockerfile
    assert "PYTORCH_VERSION=2.14.0" in dockerfile
    assert "TORCHVISION_VERSION=0.29.0" in dockerfile
    assert "TORCHAUDIO_VERSION=2.11.0" in dockerfile
    assert "COMFY_KITCHEN_VERSION=0.2.31" in dockerfile
    assert "https://download.pytorch.org/whl/cu130" in dockerfile
    assert "3216c62e9962c3babd28a4dfea6e5aef50b8fe16" in dockerfile
    assert "b75fc664ecab9c4602380d9660833d02f6a63333" in dockerfile
    assert "cu126" not in dockerfile


def test_runtime_report_identifies_cu130(monkeypatch):
    fake_torch = SimpleNamespace(
        __version__="2.14.0+cu130",
        version=SimpleNamespace(cuda="13.0"),
        cuda=SimpleNamespace(is_available=lambda: True),
    )
    fake_packages = {
        "torch": fake_torch,
        "torchvision": SimpleNamespace(__version__="0.29.0+cu130"),
        "torchaudio": SimpleNamespace(__version__="2.11.0+cu130"),
    }
    monkeypatch.setattr(
        REPORT_MODULE.importlib,
        "import_module",
        lambda name: fake_packages[name],
    )
    fake_distribution_versions = {
        "comfy-kitchen": "0.2.31",
        "triton": "3.8.0",
    }
    monkeypatch.setattr(
        REPORT_MODULE.importlib.metadata,
        "version",
        lambda name: fake_distribution_versions[name],
    )

    assert REPORT_MODULE.runtime_summary() == {
        "torch": "2.14.0+cu130",
        "torchvision": "0.29.0+cu130",
        "torchaudio": "2.11.0+cu130",
        "comfy_kitchen": "0.2.31",
        "triton": "3.8.0",
        "torch_cuda": "13.0",
        "cuda_available": True,
    }
