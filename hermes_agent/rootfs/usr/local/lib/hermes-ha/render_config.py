"""Applica i vincoli dell'App al config.yaml di Hermes.

Uso: render_config.py <config.yaml> <ha_access: mcp|full|none> <allow_shell: true|false>

Eseguito a ogni avvio. Tocca solo le chiavi elencate qui sotto; tutto il resto
(modello, provider, preferenze salvate da Web UI o CLI) resta com'è.

Chiavi gestite:
  platform_toolsets.cli   toolset usati da Web UI e CLI
  agent.disabled_toolsets secondo livello di blocco per gli stessi toolset
  security.allow_lazy_installs  sempre false (niente pip install a runtime)
  gateway.multiplex_profiles    sempre true (un gateway serve tutti i profili)
  update.installs.<id>.channel  sempre stable (mai il branch main)
  mcp_servers.homeassistant     presente se ha_access è mcp o full
"""

import hashlib
import os
import sys

import yaml

# Toolset che danno all'agente accesso al container: esecuzione di comandi,
# esecuzione di codice Python, lettura/scrittura di file. Con questi attivi
# l'agente può leggere /data/hermes/.env e quindi il token di HA.
UNSAFE = ["terminal", "code_execution", "file"]

# Default quando la lista non esiste ancora. Nessun toolset "composito"
# (es. hermes-cli): con una lista esplicita di toolset configurabili, Hermes
# abilita esattamente quelli elencati (hermes_cli/tools_config.py,
# _get_platform_tools, ramo has_explicit_config).
DEFAULT_CLI = ["web", "memory", "session_search", "todo", "clarify", "skills", "cronjob"]

HA_MCP_URL = "http://supervisor/core/api/mcp"

# Radice dell'installazione di hermes-agent nell'immagine: indicizza il record
# del canale di aggiornamento (sha256 del path, primi 16 caratteri).
INSTALL_ROOT = "/opt/hermes-agent"


def main() -> None:
    path, ha_access, allow_shell_raw = sys.argv[1:4]
    allow_shell = allow_shell_raw.lower() == "true"

    cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}

    # ── toolset per Web UI e CLI (piattaforma "cli") ────────────────────────
    platform_toolsets = cfg.get("platform_toolsets") or {}
    cli = platform_toolsets.get("cli")
    if not isinstance(cli, list):
        cli = list(DEFAULT_CLI) + (UNSAFE if allow_shell else [])
    cli = [str(t) for t in cli]

    if not allow_shell:
        # I compositi "hermes-*" si espandono di nuovo in tutti i tool core,
        # terminal compreso: li sostituiamo con i default sicuri invece di
        # toglierli e basta (altrimenti resterebbe una lista quasi vuota).
        had_composite = any(t.startswith("hermes") for t in cli)
        cli = [t for t in cli if t not in UNSAFE and not t.startswith("hermes")]
        if had_composite:
            cli = list(dict.fromkeys(DEFAULT_CLI + cli))

    # Il toolset nativo "homeassistant" usa HASS_TOKEN (API REST completa):
    # lo abilitiamo solo con ha_access=full.
    if ha_access == "full":
        if "homeassistant" not in cli:
            cli.append("homeassistant")
    else:
        cli = [t for t in cli if t != "homeassistant"]

    platform_toolsets["cli"] = cli
    cfg["platform_toolsets"] = platform_toolsets

    agent = cfg.get("agent") or {}
    disabled = set(agent.get("disabled_toolsets") or [])
    if allow_shell:
        disabled -= set(UNSAFE)
    else:
        disabled |= set(UNSAFE)
    agent["disabled_toolsets"] = sorted(disabled)
    cfg["agent"] = agent

    # ── niente installazioni di pacchetti a runtime ─────────────────────────
    security = cfg.get("security") or {}
    security["allow_lazy_installs"] = False
    cfg["security"] = security

    # ── un solo gateway che serve TUTTI i profili ───────────────────────────
    # Hermes decide da sé se multiplexare i profili, ma il suo controllo
    # preliminare si rifiuta quando gira in un container con s6 e NON trova lo
    # slot dinamico /run/service/gateway-default (che nell'immagine ufficiale
    # viene registrato al boot). Da noi quello slot non esiste di proposito:
    # il gateway è il servizio s6 STATICO `main-hermes` (vedi CLAUDE.md regola
    # #12), scelto per non dover rendere /run/service scrivibile da `hermes`
    # — che sarebbe una scorciatoia verso root. Per Hermes è quindi un falso
    # positivo, e senza questa chiave i profili secondari non vengono serviti:
    # "Your gateway serves only one profile. Not served: ivana, savez"
    # (caso reale sul Pi, 2026-09-28).
    # Un `true` ESPLICITO salta quel controllo (hermes_cli/gateway_multiplex_mode.py,
    # resolve_multiplex_mode: `if current: return MultiplexDecision(True, "config")`),
    # ed è corretto affermarlo qui perché l'architettura dell'App garantisce
    # esattamente UN gateway: s6 ne supervisiona uno solo e la registrazione
    # dinamica per-profilo non è raggiungibile.
    gateway = cfg.get("gateway") or {}
    gateway["multiplex_profiles"] = True
    cfg["gateway"] = gateway

    # ── canale di aggiornamento: solo release, mai `main` ───────────────────
    # Per un'installazione da SORGENTE (la nostra: git clone, nessuno stamp di
    # pacchetto) il canale predefinito di Hermes è `main`, non `stable`
    # (hermes_cli/update_channel.py, default_channel: "«self» source installs
    # follow main"). Senza questa chiave il pulsante "Update" della dashboard
    # scarica quindi lo sviluppo non rilasciato: successo davvero il
    # 2026-09-29 sul Pi — 2129 commit dopo l'ultimo tag, assistente rotto da un
    # ImportError e la nostra patch a vite.config.ts finita in stash.
    # Il record è per-installazione ed è indicizzato da sha256(path)[:16]
    # (verificato: /opt/hermes-agent -> ffad2f5543956651).
    install_id = hashlib.sha256(INSTALL_ROOT.encode()).hexdigest()[:16]
    update_cfg = cfg.get("update") or {}
    installs = update_cfg.get("installs") or {}
    record = installs.get(install_id) or {}
    record["path"] = INSTALL_ROOT
    record["channel"] = "stable"
    installs[install_id] = record
    update_cfg["installs"] = installs
    cfg["update"] = update_cfg

    # ── MCP Server di Home Assistant ────────────────────────────────────────
    # Il token non viene scritto qui: Hermes interpola ${HERMES_HA_TOKEN}
    # dall'ambiente, che carica da /data/hermes/.env.
    mcp_servers = cfg.get("mcp_servers") or {}
    if ha_access in ("mcp", "full"):
        mcp_servers["homeassistant"] = {
            "url": HA_MCP_URL,
            "headers": {"Authorization": "Bearer ${HERMES_HA_TOKEN}"},
        }
    else:
        mcp_servers.pop("homeassistant", None)
    if mcp_servers:
        cfg["mcp_servers"] = mcp_servers
    else:
        cfg.pop("mcp_servers", None)

    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)

    print(f"[render_config] toolset cli: {', '.join(cli)}")
    print(f"[render_config] ha_access={ha_access} allow_shell_tools={allow_shell}")


if __name__ == "__main__":
    main()
