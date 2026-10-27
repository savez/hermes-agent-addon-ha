"""Test di `render_config.py` (T1.2 dello storico di sviluppo).

Esegue lo script come sottoprocesso, esattamente come fa
`init-hermes.sh`, e verifica il config.yaml risultante. Non richiede
Docker né un venv di hermes-agent: per il test contro il resolver reale
vedi tests/test_toolsets_live.py.

Esecuzione: uv run --with pyyaml --with pytest pytest tests/test_render_config.py
"""
import os
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
IMAGE = "image-render"


def _env(tmp_path):
    # Come per il plugin HA, nei test il plugin image-render è una copia
    # finta: HERMES_APP_PLUGINS_DIR sostituisce /opt/hermes-app-plugins.
    base = tmp_path / "image" / "hermes-app-plugins"
    (base / IMAGE).mkdir(parents=True, exist_ok=True)
    (base / IMAGE / "plugin.yaml").write_text(f"name: {IMAGE}\n")
    return {**os.environ, "HERMES_APP_PLUGINS_DIR": str(base)}


def run_render_config(tmp_path, ha_access, allow_shell, initial_cfg=None, plugin_src=None):
    config_path = tmp_path / "config.yaml"
    if initial_cfg is not None:
        config_path.write_text(yaml.safe_dump(initial_cfg, sort_keys=False))
    # Il plugin vero sta in /opt/hermes-ha-plugins nell'immagine: nei test se
    # ne usa sempre una copia finta, così nessun test dipende dal filesystem
    # dell'immagine.
    if plugin_src is None:
        plugin_src = make_plugin_src(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(RENDER_CONFIG),
            str(config_path),
            ha_access,
            str(allow_shell),
            str(plugin_src),
        ],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    with open(config_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh), config_path


def make_plugin_src(tmp_path):
    src = tmp_path / "image" / "hermes-ha-plugins" / "homeassistant"
    src.mkdir(parents=True, exist_ok=True)
    (src / "plugin.yaml").write_text("name: homeassistant\n")
    return src


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


def test_mcp_user_keys_survive_restart(tmp_path):
    # `enabled: false` (o un filtro sui tool) messo dall'utente sulla voce MCP
    # di HA deve sopravvivere al riavvio: l'App impone solo url e token.
    initial = {
        "mcp_servers": {
            "homeassistant": {
                "url": "http://old",
                "enabled": False,
                "tools": {"exclude": ["GetDateTime"]},
                "headers": {"Authorization": "Bearer stale", "X-Extra": "1"},
            }
        }
    }
    cfg, _ = run_render_config(tmp_path, "full", "false", initial_cfg=initial)
    entry = cfg["mcp_servers"]["homeassistant"]
    assert entry["enabled"] is False
    assert entry["tools"] == {"exclude": ["GetDateTime"]}
    assert entry["url"] == "http://supervisor/core/api/mcp"
    assert entry["headers"] == {"Authorization": "Bearer ${HERMES_HA_TOKEN}", "X-Extra": "1"}


def test_full_links_ha_plugin(tmp_path):
    src = make_plugin_src(tmp_path)
    cfg, _ = run_render_config(tmp_path, "full", "false", plugin_src=src)
    link = tmp_path / "plugins" / "homeassistant"
    assert link.is_symlink()
    assert link.resolve() == src.resolve()
    assert "homeassistant" in cfg["plugins"]["enabled"]


def test_mcp_removes_ha_plugin(tmp_path):
    src = make_plugin_src(tmp_path)
    run_render_config(tmp_path, "full", "false", plugin_src=src)
    cfg, _ = run_render_config(tmp_path, "mcp", "false", plugin_src=src)
    link = tmp_path / "plugins" / "homeassistant"
    assert not link.exists() and not link.is_symlink()
    assert "homeassistant" not in cfg["plugins"]["enabled"]


def test_plugins_enabled_preserved(tmp_path):
    src = make_plugin_src(tmp_path)
    initial = {"plugins": {"enabled": ["disk-cleanup"], "disabled": []}}
    cfg, _ = run_render_config(tmp_path, "full", "false", initial_cfg=initial, plugin_src=src)
    assert cfg["plugins"]["enabled"] == ["disk-cleanup", "homeassistant", IMAGE]
    cfg, _ = run_render_config(tmp_path, "mcp", "false", plugin_src=src)
    assert cfg["plugins"]["enabled"] == ["disk-cleanup", IMAGE]
    assert cfg["plugins"]["disabled"] == []


def test_user_plugin_dir_not_removed(tmp_path):
    src = make_plugin_src(tmp_path)
    own = tmp_path / "plugins" / "homeassistant"
    own.mkdir(parents=True)
    (own / "plugin.yaml").write_text("name: homeassistant\n")
    config_path = tmp_path / "config.yaml"
    result = subprocess.run(
        [sys.executable, str(RENDER_CONFIG), str(config_path), "mcp", "false", str(src)],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert (own / "plugin.yaml").is_file()
    assert "non è un link dell'App" in result.stdout


def test_mcp_without_plugins_key_enables_only_image_render(tmp_path):
    cfg, _ = run_render_config(tmp_path, "mcp", "false")
    assert cfg["plugins"] == {"enabled": [IMAGE]}


def test_image_render_linked_with_any_ha_access(tmp_path):
    for ha_access in ("none", "mcp", "full"):
        cfg, _ = run_render_config(tmp_path, ha_access, "false")
        link = tmp_path / "plugins" / IMAGE
        assert link.is_symlink()
        assert link.resolve() == (tmp_path / "image" / "hermes-app-plugins" / IMAGE).resolve()
        assert cfg["plugins"]["enabled"].count(IMAGE) == 1


def test_image_render_disabled_by_user_stays_disabled(tmp_path):
    initial = {"plugins": {"enabled": [IMAGE], "disabled": [IMAGE]}}
    cfg, _ = run_render_config(tmp_path, "mcp", "false", initial_cfg=initial)
    assert IMAGE not in cfg["plugins"]["enabled"]
    assert cfg["plugins"]["disabled"] == [IMAGE]


def test_image_render_user_dir_and_disabled(tmp_path):
    # Cartella dell'utente + plugin disabilitato: non deve far fallire l'avvio.
    own = tmp_path / "plugins" / IMAGE
    own.mkdir(parents=True)
    initial = {"plugins": {"enabled": [], "disabled": [IMAGE]}}
    cfg, _ = run_render_config(tmp_path, "mcp", "false", initial_cfg=initial)
    assert cfg["plugins"] == {"enabled": [], "disabled": [IMAGE]}
    assert not own.is_symlink()


def test_image_render_user_dir_not_replaced(tmp_path):
    own = tmp_path / "plugins" / IMAGE
    own.mkdir(parents=True)
    (own / "plugin.yaml").write_text("name: mine\n")
    cfg, _ = run_render_config(tmp_path, "mcp", "false")
    assert not own.is_symlink() and (own / "plugin.yaml").read_text() == "name: mine\n"
    assert IMAGE not in cfg.get("plugins", {}).get("enabled", [])


def test_full_removes_homeassistant_from_disabled_toolsets(tmp_path):
    # Caso reale del Pi: `homeassistant` in agent.disabled_toolsets. Hermes
    # applica quella lista ai singoli tool, quindi senza toglierlo `full`
    # resterebbe senza nessun tool ha_*.
    initial = {"agent": {"disabled_toolsets": ["file", "homeassistant", "terminal"]}}
    cfg, _ = run_render_config(tmp_path, "full", "false", initial_cfg=initial)
    assert "homeassistant" not in cfg["agent"]["disabled_toolsets"]


def test_full_removes_homeassistant_from_disabled_plugins(tmp_path):
    initial = {"plugins": {"enabled": [], "disabled": ["homeassistant", "other"]}}
    cfg, _ = run_render_config(tmp_path, "full", "false", initial_cfg=initial)
    assert cfg["plugins"]["disabled"] == ["other"]
    assert "homeassistant" in cfg["plugins"]["enabled"]



def run_profile_mode(tmp_path, ha_access, initial_cfg, plugin_src):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(initial_cfg, sort_keys=False))
    result = subprocess.run(
        [sys.executable, str(RENDER_CONFIG), "--profile", str(config_path), ha_access, str(plugin_src)],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    with open(config_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_profile_mode_links_plugin_only(tmp_path):
    # Nei profili si gestisce solo il plugin HA: i loro toolset e le altre
    # chiavi restano come li ha scelti l'utente.
    src = make_plugin_src(tmp_path)
    initial = {
        "platform_toolsets": {"cli": ["web", "code_execution"]},
        "agent": {"disabled_toolsets": ["homeassistant"]},
        "plugins": {"enabled": ["disk-cleanup"]},
    }
    cfg = run_profile_mode(tmp_path, "full", initial, src)
    assert (tmp_path / "plugins" / "homeassistant").is_symlink()
    assert (tmp_path / "plugins" / IMAGE).is_symlink()
    assert cfg["plugins"]["enabled"] == ["disk-cleanup", "homeassistant", IMAGE]
    assert cfg["agent"]["disabled_toolsets"] == []
    assert cfg["platform_toolsets"] == {"cli": ["web", "code_execution"]}
    assert "security" not in cfg and "mcp_servers" not in cfg


def test_profile_mode_mcp_unlinks_plugin(tmp_path):
    src = make_plugin_src(tmp_path)
    run_profile_mode(tmp_path, "full", {"plugins": {"enabled": []}}, src)
    cfg = run_profile_mode(tmp_path, "mcp", {"plugins": {"enabled": ["homeassistant"]}}, src)
    assert not (tmp_path / "plugins" / "homeassistant").is_symlink()
    assert cfg["plugins"]["enabled"] == [IMAGE]
