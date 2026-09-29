"""Test contro il resolver reale di hermes-agent (T1.3 dello storico di sviluppo).

È il test che conta davvero: verifica che `hermes_cli.tools_config
._get_platform_tools`, la stessa funzione usata dalla piattaforma "cli"
in produzione, non risolva mai i toolset UNSAFE quando allow_shell_tools
è false — indipendentemente da cosa contenga già config.yaml.

Richiede un venv di hermes-agent al commit pinnato nel Dockerfile
(HERMES_AGENT_SHA in hermes_agent/Dockerfile). Per prepararlo:

    git clone --depth 1 --branch v2026.8.13 \\
        https://github.com/NousResearch/hermes-agent.git /tmp/hermes-agent-src
    cd /tmp/hermes-agent-src
    test "$(git rev-parse HEAD)" = f80f453ae0679347e38abc917c7f94f717bf96c5
    uv sync --frozen --python 3.12 --extra all --extra anthropic
    export HERMES_AGENT_VENV=/tmp/hermes-agent-src/.venv

Senza HERMES_AGENT_VENV il modulo viene saltato: le verifiche statiche in
test_render_config.py restano comunque attive e non richiedono rete.

Esecuzione: uv run --with pyyaml --with pytest pytest tests/test_toolsets_live.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
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

VENV = os.environ.get("HERMES_AGENT_VENV")
pytestmark = pytest.mark.skipif(
    not VENV,
    reason="HERMES_AGENT_VENV non impostata: serve un venv di hermes-agent al commit pinnato (vedi docstring)",
)


def _render(tmp_path, ha_access, allow_shell, initial_cfg=None):
    config_path = tmp_path / "config.yaml"
    if initial_cfg is not None:
        config_path.write_text(yaml.safe_dump(initial_cfg, sort_keys=False))
    subprocess.run(
        [sys.executable, str(RENDER_CONFIG), str(config_path), ha_access, str(allow_shell)],
        check=True,
        capture_output=True,
        text=True,
    )
    return config_path


def _resolve_platform_tools(config_path):
    venv_python = Path(VENV) / "bin" / "python"
    code = (
        "import json, yaml\n"
        "from hermes_cli.tools_config import _get_platform_tools\n"
        f"cfg = yaml.safe_load(open({str(config_path)!r}, encoding='utf-8'))\n"
        "print(json.dumps(sorted(_get_platform_tools(cfg, 'cli'))))\n"
    )
    result = subprocess.run(
        [str(venv_python), "-c", code], capture_output=True, text=True, check=True
    )
    return set(json.loads(result.stdout))


@pytest.mark.parametrize(
    "ha_access,allow_shell,initial_cfg",
    [
        ("mcp", "false", None),
        ("full", "false", None),
        ("none", "false", None),
        ("mcp", "false", {"platform_toolsets": {"cli": ["hermes-cli", "terminal"]}}),
    ],
)
def test_no_unsafe_toolset_ever_resolved_when_shell_disabled(
    tmp_path, ha_access, allow_shell, initial_cfg
):
    config_path = _render(tmp_path, ha_access, allow_shell, initial_cfg)
    resolved = _resolve_platform_tools(config_path)
    assert not (resolved & UNSAFE), f"toolset UNSAFE risolti: {resolved & UNSAFE}"


def test_allow_shell_true_does_resolve_unsafe_toolsets(tmp_path):
    # Verifica anche il caso opposto: se l'utente attiva esplicitamente
    # allow_shell_tools, gli UNSAFE devono comparire — altrimenti l'opzione
    # non farebbe nulla e l'utente crederebbe (a torto) di averla attivata.
    config_path = _render(tmp_path, "mcp", "true")
    resolved = _resolve_platform_tools(config_path)
    assert UNSAFE <= resolved
