"""Test di `render_config.py` (T1.2 dello storico di sviluppo).

Esegue lo script come sottoprocesso, esattamente come fa
`init-hermes.sh`, e verifica il config.yaml risultante. Non richiede
Docker né un venv di hermes-agent: per il test contro il resolver reale
vedi tests/test_toolsets_live.py.

Esecuzione: uv run --with pyyaml --with pytest pytest tests/test_render_config.py
"""
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_CONFIG = (
    REPO_ROOT
    / "hermes_agent"
    / "rootfs"
    / "usr"
    / "local"
    / "lib"
    / "hermes-ha"
    / "render_config.py"
)

UNSAFE = {"terminal", "code_execution", "file"}
DEFAULT_CLI = ["web", "memory", "session_search", "todo", "clarify", "skills", "cronjob"]


def run_render_config(tmp_path, ha_access, allow_shell, initial_cfg=None):
    config_path = tmp_path / "config.yaml"
    if initial_cfg is not None:
        config_path.write_text(yaml.safe_dump(initial_cfg, sort_keys=False))
    result = subprocess.run(
        [sys.executable, str(RENDER_CONFIG), str(config_path), ha_access, str(allow_shell)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    with open(config_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh), config_path


def test_missing_config_uses_safe_defaults(tmp_path):
    cfg, _ = run_render_config(tmp_path, "mcp", "false")
    cli = cfg["platform_toolsets"]["cli"]
    assert cli == DEFAULT_CLI
    assert not (set(cli) & UNSAFE)
    assert set(cfg["agent"]["disabled_toolsets"]) == UNSAFE
    assert cfg["security"]["allow_lazy_installs"] is False


def test_composite_hermes_cli_toolset_is_normalized_to_safe_defaults(tmp_path):
    initial = {"platform_toolsets": {"cli": ["hermes-cli", "terminal"]}}
    cfg, _ = run_render_config(tmp_path, "mcp", "false", initial_cfg=initial)
    cli = cfg["platform_toolsets"]["cli"]
    assert cli == DEFAULT_CLI
    assert not (set(cli) & UNSAFE)


def test_allow_shell_true_enables_unsafe_toolsets(tmp_path):
    cfg, _ = run_render_config(tmp_path, "mcp", "true")
    cli = cfg["platform_toolsets"]["cli"]
    assert UNSAFE <= set(cli)
    assert not (UNSAFE & set(cfg["agent"]["disabled_toolsets"]))


def test_ha_access_full_enables_homeassistant_toolset_and_mcp_server(tmp_path):
    cfg, _ = run_render_config(tmp_path, "full", "false")
    assert "homeassistant" in cfg["platform_toolsets"]["cli"]
    assert "homeassistant" in cfg["mcp_servers"]


def test_ha_access_none_removes_mcp_server_but_keeps_other_servers(tmp_path):
    initial = {
        "mcp_servers": {
            "homeassistant": {"url": "http://old"},
            "other": {"url": "https://example.com"},
        }
    }
    cfg, _ = run_render_config(tmp_path, "none", "false", initial_cfg=initial)
    assert "homeassistant" not in cfg.get("mcp_servers", {})
    assert cfg["mcp_servers"]["other"] == {"url": "https://example.com"}


def test_unmanaged_keys_are_preserved(tmp_path):
    initial = {
        "model": "gpt-4",
        "providers": {"openai": {"api_key_env": "OPENAI_API_KEY"}},
    }
    cfg, _ = run_render_config(tmp_path, "mcp", "false", initial_cfg=initial)
    assert cfg["model"] == "gpt-4"
    assert cfg["providers"] == {"openai": {"api_key_env": "OPENAI_API_KEY"}}


def test_mcp_header_uses_placeholder_and_never_a_real_token(tmp_path):
    cfg, config_path = run_render_config(tmp_path, "full", "false")
    header = cfg["mcp_servers"]["homeassistant"]["headers"]["Authorization"]
    assert header == "Bearer ${HERMES_HA_TOKEN}"
    raw = config_path.read_text(encoding="utf-8")
    assert "SUPERVISOR_TOKEN" not in raw
