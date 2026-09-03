from pathlib import Path


DOCKERFILE = (
    Path(__file__).parents[1]
    / "comfyui_aws_stack"
    / "docker"
    / "Dockerfile"
)


def test_videohelpersuite_uses_system_ffmpeg():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "ffmpeg libsm6" in dockerfile
    assert "VHS_FORCE_FFMPEG_PATH=/usr/bin/ffmpeg" in dockerfile
