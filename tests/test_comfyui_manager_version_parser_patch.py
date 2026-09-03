import importlib.util
from pathlib import Path


PATCH_SCRIPT = (
    Path(__file__).parents[1]
    / "comfyui_aws_stack"
    / "docker"
    / "scripts"
    / "patch_comfyui_manager_version_parser.py"
)

SPEC = importlib.util.spec_from_file_location(
    "patch_comfyui_manager_version_parser",
    PATCH_SCRIPT,
)
assert SPEC is not None
assert SPEC.loader is not None
PATCH_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH_MODULE)


def manager_util_source(parser: str) -> str:
    return f"""\
class StrictVersion:
    def __init__(self, version_string):
        self.version_string = version_string
        self.major = 0
        self.minor = 0
        self.patch = 0
        self.pre_release = None
        self.parse_version_string()

{parser}
    def __str__(self):
        version = f"{{self.major}}.{{self.minor}}.{{self.patch}}"
        if self.pre_release:
            version += f"-{{self.pre_release}}"
        return version
"""


def load_strict_version(path: Path):
    spec = importlib.util.spec_from_file_location("patched_manager_util", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.StrictVersion


def test_patches_semver_prerelease_parser(tmp_path):
    manager_util = tmp_path / "manager_util.py"
    manager_util.write_text(
        manager_util_source(PATCH_MODULE.OLD_PARSER),
        encoding="utf-8",
    )

    assert PATCH_MODULE.patch_manager_version_parser(manager_util) == "patched"

    strict_version = load_strict_version(manager_util)
    assert str(strict_version("0.7.0-a2")) == "0.7.0-a2"
    assert str(strict_version("1.2.3-beta.1")) == "1.2.3-beta.1"
    assert str(strict_version("1.2.3.beta1")) == "1.2.3-beta1"


def test_patch_is_idempotent(tmp_path):
    manager_util = tmp_path / "manager_util.py"
    manager_util.write_text(
        manager_util_source(PATCH_MODULE.OLD_PARSER),
        encoding="utf-8",
    )

    assert PATCH_MODULE.patch_manager_version_parser(manager_util) == "patched"
    first_content = manager_util.read_text(encoding="utf-8")

    assert PATCH_MODULE.patch_manager_version_parser(manager_util) == "already fixed"
    assert manager_util.read_text(encoding="utf-8") == first_content


def test_skips_unrecognized_manager_version(tmp_path):
    manager_util = tmp_path / "manager_util.py"
    manager_util.write_text("# future implementation\n", encoding="utf-8")

    assert (
        PATCH_MODULE.patch_manager_version_parser(manager_util)
        == "parser layout not recognized; skipped"
    )
    assert manager_util.read_text(encoding="utf-8") == "# future implementation\n"
