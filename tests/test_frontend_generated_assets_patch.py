import importlib.util
from pathlib import Path

import pytest


PATCH_SCRIPT = (
    Path(__file__).parents[1]
    / "comfyui_aws_stack"
    / "docker"
    / "scripts"
    / "patch_comfyui_frontend_generated_assets.py"
)
DOCKERFILE = (
    Path(__file__).parents[1]
    / "comfyui_aws_stack"
    / "docker"
    / "Dockerfile"
)

SPEC = importlib.util.spec_from_file_location(
    "patch_comfyui_frontend_generated_assets",
    PATCH_SCRIPT,
)
assert SPEC is not None
assert SPEC.loader is not None
PATCH_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH_MODULE)


OLD_FUNCTION = (
    "function useAssetsApi(e){let t=Rv(),"
    "n=T(()=>e===`input`?t.inputAssets:t.historyAssets),"
    "r=T(()=>e===`input`?t.inputLoading:t.historyLoading),"
    "i=T(()=>e===`input`?t.inputError:t.historyError),"
    "fetchMediaList=async()=>e===`input`?"
    "(await t.updateInputs(),t.inputAssets):"
    "(await t.updateHistory(),t.historyAssets),"
    "refresh=()=>fetchMediaList(),"
    "loadMore=async()=>{e===`output`&&await t.loadMoreHistory()};"
    "return{media:n,loading:r,error:i,fetchMediaList,refresh,loadMore,"
    "hasMore:T(()=>e===`output`&&t.hasMoreHistory),"
    "isLoadingMore:T(()=>e===`output`&&t.isLoadingMore)}}"
)


def write_bundle(assets_dir: Path, function_source: str = OLD_FUNCTION) -> Path:
    assets_dir.mkdir(parents=True)
    bundle = assets_dir / "settingStore-fixture.js"
    bundle.write_text(
        f"const unrelated=t.historyAssets;{function_source}"
        "const trailing=t.historyAssets;",
        encoding="utf-8",
    )
    return bundle


def test_redirects_generated_tab_to_persistent_output_assets(tmp_path):
    assets_dir = tmp_path / "assets"
    bundle = write_bundle(assets_dir)

    result = PATCH_MODULE.patch_frontend_generated_assets(assets_dir)
    patched_source = bundle.read_text(encoding="utf-8")
    function_start, function_end = PATCH_MODULE.find_assets_api_span(
        patched_source
    )
    patched_function = patched_source[function_start:function_end]

    assert result == "settingStore-fixture.js: patched"
    assert ".flatOutputAssets" in patched_function
    assert ".flatOutputLoading" in patched_function
    assert ".flatOutputError" in patched_function
    assert ".updateFlatOutputs()" in patched_function
    assert ".loadMoreFlatOutputs()" in patched_function
    assert ".flatOutputHasMore" in patched_function
    assert ".flatOutputIsLoadingMore" in patched_function
    assert ".historyAssets" not in patched_function
    assert patched_source.count("const unrelated=t.historyAssets;") == 1
    assert patched_source.count("const trailing=t.historyAssets;") == 1


def test_frontend_patch_is_idempotent(tmp_path):
    assets_dir = tmp_path / "assets"
    bundle = write_bundle(assets_dir)

    assert (
        PATCH_MODULE.patch_frontend_generated_assets(assets_dir)
        == "settingStore-fixture.js: patched"
    )
    first_content = bundle.read_text(encoding="utf-8")

    assert (
        PATCH_MODULE.patch_frontend_generated_assets(assets_dir)
        == "settingStore-fixture.js: already fixed"
    )
    assert bundle.read_text(encoding="utf-8") == first_content


def test_frontend_patch_rejects_an_unknown_layout(tmp_path):
    assets_dir = tmp_path / "assets"
    unknown_function = OLD_FUNCTION.replace(
        ".historyError",
        ".futureHistoryError",
        1,
    )
    bundle = write_bundle(assets_dir, unknown_function)
    original_source = bundle.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="layout not recognized"):
        PATCH_MODULE.patch_frontend_generated_assets(assets_dir)

    assert bundle.read_text(encoding="utf-8") == original_source


def test_frontend_patch_requires_one_bundle(tmp_path):
    assets_dir = tmp_path / "assets"
    write_bundle(assets_dir)
    (assets_dir / "settingStore-second.js").write_text(
        OLD_FUNCTION,
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="found 2"):
        PATCH_MODULE.patch_frontend_generated_assets(assets_dir)


def test_docker_build_applies_frontend_patch():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert (
        "COPY --chown=user:user "
        "scripts/patch_comfyui_frontend_generated_assets.py "
        "/home/user/bin/patch_comfyui_frontend_generated_assets.py"
        in dockerfile
    )
    assert (
        "RUN python "
        "/home/user/bin/patch_comfyui_frontend_generated_assets.py"
        in dockerfile
    )
