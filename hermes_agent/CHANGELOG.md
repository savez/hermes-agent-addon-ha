# Changelog

## 0.6.3

**Il pulsante "Update" ora segue le release, non il branch `main`.**
Incidente reale sul Pi il 2026-09-29: premuto Update, l'assistente non è
più partito con
`cannot import name 'TODO_LEGACY_ALIASES' from 'tools.todo_tool'`.

- **Causa**: per un'installazione da **sorgente** — la nostra: `git clone`,
  nessuno stamp di pacchetto — il canale predefinito di Hermes è `main`, non
  `stable` (`hermes_cli/update_channel.py`, `default_channel`: *"«self»
  source installs follow main"*). Il pulsante ha quindi portato il checkout
  dal tag `v2026.9.24` a `main`, **2129 commit dopo l'ultimo tag canary**,
  cioè sviluppo non rilasciato. Conseguenze a cascata: l'`ImportError`
  sopra, e la nostra patch a `vite.config.ts` messa in autostash e **non
  ripristinata** per conflitto (lo scenario già documentato in `DOCS.md`
  come rischio residuo della 0.5.2) — quindi anche le pagine System/Chat
  sarebbero tornate bianche al primo rebuild del frontend.
- **Fix**: `render_config.py` scrive sempre il canale `stable` nel record
  per-installazione (`update.installs.<id>.channel`), dove `<id>` è
  `sha256(percorso di installazione)[:16]` — verificato che per
  `/opt/hermes-agent` dà `ffad2f5543956651`, lo stesso id che genera
  `hermes update --set-channel stable`. Scelta confermata dall'utente:
  restare sempre su `stable`.
- **Da sapere**: il rimedio a un Update finito su `main` è **ricostruire
  l'App**. Il build riclona l'ultimo tag di release e riapplica da solo la
  patch a `vite.config.ts`, senza toccare `/data/hermes` (profili, memoria,
  cron restano). Verificato che l'incidente aveva toccato solo cache
  rigenerabili: `_config_version` era rimasto a 46.

## 0.6.2

**I profili secondari ora vengono davvero serviti dal gateway.** Trovato dal
messaggio che Hermes stesso mostrava sul Pi il 2026-09-28 (T8):

```
Your gateway serves only one profile. Not served: ivana, savez.
Why: s6-supervised container without a root gateway slot
     (/run/service/gateway-default); the container's boot registers it.
```

- **Causa**: Hermes multiplexa i profili solo dopo un controllo preliminare
  che **si rifiuta** quando gira sotto s6 e non trova lo slot dinamico
  `/run/service/gateway-default` — quello che l'immagine ufficiale registra
  al boot. Da noi quello slot non esiste di proposito: il gateway è il
  servizio s6 **statico** `main-hermes` (0.6.0), scelto per non rendere
  `/run/service` scrivibile da `hermes`. Per Hermes è quindi un falso
  positivo, e il risultato era un gateway che serviva solo `default`.
- **Fix**: `render_config.py` ora scrive sempre
  `gateway.multiplex_profiles: true`. Un `true` esplicito **salta** quel
  controllo (`hermes_cli/gateway_multiplex_mode.py`, `resolve_multiplex_mode`:
  `if current: return MultiplexDecision(True, "config")`), ed è corretto
  affermarlo perché l'architettura dell'App garantisce esattamente **un**
  gateway: s6 ne supervisiona uno solo e la registrazione dinamica
  per-profilo non è raggiungibile.
- **Verificato in produzione**: prima `served_profiles()` restituiva solo
  `('default',)`; applicata la chiave e riavviato il gateway, restituisce
  `('default', 'ivana', 'savez')`. Verificato anche che `render_config.py`
  conserva tutte le chiavi che non gestisce (modello, dashboard, platforms,
  moa) mentre aggiunge la nuova.

## 0.6.1

**Il token di Home Assistant ora viene propagato ai profili secondari.**
Trovato creando i primi profili aggiuntivi sul Pi reale il 2026-09-28 (T8):

- `init-hermes.sh` riscriveva `HERMES_HA_TOKEN` solo in
  `/data/hermes/.env`. Ma il token del Supervisor **cambia a ogni avvio del
  container**, e ogni profilo creato con `hermes profile create` ha un
  proprio `.env` più un `config.yaml` che punta allo stesso MCP di HA con
  `${HERMES_HA_TOKEN}`. Risultato: un profilo secondario si portava dietro
  la copia del token presa al momento della clonazione e **perdeva
  l'accesso a Home Assistant al primo riavvio dell'App** (l'MCP avrebbe
  risposto 401 senza che niente lo spiegasse).
- Ora lo script scrive il token in tutti i profili sotto
  `/data/hermes/profiles/`, saltando le cartelle nascoste (es. il
  tombstone `.deleted`), e lo segnala nel log: *"Token di HA propagato a N
  profilo/i secondario/i"*. Le altre chiavi dei `.env` — API key dei
  provider e i token dei bot di ciascun profilo — restano intatte.
  Verificato con un test della logica su Linux (stessa `sed` della
  produzione): token aggiornato ovunque, tutto il resto preservato.

## 0.6.0

**Il gateway (Telegram e gli altri canali) ora parte davvero.** Tre problemi
distinti, tutti diagnosticati collegandosi via SSH al Pi reale il 2026-09-26
(T7) — non per ipotesi:

- **Il gateway non partiva affatto**: `hermes gateway run` non gira in
  foreground come sembra, ma rimbalza su `gateway start`, che prova a
  registrarsi come servizio s6 *dinamico* scrivendo in `/run/service` — di
  root, non scrivibile dall'utente `hermes` — e muore con
  `[Errno 13] Permission denied: '/run/service/.gateway-default.tmp'`.
  Quella registrazione dinamica assume per giunta i path dell'immagine
  ufficiale (`/opt/hermes/.venv`, `/opt/data`), che qui non esistono: anche
  con i permessi aperti avrebbe generato un servizio morto all'avvio.
  **Fix**: nuovo servizio s6 *statico* nostro,
  `rootfs/etc/s6-overlay/s6-rc.d/main-hermes/`, che esegue
  `hermes gateway run --replace` come utente `hermes` con
  `HERMES_S6_SUPERVISED_CHILD=1` (il sentinella che disattiva il rimbalzo su
  `gateway start`). Il nome `main-hermes` è quello che hermes-agent si
  aspetta per il servizio statico del gateway, così `hermes doctor` lo
  riconosce. Verificato dal vivo: con quel sentinella il gateway si avvia
  e resta su.
- **Telegram non si attivava comunque**: `ModuleNotFoundError: No module
  named 'telegram'` → `Platform 'Telegram' requirements not met` / `No
  adapter available for telegram`. L'extra `messaging`
  (`python-telegram-bot`, discord, slack) è stato tolto da `all` upstream il
  2026-05-12 perché conta di installarsi pigramente al primo uso — e noi i
  lazy install li abbiamo disattivati (regola #9). **Fix**: aggiunto
  `--extra messaging` a `HERMES_EXTRAS` nel Dockerfile, che è esattamente la
  via d'uscita prevista dalla regola #9 (nuovi provider = extra + rebuild).
- **`git` non era nell'immagine finale**: era installato solo nello stage di
  build. Quindi il pulsante "Update" della dashboard (regola #1, abilitato
  di proposito) era semplicemente **impossibile**, e con lui l'autostash che
  porta avanti la patch a `vite.config.ts` introdotta in 0.5.2. **Fix**:
  `git` aggiunto anche allo stage runtime.

## 0.5.3

**Fix per "sidecar connect failed" / "Reconnect side panel" e per il
terminale (pty) di Chat/System sotto Ingress**, trovato da un caso reale
sul Pi (log `pty refused: origin_mismatch origin=http://<ip-di-home-assistant>:8123
bound=127.0.0.1 peer=127.0.0.1`) e verificato con test diretti sul codice
e con un handshake WebSocket reale:

- **Causa**: tutte le rotte WebSocket della dashboard (`/api/pty` — il
  terminale usato anche dalla Chat principale, `/api/ws` — il sidecar
  JSON-RPC del pannello laterale, `/api/events` — il feed di attività)
  ripetono un controllo anti-DNS-rebinding sull'header `Origin`,
  indipendente da quello sull'Host già corretto in `0.3.4` (il middleware
  HTTP normale non gira sulle rotte WebSocket, quindi hermes-agent lo
  ripete lì). Il browser manda l'Origin reale
  (`http://<ip-di-home-assistant>:8123`), che non combacia con l'interfaccia di
  bind (`127.0.0.1`) — connessione rifiutata (403 all'handshake).
- **Fix**: aggiunto in `nginx.conf`, accanto all'override esistente di
  `Host`, `proxy_set_header Origin http://127.0.0.1:8788;` — stesso
  principio del fix già in produzione per l'Host.
- **Verificato**: build reale, poi con un client WebSocket vero
  (`websockets`) e un token di sessione valido, stessa richiesta a
  `/api/pty`: **rifiutata (403)** con l'Origin reale del browser,
  **accettata** con l'Origin riscritto come fa ora `nginx.conf`.

## 0.5.2

**Fix reale (non più "al buio") per System/Chat che restavano vuote sotto
Ingress**, trovato leggendo il codice sorgente di Vite/hermes-agent e
verificato con una build e un'esecuzione reali (non solo sul Pi):

- **Causa**: `hermes-agent` riscrive correttamente il prefisso di Ingress
  in `index.html` a ogni richiesta (per questo il caricamento iniziale
  funzionava), ma non nei file `.js` già compilati delle pagine caricate
  "on demand" (React.lazy). Vite/Rolldown vi fissa in fase di build il
  percorso assoluto `/assets/...` come stringa fissa, indipendente da
  qualunque header. Aprendo System (che carica anche il CSS del terminale
  xterm) il browser tentava di scaricare quei file **direttamente da Home
  Assistant Core** (`<ip-di-home-assistant>:8123/assets/...`), non dal nostro
  addon — 404 sicuro. Il fallimento del preload del CSS interrompeva tutto
  il caricamento della pagina, che per questo restava vuota.
- **Fix**: `patches/vite-base-path-runtime.snippet`, applicato con `sed`
  nel Dockerfile su `web/vite.config.ts` prima della build del frontend.
  Aggiunge un `experimental.renderBuiltUrl` che calcola quell'URL **a
  runtime nel browser** usando `window.__HERMES_BASE_PATH__` — variabile
  che il backend di hermes-agent inietta già correttamente a ogni
  richiesta (la stessa che usa per il router della SPA). Verificato: build
  reale, poi container reale in esecuzione, curl con `X-Ingress-Path`
  simulato — il bundle compilato usa `(window.__HERMES_BASE_PATH__||"")+`
  al posto della stringa fissa, e `window.__HERMES_BASE_PATH__` viene
  impostato al prefisso corretto prima che il modulo JS lo legga.
- **Applicata senza commit git, deliberatamente**: `hermes update` fa
  autostash di ogni modifica non committata prima del `git pull` e la
  riapplica dopo (comportamento nativo di hermes-agent, non nostro — vedi
  `hermes_cli/update_cmd_stash.py` upstream), quindi questa patch
  sopravvive agli aggiornamenti dalla dashboard senza bisogno di un
  rebuild Docker completo. Unico rischio residuo, non distruttivo: se una
  futura release upstream modificasse proprio quelle righe di
  `vite.config.ts`, l'autostash potrebbe andare in conflitto — in quel
  caso `hermes update` lascia la patch (non il resto dell'aggiornamento)
  parcheggiata nello stash e il codice si aggiorna comunque; la patch va
  poi ripristinata con un rebuild Docker.
- Confermato inerte (non l'ipotesi giusta) il fix "al buio" per il
  prefisso del path aggiunto in 0.5.0 (T6bis): l'`access_log` dedicato
  mostra `request_uri`/`rewritten_uri` sempre identici sul Pi reale — il
  Supervisor toglie già da solo il prefisso del token. Lasciato in
  `nginx.conf` perché innocuo.

## 0.5.1

Richiesta esplicita dell'utente: l'immagine occupava quasi 3GB.

- **Riduzione dimensione immagine**: il `git clone` di `hermes-agent` nel
  Dockerfile ora usa `--filter=tree:0` invece di un clone completo. Scarica
  comunque TUTTA la storia dei commit (nessun impatto sulla sicurezza di
  `hermes update`, che fa `git fetch`/`git merge --ff-only` dopo il primo
  avvio — verificato empiricamente: un `git fetch` su un repo clonato così
  funziona normalmente), ma non gli alberi/blob delle versioni passate dei
  file, che restano scaricabili al bisogno. Su questo repo taglia `.git` da
  ~1.1GB a ~130MB (circa 900MB in meno). Scartata l'alternativa
  `--depth 1` (clone superficiale): taglia anche la storia dei commit,
  rendendo i `git fetch` futuri di `hermes update` meno affidabili o a
  rischio di fallire.

## 0.5.0

Tornati a Ingress dopo meno di un giorno sulla porta diretta (0.4.0):
un profilo Hermes potrebbe in futuro legarsi a un'utenza HA, il che
richiede l'identità che passa da Ingress — vedi `CLAUDE.md` regola #5.

- Ripristinati `ingress`/`ingress_port`/`panel_*` in `config.yaml`, la
  allow-list nginx limitata al Supervisor, l'override `Host`, la
  traduzione `X-Ingress-Path` → `X-Forwarded-Prefix`.
- **Fix "al buio" (T6bis), non ancora confermato sul Pi**: aggiunta a
  `nginx.conf` una riscrittura del path (`rewrite ... last;` a livello di
  server) che toglie il prefisso `/api/hassio_ingress/<token>` dal path
  della richiesta **se il Supervisor non lo toglie già da solo** — ipotesi
  per spiegare perché System/Chat non si caricavano anche con il fix
  dell'header già applicato in 0.3.2. Se il Supervisor lo toglie già, il
  fix non ha alcun effetto (verificato in entrambi gli scenari
  localmente). Aggiunto un `access_log` dedicato (`ingress_debug`) che
  mostra `request_uri` (come arrivato) vs `rewritten_uri` (dopo il fix)
  per ogni richiesta — usalo per confermare quale caso si applica
  davvero e se System/Chat ora funzionano.
- SSH (porta 2222) pubblicata direttamente sulla LAN per default (decisione
  indipendente da quella sopra, presa nello stesso momento): niente più
  tunnel obbligatorio via "Advanced SSH & Web Terminal" per la CLI.

## 0.4.0

Scelta esplicita dell'utente, dopo una serie di bug del prefisso di
Ingress mai completamente risolti (0.3.2/0.3.3/0.3.4) — vedi `CLAUDE.md`
regola #5 e `DOCS.md` → "Modello di sicurezza":

- **Rimosso il pannello Ingress**: niente più `ingress`/`ingress_port`/
  `panel_*` in `config.yaml`. La dashboard è ora raggiungibile
  **direttamente sulla LAN**, porta **8099** (pubblicata di default),
  come un'App con una sua porta pubblica (es. Uptime Kuma) — non più
  nella sidebar di HA.
- Rimossi da `nginx.conf` l'allow-list ristretta al solo Supervisor e la
  traduzione `X-Ingress-Path` → `X-Forwarded-Prefix` (non più necessaria
  senza un prefisso di path). Mantenuto l'override dell'header `Host`
  verso la dashboard (resta necessario: lei bind sempre 127.0.0.1
  internamente, indipendentemente da come nginx è esposto fuori).
- `watchdog` torna a usare `[PORT:8099]` (ora si risolve correttamente:
  8099 è davvero in `ports:`).
- **Conseguenza di sicurezza esplicitamente accettata**: combinato con la
  0.3.3 (niente password), la dashboard non ha più **nessuna barriera di
  login** — solo l'isolamento della rete locale. Chiunque raggiunga
  l'IP del Pi sulla LAN ha accesso completo (shell, token di HA, chiavi
  API).

## 0.3.4

- **Fix critico**: dopo la 0.3.3 (niente più login), il pannello Ingress
  dava `{"detail":"Invalid Host header. Dashboard requests must use the
  bound hostname or the configured public hostname."}`. Causa: la
  dashboard rifiuta ogni richiesta il cui `Host` non combaci con
  l'interfaccia su cui è in ascolto (protezione anti-DNS-rebinding,
  **indipendente dal login** — bindiamo `127.0.0.1`, quindi accetta solo
  Host `localhost`/`127.0.0.1`/`::1`); il vecchio trucco Host/Origin
  rimosso in 0.3.3 soddisfaceva anche questo controllo per coincidenza.
  Corretto in `nginx.conf`: `proxy_set_header Host 127.0.0.1:8788;` (un
  Host letterale, genuinamente loopback — non riattiva il gate di
  autenticazione, che dipende solo dal bind/`public_url`, non dall'Host
  della richiesta). Verificato con build e run reali simulando l'Host
  reale del client (`<ip-di-home-assistant>:8123`): 200 OK, `auth_required:false`.

## 0.3.3

Scelta esplicita dell'utente che riduce ulteriormente le garanzie della
0.3.2 — vedi `DOCS.md` → "Modello di sicurezza":

- **Rimossa la password della dashboard** (`dashboard_password`,
  opzione e schema in `config.yaml`). La dashboard non registra più un
  provider di autenticazione: l'unica barriera per arrivarci resta il
  login di Home Assistant, dietro cui sta il pannello Ingress. Chiunque
  abbia un account HA (anche non admin) entra senza altra password.
- Rimosso di conseguenza il trucco Host/Origin sintetico in `nginx.conf`
  (serviva solo a forzare il gate di autenticazione ora non più presente)
  — nginx ora passa a monte l'header `Host` reale del client.
- Rimossa la generazione del secret di sessione (`.dashboard_secret`) in
  `init-hermes.sh`: non serve più senza un provider di autenticazione.

## 0.3.2

- **Fix critico**: il pannello Ingress dava sempre 404 dopo il login. Causa:
  la dashboard prefissa i propri redirect (es. verso `/login`) leggendo
  l'header standard `X-Forwarded-Prefix`, ma il Supervisor di HA manda
  invece `X-Ingress-Path` (header proprietario di HA) — senza traduzione,
  il redirect usciva come path assoluto senza prefisso, il browser lo
  seguiva fuori dal proxy di Ingress e finiva su un path che HA Core non
  conosce. Corretto in `nginx.conf`:
  `proxy_set_header X-Forwarded-Prefix $http_x_ingress_path;`.
  Verificato: con l'header simulato, il redirect ora esce correttamente
  prefissato (`/api/hassio_ingress/<token>/login` invece di `/login`).

## 0.3.1

- **Fix critico**: il `watchdog` in `config.yaml` puntava a
  `http://[HOST]:[PORT:8099]/api/health` — `[PORT:8099]` non si risolve
  perché 8099 (porta di Ingress) non è elencata in `ports:`. Il Supervisor
  colpiva un URL rotto, considerava l'App "non sana" e la riavviava in
  loop pochi secondi/minuti dopo ogni avvio riuscito. Trovato da un caso
  reale sul Pi (pannello Ingress sempre 404, log del Supervisor con stop
  puliti ripetuti subito dopo ogni "Avvio nginx"). Corretto usando la
  porta letterale: `http://[HOST]:8099/api/health`.

## 0.3.0

Scelte esplicite dell'utente che riducono le garanzie di immutabilità
della 0.2.0 — vedi `DOCS.md` → "Modello di sicurezza":

- Sostituito `hermes-webui` (nesquena) con la **dashboard nativa** di
  `hermes-agent` (comando `hermes dashboard`): più completa (sessioni,
  cron, profili, MCP dalla UI, review git), stesso bind
  `127.0.0.1:8788`.
- `hermes-agent` **non è più pinnato**: ogni build clona l'ultimo tag
  disponibile su GitHub, senza verificare un commit atteso.
- **Update dalla dashboard abilitato**: il pulsante "Update" (`git pull` +
  reinstall dentro `/opt/hermes-agent`) applica un aggiornamento senza
  rebuild Docker. Solo `/opt/hermes-agent` (non il resto di `/opt`) è
  scrivibile dall'utente `hermes` per permetterlo.
- Aggiunto uno stage Node 26/npm al Dockerfile per buildare il frontend
  della dashboard (`web/`, Vite/TypeScript); Node/npm restano
  nell'immagine finale per i rebuild del frontend che un futuro `hermes
  update` può innescare.
- Bloccati via `nginx.conf` due endpoint della dashboard che
  installavano dipendenze a runtime bypassando il blocco dei lazy
  install: setup dei provider di memoria cloud esterni e onboarding del
  bridge WhatsApp.
- `nginx.conf` riscrive gli header `Host`/`Origin` verso la dashboard a
  un valore sintetico fisso, così il login resta sempre obbligatorio
  (regola non negoziabile) a prescindere dall'URL reale con cui si apre
  HA — la dashboard nativa richiederebbe altrimenti login solo per bind
  non-loopback.
- Rinominata l'opzione `webui_password` in `dashboard_password`; rimossa
  `allowed_origins` (non più necessaria con il punto sopra).

## 0.2.0

- `hermes-agent` aggiornato a `v2026.9.24` (commit
  `f97608f178d1ffeca59860195ab7da295f7c8e5f`), da `v2026.8.13`: risolve
  un'incompatibilità di schema con `hermes-webui v0.51.137` (la lista
  sessioni nel pannello era disattivata per una colonna `source` mancante
  in `state.db`).
- Corretto un bug in `init-hermes.sh`: la scrittura di
  `ssh_authorized_keys` su file poteva abortire silenziosamente l'init
  sotto `set -e` per un'idiosincrasia di `bashio::config` (vedi commit).

## 0.1.0

- Prima versione: Hermes Agent (`v2026.8.13`) + hermes-webui (`v0.51.137`)
  come App locale per Home Assistant OS, pannello Ingress, CLI via SSH,
  utente non privilegiato `hermes`, accesso a HA limitato via MCP di
  default.
