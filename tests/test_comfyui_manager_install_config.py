import configparser
import importlib.util
from pathlib import Path


CONFIG_SCRIPT = (
    Path(__file__).parents[1]
    / "comfyui_aws_stack"
    / "docker"
    / "scripts"
    / "configure_comfyui_manager.py"
)

SPEC = importlib.util.spec_from_file_location(
    "configure_comfyui_manager",
    CONFIG_SCRIPT,
)
assert SPEC is not None
assert SPEC.loader is not None
CONFIG_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG_MODULE)


def read_config(path: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read(path)
    return config


def test_creates_manager_config_with_install_flags(tmp_path):
    config_path = tmp_path / "user" / "__manager" / "config.ini"

    assert CONFIG_MODULE.configure_manager(config_path) is True

    config = read_config(config_path)
    assert config["default"]["allow_git_url_install"] == "true"
    assert config["default"]["allow_pip_install"] == "true"
    assert config["default"]["file_logging"] == "false"


def test_preserves_existing_manager_settings_and_sections(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """\
[default]
security_level = normal
network_mode = public
allow_git_url_install = False
allow_pip_install = False
file_logging = True

[custom]
keep_me = yes
""",
        encoding="utf-8",
    )

    assert CONFIG_MODULE.configure_manager(config_path) is True

    config = read_config(config_path)
    assert config["default"]["security_level"] == "normal"
    assert config["default"]["network_mode"] == "public"
    assert config["default"]["allow_git_url_install"] == "true"
    assert config["default"]["allow_pip_install"] == "true"
    assert config["default"]["file_logging"] == "false"
    assert config["custom"]["keep_me"] == "yes"


def test_configuration_is_idempotent(tmp_path):
    config_path = tmp_path / "config.ini"

    assert CONFIG_MODULE.configure_manager(config_path) is True
    first_content = config_path.read_text(encoding="utf-8")

    assert CONFIG_MODULE.configure_manager(config_path) is False
    assert config_path.read_text(encoding="utf-8") == first_content
