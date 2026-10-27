# Hermes Agent

## Cos'è

Questa App fa girare [Hermes Agent](https://github.com/NousResearch/hermes-agent)
(NousResearch) dentro Home Assistant OS, con due modi per parlarci:

- un pannello nella sidebar di HA (Ingress), che mostra la **dashboard
  nativa di Hermes** (comando `hermes dashboard`, incluso nel pacchetto
  stesso — non un progetto separato) per configurare provider/modello,
  chattare, gestire le sessioni, i cron job, i profili e l'integrazione
  MCP direttamente dalla UI;
- una CLI (`hermes`) raggiungibile via SSH, per lo stesso agente da
  terminale.

**Cosa non contiene**: nessun modello LLM gira sul Raspberry Pi. Serve un
provider cloud (Anthropic, OpenAI, OpenRouter, ecc. — configurato al primo
avvio) o un endpoint compatibile che tu gestisci altrove. L'App fornisce solo
il runtime dell'agente e l'interfaccia, non l'intelligenza.

**Due funzioni della dashboard restano disattivate per sicurezza**: i
provider di memoria cloud esterni e il bridge WhatsApp installerebbero
dipendenze a runtime senza passare dal controllo che blocca gli
`pip`/`npm install` non richiesti — sono bloccati a livello di rete (vedi
"Modello di sicurezza" sotto), non configurabili da questa App.

Ogni versione dell'App installa **una versione fissa di `hermes-agent`**
(dalla 0.8.5: v0.22.5), verificata al build sul suo commit. Il pulsante
"Update" della dashboard è disattivato: Hermes si aggiorna aggiornando
l'App (vedi "Aggiornare" sotto).

**La dashboard non ha una propria password** (scelta deliberata, vedi
"Modello di sicurezza" sotto): l'unica barriera per arrivarci è il login
di Home Assistant stesso, dietro cui sta il pannello Ingress.

## Requisiti

- Home Assistant OS su un host **aarch64** (verificato il target Raspberry
  Pi 5; altre board aarch64 dovrebbero funzionare, non testate).
- Spazio disco: l'immagine buildata pesa **~850 MB** (misurato con
  `docker inspect` su Apple Silicon via Colima, build nativo arm64). Il
  peso viene soprattutto da Node.js/npm, che servono a costruire il
  frontend della dashboard e restano nell'immagine perché la CLI
  raggiungibile via SSH gira con Node. Il clone di `hermes-agent` usa
  `--filter=tree:0`: tiene la storia dei commit senza gli alberi delle
  versioni passate, il che da solo evita circa 900 MB.
  Considera comunque che i dati dell'agente in `/data` crescono con l'uso
  (cache dei modelli, sessioni, memoria, un profilo per ogni bot):
  tieniti **qualche GB libero**.
- Tempo di build: pochi minuti sullo stesso ambiente arm64 nativo. Sul
  Raspberry Pi, con storage su SD o USB, aspettati sensibilmente di più:
  la prima build non è istantanea.
- Un provider LLM configurato (chiave API di un provider cloud, o un
  endpoint compatibile OpenAI). **Nessun modello gira sul dispositivo.**
- Per la CLI via SSH basta aggiungere una chiave pubblica nelle opzioni
  (vedi "CLI via SSH" sotto): senza chiavi, sshd non parte affatto.

## Installazione come App locale

Questa non è un'App dello Store ufficiale: è un'**App locale**, installata
copiando la cartella su disco. Non viene scaricata nessuna immagine
precompilata — il Supervisor la builda lui, sul Pi, dal `Dockerfile` in
questa cartella (nessuna chiave `image:` in `config.yaml`).

1. Copia l'intera cartella `hermes_agent/` dentro `/addons/` sul Pi. Due
   modi:
   - via l'App **Samba share**: monta la condivisione `addons` dal tuo
     computer e copia la cartella;
   - via SSH (con l'App SSH stessa, o accesso diretto se disponibile):
     `scp -r hermes_agent/ <host>:/addons/`.
2. In Home Assistant: **Impostazioni → Add-on → Store**, poi il menu
   **⋮** in alto a destra → **"Controlla aggiornamenti"**. L'App apparirà
   sotto la sezione **"Local add-ons"**.
3. Apri l'App e clicca **Installa**. Il Supervisor builda l'immagine per
   aarch64 dal `Dockerfile`: la prima volta richiede il tempo indicato sopra
   (nessuna emulazione necessaria, il Pi è già aarch64).
4. **Avvia** — non c'è nessuna password da impostare prima: la dashboard
   non ne ha una propria (vedi "Modello di sicurezza").

## Configurazione

| Opzione | Default | Cosa fa e conseguenze di sicurezza |
|---|---|---|
| `ha_access` | `mcp` | Quanto l'agente vede di Home Assistant. `mcp`: solo le entità che esponi esplicitamente all'integrazione MCP Server/Assist, via il proxy del Supervisor. `full`: accesso REST completo all'API di Core (tutte le entità, tutti i servizi, incluso chiamare qualunque automazione) — usa lo stesso `SUPERVISOR_TOKEN` con pieni permessi. `none`: nessun accesso a HA. |
| `allow_shell_tools` | `false` | Se `false` (consigliato), i toolset `terminal`, `code_execution` e `file` sono disattivati: l'agente non può eseguire comandi o leggere file nel container, quindi **non può leggere il token di HA da `/data/hermes/.env`** anche con `ha_access` diverso da `none`. Se `true`, l'agente ha shell e filesystem nel container: può leggere quel token e qualunque altro segreto salvato lì. Attivalo solo se ti serve davvero e capisci la conseguenza. |
| `ssh_authorized_keys` | `[]` (vuota) | Chiavi pubbliche SSH autorizzate per l'utente `hermes` sulla porta 2222 (solo CLI, mai la dashboard). Vuota = SSH disattivato. Le chiavi le scrive solo l'App (file di proprietà di `root`, fuori da `/data/hermes`): l'agente stesso non può aggiungersene una. |

## Primo avvio

Dopo il primo avvio, apri il pannello **Hermes** nella sidebar (Ingress):
si apre direttamente la dashboard, senza un login separato — se sei
loggato in HA, sei dentro. Se è la prima volta che l'agente viene
avviato, configuri il provider LLM dall'onboarding della dashboard stessa.

In alternativa, dalla CLI via SSH (vedi sotto):

```
hermes model     # scegli provider e modello
hermes setup      # configurazione guidata completa
hermes chat       # chat da terminale, per una prova rapida
```

## Integrazione con HA

Per far vedere entità di Home Assistant all'agente:

1. Installa/abilita l'integrazione **"Model Context Protocol Server"** in
   HA (Impostazioni → Dispositivi e servizi → Aggiungi integrazione).
2. In quell'integrazione, esponi ad **Assist** solo le entità che vuoi che
   l'agente possa vedere e controllare — meno esponi, meno può fare
   l'agente anche nel caso peggiore.
3. Imposta `ha_access`:
   - `mcp` (default): l'agente vede solo le entità esposte ad Assist, via
     l'integrazione MCP Server;
   - `full`: oltre a MCP, l'agente ha accesso REST completo a Core,
     **indipendentemente** da cosa hai esposto ad Assist, tramite il plugin
     ufficiale `homeassistant` di Hermes (incluso nell'App dalla 0.8.0):
     `ha_list_entities`, `ha_get_state`, `ha_list_services`,
     `ha_call_service`. Può chiamare qualsiasi servizio su qualsiasi entità —
     serrature, allarmi, tapparelle, automazioni — tranne i domini che
     eseguono codice o fanno richieste di rete (`shell_command`,
     `command_line`, `python_script`, `pyscript`, `hassio`,
     `rest_command`), che il plugin rifiuta. Usalo solo se ti serve davvero
     l'automazione completa e ne accetti il rischio: ricorda che gli ordini
     possono arrivare anche dai canali di messaggistica, e che l'agente legge
     contenuti dal web;
   - `none`: l'agente non vede nulla di HA.

   Con `full` l'MCP resta attivo accanto al plugin, e i due si
   sovrappongono (27 tool MCP più i 4 `ha_*`). Se ti basta il plugin, spegni
   l'MCP dalla dashboard di Hermes o mettendo `enabled: false` sotto
   `mcp_servers.homeassistant` nel `config.yaml` del profilo: dalla 0.8.2
   l'App imposta solo url e token di quella voce e la tua scelta resta.

## CLI via SSH

La CLI serve per i comandi che la dashboard non copre e per diagnosticare
quando la dashboard stessa non funziona. Il manifest pubblica la porta
**2222 sulla rete locale**, e sshd accetta **solo chiavi** (mai password,
mai `root`, unico port-forwarding permesso `127.0.0.1:8788`).

1. Genera una coppia di chiavi, se non ne hai già una dedicata:
   ```
   ssh-keygen -t ed25519 -f ~/.ssh/hermes -C "hermes-addon"
   ```
2. Copia il contenuto di `~/.ssh/hermes.pub` nell'opzione
   `ssh_authorized_keys` dell'add-on (è una lista YAML):
   ```yaml
   ssh_authorized_keys:
     - ssh-ed25519 AAAA... commento
   ```
3. **Riavvia l'add-on.** Salvare le opzioni non basta: sshd legge le chiavi
   all'avvio. Nel log deve comparire
   `SSH CLI attivo su porta 2222 (1 chiave/i)`; se invece leggi
   `Nessuna chiave in 'ssh_authorized_keys'`, la chiave non è arrivata alla
   configurazione.
4. Collegati:
   ```
   ssh -i ~/.ssh/hermes -p 2222 hermes@<ip-di-home-assistant>
   hermes model          # scegli provider e modello
   hermes chat           # chat da terminale
   hermes doctor         # diagnostica
   ```

Se la porta non risponde pur avendo la riga di log corretta, controlla la
sezione **Rete** nella pagina dell'add-on: il campo della porta 2222 deve
essere valorizzato, altrimenti non viene pubblicata.

**Il compromesso, dichiarato**: SSH sulla LAN è comodo ma è una superficie
in più, e un errore di configurazione della rete domestica la espone.
L'alternativa più prudente è **svuotare `ssh_authorized_keys`** (così sshd
non parte) e raggiungere il container passando per l'add-on community
"Advanced SSH & Web Terminal" come jump host — serve
`ssh.allow_tcp_forwarding: true` nelle sue opzioni, e lo script
`tools/hermes-ssh` in questo repo automatizza il salto leggendo
l'indirizzo interno del container da `/share/hermes-agent/address`.

Da evitare in ogni caso: disattivare la *protection mode* del Supervisor
per usare `docker exec`. Quella protezione vale per tutti i container e per
l'host: spegnerla per comodità di accesso a uno solo apre un varco molto
più ampio del necessario.

## Posta con himalaya

Dalla 0.8.3 l'immagine contiene `himalaya` v1.2.0, il client IMAP/SMTP usato
dalle skill `himalaya` ed `email-inbox-triage` di Hermes. L'App non
configura nessuna casella: lo fai tu, da SSH, con `himalaya account
configure` (usa una password per app, non quella principale). La
configurazione sta in `/data/hermes/home/.config/himalaya/`.

L'agente lo usa solo con il toolset `terminal`, cioè con
`allow_shell_tools: true`: leggi prima il modello di sicurezza qui sotto,
perché con la shell l'agente può leggere anche il token di HA. Una mail può
inoltre contenere testo che l'agente scambia per istruzioni: per i controlli
automatici della posta tieni l'accesso in sola lettura.

## Immagini da SVG

Dalla 0.8.4 l'App aggiunge a Hermes il toolset `image_render`, con due tool:

- `svg_to_image`: l'agente scrive un SVG (grafico, schema, card, locandina)
  e lo trasforma in PNG, JPG o WEBP, con larghezza o altezza a scelta;
- `convert_image`: converte o ridimensiona un'immagine già nella cache di
  Hermes, per esempio una foto ricevuta su Telegram (anche HEIC) o un file
  prodotto da `svg_to_image`.

Il file finisce nella cache immagini del profilo (`cache/images`), e l'agente
lo invia scrivendo `MEDIA:<percorso>` nella risposta; può anche guardarlo con
il tool di vision per controllare il risultato. Il plugin è collegato e
abilitato in **tutti i profili** a ogni avvio, con qualunque `ha_access` e
anche con `allow_shell_tools: false`: non usa rete né shell e non legge
nessun file fuori dalla cache. Per spegnerlo in un profilo aggiungi
`image-render` a `plugins.disabled` nel suo `config.yaml`, oppure togli il
toolset dalla dashboard.

Limiti: lato massimo 4096 px; font disponibili solo DejaVu (sans-serif,
serif, monospace — le altre famiglie ricadono su sans-serif), niente emoji a
colori; nell'SVG sono ammessi solo riferimenti interni (`#id`) e immagini
inline `data:image/png|jpeg|gif|webp`, nessun file o URL esterno.

Dopo l'aggiornamento riavvia l'App e apri una sessione nuova (`/new` su
Telegram): l'elenco dei tool è fissato quando la sessione nasce.

## Profili: più agenti, più bot

Un profilo è un'istanza separata di Hermes dentro lo stesso add-on, con
**memoria, skill, cron, modello e bot propri**. Il profilo principale vive
in `/data/hermes`, quelli aggiuntivi in `/data/hermes/profiles/<nome>/`.

Un solo processo gateway serve tutti i profili (multiplex). Per crearne uno
serve la CLI:

```
hermes profile create <nome> --clone-all
```

`--clone-all` copia configurazione, credenziali dei provider e skill dal
profilo attivo, **escludendo i canali di messaggistica**: due profili con lo
stesso token del bot entrerebbero in conflitto sullo stesso flusso di
messaggi. Quindi ogni profilo vuole **il suo bot**: creane uno nuovo su
BotFather e inserisci token e utenti autorizzati selezionando quel profilo
nella dashboard, sezione **Channels**.

Due cose da ricordare, imparate sul campo:

- Dopo aver creato un profilo o modificato un canale, **riavvia l'add-on**.
  Attivare o disattivare una piattaforma dalla dashboard smonta
  l'adattatore ma non lo ricrea: il bot sembra collegato e resta muto.
- Le conversazioni sono separate per interlocutore, ma **memoria e
  configurazione sono condivise all'interno dello stesso profilo**. Se
  vuoi che due persone non condividano ciò che l'agente ricorda, servono
  due profili distinti, non due utenti sullo stesso profilo.

## Aggiornare

Hermes si aggiorna **solo aggiornando l'App**. Ogni versione dell'App
corrisponde a una versione di `hermes-agent` (tag + commit, verificati al
build): quando esce una versione nuova dell'App, Store → ⋮ → **"Controlla
aggiornamenti"** → **Aggiorna**. Il tag installato è stampato nel log del
build (Impostazioni → Sistema → Log → Supervisor).

Il pulsante "Update" della dashboard di Hermes è **disattivato**: Hermes
risponde che gli aggiornamenti si fanno fuori dalla dashboard, e da riga di
comando `hermes update` rifiuta citando `docker pull`. Per questa App
`docker pull` vuol dire "aggiorna l'App". Anche se qualcuno ci provasse,
`/opt/hermes-agent` è di root e non scrivibile.

Perché così: fino alla 0.7.x il build prendeva l'ultima release e il
pulsante era attivo. Ogni salto di versione di Hermes ha però richiesto
correzioni all'App (per la v0.21.7 tre release, 0.7.2–0.7.4), e un Update
dalla dashboard poteva portare una versione mai provata qui. Il prezzo della
scelta: le correzioni di Hermes, anche di sicurezza, arrivano solo con una
nuova versione dell'App.

**Ricostruisci** (Store → ⋮ → Ricostruisci) rifà la stessa immagine, con la
stessa versione di Hermes, **senza toccare `/data`**: profili, memoria,
cron, configurazioni e credenziali restano. È la via di ritorno da uno stato
incoerente.

Nota per chi contribuisce: questo add-on applica al frontend di Hermes una
piccola patch in fase di build (`patches/vite-base-path-runtime.snippet`),
necessaria perché la dashboard funzioni sotto il sotto-path di Ingress. Al
salto di versione di Hermes va controllato che `web/vite.config.ts` non sia
cambiato a monte (checklist in `CLAUDE.md`).

Per aggiungere un provider LLM non incluso nel build attuale: aggiungi il
suo extra a `HERMES_EXTRAS` nel Dockerfile e rifai il build — non si
installa nulla a runtime per gli altri toolset (`security.allow_lazy_installs: false`).

## Modello di sicurezza e limiti noti

- **La dashboard non ha una password propria** (deciso il 2026-09-25,
  scelta esplicita dell'utente di questo progetto): l'unica barriera per
  arrivarci è il login di Home Assistant, dietro cui sta il pannello
  Ingress. **Chiunque abbia un account HA** — anche non amministratore,
  anche un familiare con un account separato — che clicchi sul pannello
  Hermes ci entra senza altra password. Se questo non ti va bene, valuta
  di limitare chi ha un account su questa istanza di HA, non c'è un
  controllo aggiuntivo lato App.
- **Il `SUPERVISOR_TOKEN`** iniettato nel container (`homeassistant_api:
  true`) dà accesso completo all'API di Core. La restrizione "solo MCP"
  (`ha_access: mcp`) regge **solo finché l'agente non ha shell o accesso ai
  file** (`allow_shell_tools: false`): con quei toolset attivi, l'agente può
  leggere `/data/hermes/.env` e usare quel token per l'accesso REST
  completo, a prescindere da `ha_access`.
- **Il terminale/PTY integrato della dashboard** non si può disattivare da
  configurazione: chiunque arrivi al pannello (vedi punto sopra) ha una
  shell nel container, con gli stessi permessi dell'utente `hermes`.
- **La dashboard può rivelare il token di HA direttamente dalla UI**: la
  pagina "Keys/Env" elenca (redatte) e può rivelare in chiaro tutte le
  chiavi in `.env`, incluso `HERMES_HA_TOKEN` — non serve nemmeno aprire
  il terminale. Stesso confine di fiducia dei due punti sopra: chi arriva
  al pannello ha comunque accesso equivalente.
- **Le correzioni di `hermes-agent` arrivano solo con una nuova versione
  dell'App** (vedi "Aggiornare"): la versione è fissata e verificata sul
  commit, e l'update dalla dashboard è disattivato. In cambio, un tag
  spostato o manomesso a monte ferma il build invece di entrare.
- **Provider di memoria cloud esterni e il bridge WhatsApp della
  dashboard non funzionano** in questa App: gli endpoint che li
  installerebbero a runtime (`npm install`, script di setup con
  `shell=True`) sono bloccati da `nginx.conf`, perché bypassavano il
  blocco delle installazioni a runtime che protegge questa App.
- **Il token di HA finisce nei backup di Home Assistant**: `.env` vive in
  `/data/hermes`, che è dentro `/data` dell'App e quindi incluso nei backup
  standard di HA (solo la cache è esclusa via `backup_exclude`). Chi ha
  accesso ai backup ha accesso al token.
- **`/share` è condiviso con le altre App**: qualunque altra App con
  accesso a `/share` può leggere `/share/hermes-agent/address` (solo
  l'indirizzo IP interno del container, non un segreto, ma comunque
  informazione sulla topologia interna).

## Risoluzione problemi

- **Hai cambiato qualcosa nei canali (Channels) dalla dashboard e il bot non
  risponde più**: dopo ogni modifica ai canali — attivare/disattivare una
  piattaforma, cambiare il token del bot — **riavvia l'App**. Spegnere e
  riaccendere una piattaforma dalla dashboard smonta l'adattatore ma **non
  lo ricrea**: il gateway continua a girare e nei log sembra tutto a posto,
  ma nessuno sta più ascoltando i messaggi. Costato un'ora di debug il
  2026-09-26; per capire se il bot sta davvero ascoltando, il test sicuro è
  chiamare `getUpdates` sull'API di Telegram: se risponde `409 Conflict`
  significa che il gateway sta facendo polling (ed è quello che vuoi), se
  risponde `200` non sta ascoltando nessuno.
- **Il bot riceve ma resta muto**: controlla `TELEGRAM_ALLOWED_USERS` nel
  file `/data/hermes/.env` — è la lista (ID numerici separati da virgola)
  di chi può usare il bot; chi non è in lista viene ignorato. Nel log del
  gateway la riga `inbound message: ... user=... chat=<id>` mostra l'ID di
  chi ha scritto, ed è il modo più semplice per scoprirlo senza bot di
  terzi. `*` significa "chiunque": da evitare, perché il bot è
  raggiungibile da chiunque ne conosca il nome e quella lista è l'unica
  barriera.

- **Il pannello Ingress dà "404 not found"** (visto in un caso reale,
  corretto in `0.3.2`): la dashboard costruisce i suoi redirect (es. verso
  `/login`) leggendo l'header standard `X-Forwarded-Prefix`, ma il
  Supervisor di HA manda `X-Ingress-Path` (header proprietario). Senza
  tradurre l'uno nell'altro, il redirect usciva senza prefisso e il
  browser finiva fuori dal proxy di Ingress, su un path che HA Core non
  conosce. `nginx.conf` ora traduce `X-Ingress-Path` in
  `X-Forwarded-Prefix` per ogni richiesta. Se il 404 si ripresenta dopo
  un aggiornamento futuro della dashboard nativa, controlla prima se ha
  cambiato il nome dell'header che si aspetta.
- **Il watchdog riavvia l'App in loop subito dopo ogni avvio riuscito**
  (visto in un caso reale, corretto in `0.3.1`): controllare che
  `watchdog` in `config.yaml` non usi `[PORT:8099]` (si risolve solo per
  porte elencate in `ports:`, e 8099 non lo è) — deve essere la porta
  letterale `8099`.
- **Pagine come System o Chat restano vuote/bianche** sotto Ingress (visto
  in un caso reale, corretto in `0.5.2`): Vite fissa in fase di build
  l'URL assoluto `/assets/...` dentro i file `.js` delle pagine caricate
  "on demand", ignorando il prefisso di Ingress — il browser prova a
  scaricarli direttamente da Home Assistant Core invece che dal nostro
  addon, ottiene 404 e la pagina non si carica. `patches/vite-base-path-runtime.snippet`
  corregge questo calcolando l'URL a runtime dal browser invece che in
  fase di build. Se il problema si ripresenta dopo un aggiornamento
  dell'App, quasi certamente la nuova versione di Hermes ha modificato
  `web/vite.config.ts` in un punto che va in conflitto con la patch: va
  segnalato, non si risolve dal dispositivo.
- **Le risposte dell'agente arrivano tutte insieme invece che in
  streaming**: nginx disattiva già il buffering verso la dashboard
  (`proxy_buffering off` in `nginx.conf`). Se il problema persiste, prova
  ad aggiungere anche `add_header X-Accel-Buffering no;` nella stessa
  location — non ancora provato in questo run; se nemmeno questo basta, è
  probabilmente un limite del proxy Ingress del Supervisor stesso, non
  risolvibile da questa App.
- **L'agente non vede i tool di Home Assistant / errori MCP nei log**: il
  proxy `http://supervisor/core/api/mcp` potrebbe non gestire bene lo
  Streamable HTTP dell'MCP in alcune versioni del Supervisor. Non c'è
  ancora un fallback pronto in questa versione dell'App (pianificato:
  opzione `ha_token_override` per usare un long-lived token verso
  `http://homeassistant:8123/api/mcp` direttamente).
- **`PermissionError` nei log** riferiti a un path sotto `/opt`: agent o
  dashboard stanno cercando di scrivere in una directory d'installazione,
  che dalla 0.8.0 è tutta di sola lettura. Non rendere scrivibile `/opt`:
  va trovata la variabile d'ambiente giusta per ridirigere quel path sotto
  `/data`.
- **Con `ha_access: full` i tool `ha_*` non compaiono**: nel log dell'App,
  all'avvio, deve esserci `[render_config] plugin homeassistant: collegato`.
  Se dice "non è un link dell'App", in `/data/hermes/plugins/homeassistant`
  c'è una cartella installata a mano: toglila e riavvia l'App.
- **Build fallito, `nginx-light` non trovato**: dipende dalla revisione
  dell'immagine base HA OS; nel Dockerfile può essere sostituito con
  `nginx` (pacchetto completo, più pesante).
- **Build lento o fallito durante `uv sync`/`npm install`** per wheel o
  pacchetti mancanti su aarch64: il Dockerfile installa già
  `build-essential` nello stage di build per compilare da sorgente quando
  serve; se manca ancora qualcosa, il pacchetto va annotato in
  `CHANGELOG.md`.
- **`tools/hermes-ssh` non trova l'indirizzo**: verifica che l'App Hermes
  sia avviata (pubblica l'indirizzo solo dopo l'init) e che l'alias SSH
  nel tuo `~/.ssh/config` (default `ha`) punti davvero all'App "Advanced
  SSH & Web Terminal".
