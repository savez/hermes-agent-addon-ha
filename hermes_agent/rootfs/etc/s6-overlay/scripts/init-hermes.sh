#!/command/with-contenv bashio
# shellcheck shell=bash
# =============================================================================
# Oneshot eseguito a ogni avvio, prima di dashboard, nginx e sshd.
# Rende lo stato in /data coerente con le opzioni dell'App.
# =============================================================================
set -e

readonly HERMES_DIR=/data/hermes
readonly ENV_FILE="${HERMES_DIR}/.env"
readonly CONFIG_FILE="${HERMES_DIR}/config.yaml"
readonly PY=/opt/hermes-agent/.venv/bin/python

# ─── Validazione opzioni ────────────────────────────────────────────────────
HA_ACCESS="$(bashio::config 'ha_access')"
ALLOW_SHELL="$(bashio::config 'allow_shell_tools')"

# ─── Directory persistenti ──────────────────────────────────────────────────
mkdir -p "${HERMES_DIR}/home" "${HERMES_DIR}/workspace"

# ─── .env: solo le chiavi gestite dall'App vengono riscritte ────────────────
# Le chiavi aggiunte da `hermes setup` o dalla dashboard (API key dei
# provider) restano intatte tra un riavvio e l'altro.
#
# Il token del Supervisor CAMBIA a ogni avvio del container, quindi va
# riscritto ovunque serva — compreso ogni profilo secondario creato con
# `hermes profile create` (2026-09-28, T8). Quei profili hanno un proprio
# .env e un proprio config.yaml che punta allo stesso MCP di HA con
# ${HERMES_HA_TOKEN}: senza questa propagazione si porterebbero dietro la
# copia del token presa al momento della clonazione e perderebbero
# l'accesso a Home Assistant al primo riavvio dell'App.
write_ha_env() {
    local env_file="$1"
    ( umask 077 && touch "${env_file}" )
    local key
    for key in HERMES_HA_TOKEN HASS_TOKEN HASS_URL; do
        sed -i "/^${key}=/d" "${env_file}"
    done
    case "${HA_ACCESS}" in
        mcp)
            echo "HERMES_HA_TOKEN=${SUPERVISOR_TOKEN}" >> "${env_file}"
            ;;
        full)
            {
                echo "HERMES_HA_TOKEN=${SUPERVISOR_TOKEN}"
                echo "HASS_TOKEN=${SUPERVISOR_TOKEN}"
                echo "HASS_URL=http://supervisor/core"
            } >> "${env_file}"
            ;;
    esac
}

write_ha_env "${ENV_FILE}"

PROFILE_COUNT=0
for profile_dir in "${HERMES_DIR}"/profiles/*/; do
    [ -d "${profile_dir}" ] || continue
    case "$(basename "${profile_dir}")" in .*) continue ;; esac
    write_ha_env "${profile_dir}.env"
    PROFILE_COUNT=$((PROFILE_COUNT + 1))
done

case "${HA_ACCESS}" in
    mcp)
        bashio::log.info "Accesso a HA: solo MCP Server (entità esposte ad Assist)"
        ;;
    full)
        bashio::log.warning "Accesso a HA: COMPLETO (MCP + API REST di Core, tutte le entità e tutti i servizi)"
        ;;
    none)
        bashio::log.info "Accesso a HA: disattivato"
        ;;
esac

if [ "${PROFILE_COUNT}" -gt 0 ]; then
    bashio::log.info "Token di HA propagato a ${PROFILE_COUNT} profilo/i secondario/i"
fi

# ─── config.yaml di Hermes: applica i vincoli dell'App ──────────────────────
"${PY}" /usr/local/lib/hermes-ha/render_config.py \
    "${CONFIG_FILE}" "${HA_ACCESS}" "${ALLOW_SHELL}"

if bashio::var.true "${ALLOW_SHELL}"; then
    bashio::log.warning "allow_shell_tools=true: l'agente può eseguire comandi e leggere file nel container (token HA compreso)"
fi

# Nessuna password/secret di sessione da generare: la dashboard non ha un
# proprio login (deciso il 2026-09-25 — vedi CLAUDE.md regola #7). L'unica
# barriera per arrivarci resta il login di Home Assistant, dietro cui sta
# il pannello Ingress.

# ─── Proprietà e permessi ───────────────────────────────────────────────────
chown -R hermes:hermes "${HERMES_DIR}"
chmod 700 "${HERMES_DIR}"
chmod 600 "${ENV_FILE}" "${CONFIG_FILE}"

# ─── SSH per la CLI ─────────────────────────────────────────────────────────
mkdir -p /data/ssh /etc/ssh/authorized_keys
chmod 700 /data/ssh
if [ ! -f /data/ssh/ssh_host_ed25519_key ]; then
    bashio::log.info "Genero la host key SSH (una tantum)"
    ssh-keygen -q -t ed25519 -N '' -f /data/ssh/ssh_host_ed25519_key
fi

# authorized_keys è di root e fuori da /data/hermes: l'utente `hermes`
# (e quindi l'agente) non può aggiungersi chiavi da solo.
#
# bashio::config va sempre catturato con $(...) e mai chiamato con una
# redirezione diretta (`bashio::config k > file`): il `read -r -d ''`
# usato internamente per leggere l'heredoc ritorna sempre exit status 1
# (anche a lettura riuscita) e bash non propaga `errexit` dentro le
# command substitution di default, ma lo fa per una chiamata diretta —
# quindi la redirezione diretta abortisce lo script sotto `set -e`.
: > /etc/ssh/authorized_keys/hermes
if bashio::config.has_value 'ssh_authorized_keys'; then
    SSH_KEYS="$(bashio::config 'ssh_authorized_keys')"
    printf '%s\n' "${SSH_KEYS}" > /etc/ssh/authorized_keys/hermes
    bashio::log.info "SSH CLI attivo su porta 2222 ($(grep -c . /etc/ssh/authorized_keys/hermes) chiave/i)"
fi
chown root:root /etc/ssh/authorized_keys/hermes
chmod 644 /etc/ssh/authorized_keys/hermes

# ─── Indirizzo interno per il tunnel SSH ────────────────────────────────────
# L'IP del container sulla rete interna di HA può cambiare tra un riavvio e
# l'altro: lo pubblichiamo in /share così lo script tools/hermes-ssh lo trova.
ADDRESS="$(hostname -i | awk '{print $1}')"
mkdir -p /share/hermes-agent
echo "${ADDRESS}" > /share/hermes-agent/address
bashio::log.info "Indirizzo interno del container: ${ADDRESS}"
