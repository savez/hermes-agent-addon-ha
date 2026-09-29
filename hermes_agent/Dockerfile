# =============================================================================
# Hermes Agent — App per Home Assistant OS
#
# Immagine immutabile per la parte di sistema (nginx, sshd, s6, permessi).
# `hermes-agent` fa eccezione, deciso dall'utente il 2026-09-25 (T6): niente
# più tag+SHA pinnati, il build clona sempre l'ultimo tag disponibile, e
# l'update dalla dashboard nativa di Hermes (`hermes update`) è abilitato —
# il codice dell'agente può quindi cambiare senza rebuild Docker, in
# qualunque momento, da chi ha la password della dashboard. Vedi CLAUDE.md
# regole #1/#4 e DOCS.md → "Modello di sicurezza" per il rischio accettato.
# =============================================================================

ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-debian:bookworm

# uv da immagine ufficiale Astral (niente `curl | sh`).
# Per un pin ancora più stretto aggiungi il digest: ghcr.io/astral-sh/uv:0.11.6@sha256:...
FROM ghcr.io/astral-sh/uv:0.11.6 AS uv

# Node per la build del frontend della dashboard (`web/`, Vite/TypeScript).
# hermes-agent pinna il proprio toolchain a Node 26 ovunque (vedi il
# Dockerfile ufficiale del progetto): stessa scelta qui. Serve anche nello
# stage runtime, non solo in build: `hermes update` (T6) ricostruisce il
# frontend dopo un `git pull`, quindi npm/node restano nell'immagine finale.
FROM node:26-bookworm-slim AS node_source

# ─── Stage 1: builder (Python/venv) ────────────────────────────────────────
FROM ${BUILD_FROM} AS builder

# /bin/sh sull'immagine base Debian è dash, che non supporta
# `set -o pipefail` (serve sotto, nel comando con la pipe per risolvere
# l'ultimo tag). bash è già presente nell'immagine base (lo richiedono gli
# script bashio dello stage runtime).
SHELL ["/bin/bash", "-c"]

# Nessun ARG di versione/SHA per hermes-agent: si clona sempre l'ultimo tag
# disponibile al momento del build (scelta esplicita dell'utente — vedi
# l'intestazione). Il tag risolto viene stampato nel log del build per
# lasciare traccia di cosa è stato installato quando.
ARG HERMES_REPO=https://github.com/NousResearch/hermes-agent.git
# Extra di hermes-agent installati in fase di build. I provider non elencati
# qui non potranno essere installati a runtime (lazy install disattivato).
# OpenAI / OpenRouter / endpoint compatibili OpenAI sono già nel core.
# `messaging` (telegram/discord/slack) NON è dentro `all`: upstream l'ha tolto
# il 2026-05-12 perché conta di installarlo pigramente al primo uso. Noi i lazy
# install li abbiamo disattivati (regola #9), quindi senza questo extra
# l'adattatore Telegram non si crea mai e il gateway logga "Platform 'Telegram'
# requirements not met" / "No adapter available for telegram" — diagnosticato
# via SSH sul Pi reale il 2026-09-26 (T7).
ARG HERMES_EXTRAS="--extra all --extra anthropic --extra messaging"
ARG PYTHON_VERSION=3.12

ENV DEBIAN_FRONTEND=noninteractive \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# Clona l'ultimo tag disponibile (nessuna verifica di un commit atteso: non
# c'è più un valore fisso da controllare, per scelta esplicita dell'utente).
# Storia completa dei commit (niente --depth 1): serve a `hermes update`,
# che dopo il primo avvio fa `git fetch`/`git merge --ff-only` dentro questa
# stessa cartella — un clone superficiale (shallow) renderebbe quei fetch
# più fragili o li farebbe fallire del tutto.
# `--filter=tree:0` scarica comunque TUTTA la storia dei commit (i fetch di
# `hermes update` restano sicuri) ma senza gli alberi/blob delle versioni
# passate dei file, scaricati al bisogno solo per l'ultimo commit (quello di
# cui abbiamo davvero bisogno per buildare); su questo repo taglia `.git` da
# ~1.1GB a ~130MB. Verificato empiricamente: `git fetch` dopo il clone
# funziona ancora normalmente. Diverso da `--depth 1` (che invece taglia la
# storia dei commit e non garantiva la stessa sicurezza per i fetch futuri).
# hadolint valuta `pipefail` come POSIX sh anche con SHELL bash impostato
# sopra (limite noto del suo analizzatore statico, non del Dockerfile: `bash
# -c 'set -o pipefail; ...'` è valido ed è quello davvero eseguito qui).
# hadolint ignore=DL4006,SC3040
RUN set -euxo pipefail; \
    tag="$(git ls-remote --tags --sort=-v:refname "${HERMES_REPO}" \
        | grep -v '\^{}' | head -1 | sed 's#.*refs/tags/##')"; \
    test -n "${tag}"; \
    echo "hermes-agent: ultimo tag risolto al build = ${tag}"; \
    git clone --filter=tree:0 --branch "${tag}" "${HERMES_REPO}" /opt/hermes-agent; \
    git -C /opt/hermes-agent rev-parse HEAD

# Python gestito da uv + venv dell'agent dal lockfile upstream (--frozen:
# nessuna risoluzione di dipendenze, solo le versioni pinnate in uv.lock).
# La dashboard (frontend Vite + backend FastAPI) è dentro hermes-agent
# stesso: nessun secondo progetto da clonare/gestire separatamente.
WORKDIR /opt/hermes-agent
RUN set -eux; \
    uv python install "${PYTHON_VERSION}"; \
    uv sync --frozen --python "${PYTHON_VERSION}" ${HERMES_EXTRAS}; \
    .venv/bin/python -c "import yaml, cryptography, fastapi, uvicorn"; \
    rm -rf /opt/hermes-agent/tests /opt/hermes-agent/website /opt/hermes-agent/docs

# ─── Stage 2: runtime ───────────────────────────────────────────────────────
FROM ${BUILD_FROM}

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HERMES_HOME=/data/hermes \
    HERMES_WRITE_SAFE_ROOT=/data/hermes \
    HERMES_DISABLE_LAZY_INSTALLS=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        # git serve A RUNTIME, non solo in build: `hermes update` (il pulsante
        # della dashboard, regola #1) fa git fetch/pull dentro
        # /opt/hermes-agent, e l'autostash che porta avanti la nostra patch a
        # vite.config.ts è anch'esso git. Senza, l'update è semplicemente
        # impossibile — verificato via SSH sul Pi reale il 2026-09-26 (T7):
        # `git` non esisteva nell'immagine finale.
        git \
        libatomic1 \
        nginx-light \
        openssh-server \
        ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    # Le host key generate dal pacchetto finirebbero nell'immagine: le
    # rigeneriamo al primo avvio in /data/ssh (persistenti).
    && rm -f /etc/ssh/ssh_host_* \
    # Utente non privilegiato che esegue agent, dashboard e sessioni SSH.
    # Password '*' = nessuna password ma account NON bloccato: con
    # UsePAM no, sshd rifiuta anche le chiavi per gli account bloccati ('!').
    && useradd --uid 1000 --no-create-home --home-dir /data/hermes/home \
        --shell /bin/bash hermes \
    && usermod -p '*' hermes

# Node/npm nell'immagine finale (non solo in build): servono a `hermes
# update` per ricostruire il frontend dopo un futuro `git pull` a runtime.
COPY --from=node_source /usr/local/bin/node /usr/local/bin/node
COPY --from=node_source /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

COPY --from=builder /opt/python        /opt/python
COPY --from=builder /opt/hermes-agent  /opt/hermes-agent

# Build del frontend della dashboard (Vite/TypeScript in hermes-agent/web).
# `--workspace web` (non un `npm install` alla radice, come il Dockerfile
# ufficiale di hermes-agent fa per TUTTI i workspace): risolve comunque la
# dipendenza locale apps/shared (npm segue i workspace link a prescindere
# dal filtro), ma evita di installare apps/desktop e la sua node-pty, un
# addon nativo che richiede un python3 di sistema per compilare (non
# presente in questa immagine, e comunque inutile: il dashboard usa
# ptyprocess Python lato backend, xterm.js lato frontend — niente PTY di
# Node qui). node_modules resta nell'immagine: un futuro `hermes update` lo
# riusa per il rebuild.
WORKDIR /opt/hermes-agent

# Fix per le pagine che restavano vuote sotto Ingress (System/Chat — vedi
# CHANGELOG 0.5.2): Vite fissa in fase di build l'URL assoluto "/assets/..."
# dentro i chunk JS delle pagine caricate on-demand, ignorando qualunque
# prefisso di Ingress. La riscrittura server-side di hermes-agent
# (X-Forwarded-Prefix → prefisso nell'HTML) non può toccare quei file già
# compilati. `patches/vite-base-path-runtime.snippet` aggiunge un
# `experimental.renderBuiltUrl` che calcola quell'URL a runtime nel browser
# usando `window.__HERMES_BASE_PATH__` (variabile che hermes-agent inietta
# già correttamente ad ogni richiesta). Applicata con `sed`, NON committata:
# `hermes update` fa autostash di ogni modifica non committata prima del
# `git pull` e la riapplica dopo (comportamento nativo, non nostro — vedi
# hermes_cli/update_cmd_stash.py), quindi la patch sopravvive agli
# aggiornamenti dalla dashboard senza bisogno di un rebuild Docker. Se una
# futura release upstream modificasse proprio quelle righe di
# vite.config.ts, il solo rischio è che l'autostash vada in conflitto: in
# quel caso hermes-agent lascia la patch (non il resto dell'update) parcheggiata
# nello stash e il codice si aggiorna comunque — vedi DOCS.md.
COPY patches/vite-base-path-runtime.snippet /tmp/vite-base-path-runtime.snippet
RUN set -eux; \
    sed -i '/^export default defineConfig({$/r /tmp/vite-base-path-runtime.snippet' web/vite.config.ts; \
    grep -q 'HERMES_BASE_PATH' web/vite.config.ts; \
    rm /tmp/vite-base-path-runtime.snippet

# Non è un `npm install <pkg>` senza versione: installa l'intero
# workspace dal `package-lock.json` committato (versioni già pinnate lì).
# hadolint ignore=DL3016
RUN set -eux; \
    npm install --workspace web --include-workspace-root \
        --prefer-offline --no-audit --fetch-retries=5; \
    npm run build --prefix web; \
    test -f hermes_cli/web_dist/index.html; \
    grep -q 'HERMES_BASE_PATH' hermes_cli/web_dist/assets/index-*.js

COPY rootfs /

# I permessi di esecuzione si perdono facilmente copiando via Samba: li
# reimpostiamo qui invece di affidarci ai file sorgente.
RUN chmod 0755 \
        /etc/s6-overlay/scripts/init-hermes.sh \
        /etc/s6-overlay/s6-rc.d/dashboard/run \
        /etc/s6-overlay/s6-rc.d/main-hermes/run \
        /etc/s6-overlay/s6-rc.d/nginx/run \
        /etc/s6-overlay/s6-rc.d/nginx/finish \
        /etc/s6-overlay/s6-rc.d/sshd/run \
        /usr/local/bin/hermes \
    && chmod 0644 /usr/local/lib/hermes-ha/render_config.py /etc/ssh/sshd_config \
    && chown -R root:root /opt \
    && chmod -R go-w /opt \
    # Unica eccezione a "/opt non scrivibile da hermes" (regola #4, T6):
    # /opt/hermes-agent deve restare scrivibile perché `hermes update` fa
    # git pull + reinstall lì dentro. Il resto di /opt (Python gestito da
    # uv, node/npm) resta di root, non scrivibile.
    && chown -R hermes:hermes /opt/hermes-agent

# Nessun CMD: l'ENTRYPOINT /init dell'immagine base avvia s6-overlay, che
# esegue i servizi definiti in /etc/s6-overlay/s6-rc.d.
