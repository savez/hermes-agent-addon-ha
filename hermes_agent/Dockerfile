# =============================================================================
# Hermes Agent — App per Home Assistant OS
#
# Immagine immutabile, `hermes-agent` compreso (dalla 0.8.0): ogni versione
# dell'App corrisponde a un tag di Hermes e al suo commit, verificato al
# build. L'update in-place di Hermes è chiuso (`.install_method` + /opt di
# root): il codice dell'agente cambia solo con una nuova versione dell'App.
# Vedi CLAUDE.md regole #2/#4 e DOCS.md → "Aggiornare".
# =============================================================================

ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-debian:bookworm

# uv da immagine ufficiale Astral (niente `curl | sh`).
# Per un pin ancora più stretto aggiungi il digest: ghcr.io/astral-sh/uv:0.11.6@sha256:...
FROM ghcr.io/astral-sh/uv:0.11.6 AS uv

# Node per la build del frontend della dashboard (`web/`, Vite/TypeScript).
# hermes-agent pinna il proprio toolchain a Node 26 ovunque (vedi il
# Dockerfile ufficiale del progetto): stessa scelta qui. Serve anche nello
# stage runtime, non solo in build: la TUI raggiungibile via SSH gira con
# node (`ui-tui/dist`, vedi CHANGELOG 0.7.4).
FROM node:26-bookworm-slim AS node_source

# ─── Stage 1: builder (Python/venv) ────────────────────────────────────────
FROM ${BUILD_FROM} AS builder

# /bin/sh sull'immagine base Debian è dash, che non supporta
# `set -o pipefail` e altre estensioni bash usate nei RUN sotto. bash è
# già presente nell'immagine base (lo richiedono gli
# script bashio dello stage runtime).
SHELL ["/bin/bash", "-c"]

# Versione di hermes-agent: tag e commit atteso, una coppia per versione
# dell'App. Se il tag a monte non punta più a HERMES_COMMIT (spostato o
# manomesso) il build si ferma. Al salto di versione si aggiornano insieme a
# HA_PLUGIN_SHA (sotto) e si ricontrolla PYTHON_VERSION — checklist in
# CLAUDE.md.
ARG HERMES_REPO=https://github.com/NousResearch/hermes-agent.git
ARG HERMES_REF=v0.22.2
ARG HERMES_COMMIT=d923a5eb487a17c0a68801bba9ef0f56c81040a8
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
# La versione deve corrispondere a quella per cui è stato risolto `uv.lock`,
# non a quella che `requires-python` dichiara ammissibile: `uv sync --frozen`
# pretende l'ambiente del lock e rifiuta gli altri. Il lock della v0.21.7 dice
# `requires-python = ">=3.11, <3.15"` ma ha
# `resolution-markers = ["python_full_version >= '3.14' ..."]`, quindi con la
# 3.12 il build muore con "The current Python platform is not compatible with
# the lockfile's supported environments" (incidente del 2026-10-12). Il lock
# della v0.22.2 ha gli stessi marker (verificato il 2026-10-21). Da
# ricontrollare a ogni salto di versione di hermes-agent.
ARG PYTHON_VERSION=3.14

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
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Clona il tag fissato e verifica che punti al commit atteso: un tag spostato
# a monte ferma il build invece di consegnare un'immagine diversa da quella
# provata. `--filter=tree:0` tiene la storia dei commit (git describe e le
# informazioni di versione di Hermes la leggono) senza gli alberi delle
# versioni passate: `.git` passa da ~1.1GB a ~130MB.
RUN set -eu; \
    git clone --filter=tree:0 --branch "${HERMES_REF}" "${HERMES_REPO}" /opt/hermes-agent; \
    found="$(git -C /opt/hermes-agent rev-parse HEAD)"; \
    if [ "${found}" != "${HERMES_COMMIT}" ]; then \
        echo "hermes-agent: ${HERMES_REF} punta a ${found}, atteso ${HERMES_COMMIT}" >&2; \
        exit 1; \
    fi; \
    echo "hermes-agent: ${HERMES_REF} = ${found} (verificato)"

# Plugin ufficiale Home Assistant, usato solo con `ha_access: full`
# (render_config.py lo collega in /data/hermes/plugins). Il toolset
# `homeassistant` è uscito dal core di Hermes nella v0.21.6 e a monte si
# installa dal catalogo al primo avvio, ma solo con i lazy install attivi: da
# noi sono spenti (regola #9), quindi lo mettiamo nell'immagine. Lo SHA è
# quello di `plugin-catalog/homeassistant.yaml` di HERMES_REF (versione 2.0.1):
# va riallineato a ogni salto di versione di Hermes. Unica dipendenza aiohttp,
# già nel venv (controllo di import sotto).
ARG HA_PLUGIN_REPO=https://github.com/NousResearch/hermes-official-plugins.git
ARG HA_PLUGIN_SHA=a4e311e433f1470b1fec15434deea6a05e8644eb
RUN set -eu; \
    git clone --filter=blob:none --no-checkout "${HA_PLUGIN_REPO}" /tmp/official-plugins; \
    git -C /tmp/official-plugins checkout -q "${HA_PLUGIN_SHA}" -- homeassistant; \
    mkdir -p /opt/hermes-ha-plugins; \
    cp -a /tmp/official-plugins/homeassistant /opt/hermes-ha-plugins/homeassistant; \
    rm -rf /opt/hermes-ha-plugins/homeassistant/tests /tmp/official-plugins; \
    test -f /opt/hermes-ha-plugins/homeassistant/plugin.yaml

# Python gestito da uv + venv dell'agent dal lockfile upstream (--frozen:
# nessuna risoluzione di dipendenze, solo le versioni pinnate in uv.lock).
# La dashboard (frontend Vite + backend FastAPI) è dentro hermes-agent
# stesso: nessun secondo progetto da clonare/gestire separatamente.
#
# numpy è aggiunto a parte perché non sta nel lockfile di Hermes: è la
# dipendenza opzionale del provider di memoria `holographic`, che senza di
# essa degrada **in silenzio** a sola ricerca full-text — `_HAS_NUMPY=False`
# azzera il peso HRR e fa ricadere `probe`, `related` e `reason` su FTS5
# (plugins/memory/holographic/retrieval.py). Installarla a runtime non regge:
# `hermes update` esegue `uv sync`, che rimuove quanto il lock non conosce.
# Costa 68 MB; va nel venv dell'agent, non in un venv separato, perché è
# quello da cui Hermes importa.
#
# pyyaml è una dipendenza **nostra**: `render_config.py` fa `import yaml` e
# gira con questo stesso venv (`init-hermes.sh`: `PY=/opt/hermes-agent/.venv/
# bin/python`). Finora la prendevamo in prestito dalle dipendenze transitive
# di hermes-agent, e si è rotta appena upstream è passato da PyYAML a
# `ruamel.yaml` nella v0.21.7: il build si è fermato su `ModuleNotFoundError:
# No module named 'yaml'` (2026-10-12). Dipendere da una transitiva altrui è
# una fragilità silenziosa — qui la dichiariamo.
#
# Il controllo di import sotto non è decorativo: è ciò che ha fermato il build
# invece di consegnare un'immagine che si costruisce e poi non parte, perché
# `init-hermes.sh` esegue `render_config.py` a ogni avvio.
WORKDIR /opt/hermes-agent
RUN set -eux; \
    uv python install "${PYTHON_VERSION}"; \
    uv sync --frozen --python "${PYTHON_VERSION}" ${HERMES_EXTRAS}; \
    uv pip install --python .venv/bin/python numpy pyyaml; \
    .venv/bin/python -c "import yaml, cryptography, fastapi, uvicorn, numpy, aiohttp"; \
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
        # git resta nell'immagine finale: l'update in-place è chiuso dalla
        # 0.8.0, ma Hermes legge le informazioni di versione dal checkout e
        # può usare git per altre funzioni. Toglierlo richiede prima di
        # verificare chi lo usa a monte.
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
COPY --from=builder /opt/hermes-ha-plugins /opt/hermes-ha-plugins

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
#
# Servono DUE workspace, non solo `web`. Dalla v0.21.7 la dashboard, prima di
# partire, chiama `scripts/build/node-deps.mjs --workspace ui-tui --workspace
# web`: se le dipendenze di uno dei due mancano solleva "Workspace
# dependencies are stale or missing and lazy installs are disabled" e il
# servizio **riparte in ciclo** (regola #9: i lazy install sono spenti, quindi
# non può rimediare da sé). Con il solo `web` installato l'immagine si
# costruisce benissimo e la dashboard non parte mai — incidente del
# 2026-10-12. Il `test -d ui-tui/node_modules` sotto è lì per far fallire il
# build invece di consegnare quel ciclo.
# hadolint ignore=DL3016
RUN set -eux; \
    npm install --workspace web --workspace ui-tui --include-workspace-root \
        --prefer-offline --no-audit --fetch-retries=5; \
    npm run build --prefix web; \
    test -f hermes_cli/web_dist/index.html; \
    grep -q 'HERMES_BASE_PATH' hermes_cli/web_dist/assets/index-*.js; \
    test -d ui-tui/node_modules

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
    # Update in-place di Hermes chiuso (regola #4). La stamp `docker` è
    # l'interfaccia prevista a monte per le installazioni gestite da
    # un'immagine: `detect_install_method` la legge per prima, `hermes update`
    # rifiuta (update_contract.evaluate_update_admission) e la dashboard
    # risponde `can_apply: false`. Gli altri effetti sono solo testi di
    # suggerimento (che citano `docker pull`: per noi vuol dire "aggiorna
    # l'App"). La barriera vera è la proprietà di root qui sotto.
    && printf 'docker\n' > /opt/hermes-agent/.install_method \
    # Con /opt di sola lettura Python non può più salvare i .pyc a runtime:
    # li compiliamo qui, venv compreso (le librerie di terze parti sono il
    # grosso degli import). Fatto in questo stage, dopo ogni COPY, perché i
    # .pyc vengono validati sul mtime dei sorgenti.
    && /opt/hermes-agent/.venv/bin/python -m compileall -q \
        -x '/(node_modules|\.git)/' /opt/hermes-agent >/dev/null \
    # Con il checkout di root, git eseguito da `hermes` rifiuta il repository
    # ("detected dubious ownership") e Hermes non riesce più a leggere la
    # propria versione: `hermes --version` diceva `vunknown` (verificato
    # nell'immagine di prova il 2026-10-21). Il repository è nostro e in sola
    # lettura: lo dichiariamo sicuro per tutti gli utenti.
    && git config --system --add safe.directory /opt/hermes-agent \
    # Tutto /opt è di root e non scrivibile da `hermes`, senza eccezioni.
    && chown -R root:root /opt \
    && chmod -R go-w /opt

# Nessun CMD: l'ENTRYPOINT /init dell'immagine base avvia s6-overlay, che
# esegue i servizi definiti in /etc/s6-overlay/s6-rc.d.
