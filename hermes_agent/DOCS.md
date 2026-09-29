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

`hermes-agent` **non è pinnato a una versione fissa** (scelta deliberata,
vedi "Aggiornare" sotto): ogni build prende l'ultimo tag disponibile su
GitHub, e il pulsante "Update" della dashboard è abilitato. Questo è
diverso da un'immagine davvero immutabile — leggi "Modello di sicurezza"
prima di installare se questo ti preoccupa.

**La dashboard non ha una propria password** (scelta deliberata, vedi
"Modello di sicurezza" sotto): l'unica barriera per arrivarci è il login
di Home Assistant stesso, dietro cui sta il pannello Ingress.

## Requisiti

- Home Assistant OS su un host **aarch64** (verificato il target Raspberry
  Pi 5; altre board aarch64 dovrebbero funzionare, non testate).
- Spazio disco: l'immagine buildata pesa **~850 MB** (misurato con
  `docker inspect` su Apple Silicon via Colima, build nativo arm64). Il
  peso viene soprattutto da Node.js/npm, che servono a costruire il
  frontend della dashboard e restano nell'immagine perché un
  aggiornamento in-place lo ricostruisce. Il clone di `hermes-agent` usa
  `--filter=tree:0`: scarica tutta la storia dei commit — necessaria
  perché l'aggiornamento in-place fa `git fetch` lì dentro — senza gli
  alberi delle versioni passate, il che da solo evita circa 900 MB.
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
   - `full`: l'agente ha accesso REST completo a Core, **indipendentemente**
     da cosa hai esposto ad Assist — usalo solo se ti serve davvero
     l'automazione completa e ne accetti il rischio;
   - `none`: l'agente non vede nulla di HA.

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

`hermes-agent` non è pinnato a un commit verificato: ci sono **due modi
distinti e indipendenti** per aggiornarlo, con garanzie diverse.

> [!IMPORTANT]
> L'add-on forza il canale di aggiornamento su **`stable`**. Non toglierlo:
> per un'installazione da sorgente il default di Hermes è seguire il branch
> di **sviluppo**, e un solo click su "Update" può portare il codice
> migliaia di commit oltre l'ultima release. È successo davvero, e
> l'assistente non è più partito.

**1. Rebuild dell'App (Store → ⋮ → "Controlla aggiornamenti" → Aggiorna)**
— il Dockerfile clona sempre l'**ultimo tag disponibile** su GitHub al
momento del build, senza verificare un commit atteso. Non c'è più un passo
manuale di trovare/verificare un SHA: ogni rebuild prende semplicemente
quello che sta in cima ai tag di `NousResearch/hermes-agent` in quel
momento. Il tag scelto viene stampato nel log del build (visibile in
Impostazioni → Sistema → Log → Supervisor), quindi puoi sempre controllare
dopo cosa è stato installato.

**2. Pulsante "Update" dentro la dashboard stessa** — applica
l'aggiornamento **sul momento**, senza rebuild Docker, senza che tu clicchi
nulla in HA e **senza che compaia nulla nei log del Supervisor**. Fa `git
pull` + reinstall dentro `/opt/hermes-agent` (per questo quella cartella,
solo quella, è scrivibile dall'utente `hermes` — vedi "Modello di
sicurezza"). Il frontend viene ricostruito automaticamente se serve (Node/
npm restano nell'immagine apposta per questo).

**Conseguenza pratica**: con la via 2, "quale versione di hermes-agent sta
girando" non è più qualcosa che puoi dedurre dal Dockerfile o dal log del
Supervisor — può essere cambiata da chiunque arrivi al pannello Ingress
(vedi "Modello di sicurezza": non serve nemmeno una password dedicata),
in qualunque momento. Se qualcosa si rompe dopo un aggiornamento e non hai
appena fatto un rebuild da HA, il primo posto da controllare è la
dashboard stessa (pagina di stato/aggiornamento), non i log dell'App.

**Se un aggiornamento rompe qualcosa**, il rimedio è **ricostruire
l'add-on** (Store → ⋮ → Controlla aggiornamenti → Aggiorna, oppure
Ricostruisci). Il build riclona l'ultimo tag di release e riapplica le
patch al frontend, **senza toccare `/data`**: profili, memoria, cron,
configurazioni e credenziali restano. È la via di ritorno da uno stato
incoerente.

Nota per chi contribuisce: questo add-on applica al frontend di Hermes una
piccola patch in fase di build (`patches/vite-base-path-runtime.snippet`),
necessaria perché la dashboard funzioni sotto il sotto-path di Ingress.
Non è committata nel checkout: l'aggiornamento in-place di Hermes la mette
da parte in `git stash` e la ripristina da sé, ma se upstream tocca lo
stesso file il ripristino va in conflitto e la patch resta parcheggiata.
In quel caso le pagine interne della dashboard tornano bianche al primo
rebuild del frontend, e si risolve ricostruendo l'add-on.

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
- **L'aggiornamento di `hermes-agent` non è più garantito dal build
  Docker** (vedi "Aggiornare"): il pulsante "Update" della dashboard è
  volutamente abilitato, e ogni rebuild prende l'ultimo tag disponibile
  senza verificarne il commit. Un tag manomesso o una release compromessa
  upstream entrerebbero senza revisione. Scelta esplicita dell'utente di
  questo progetto, non un default.
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
  fase di build. Se il problema si ripresenta dopo un `hermes update` (il
  pulsante della dashboard): quasi certamente una futura release upstream
  ha modificato proprio `web/vite.config.ts` in un punto che va in
  conflitto con la nostra patch non committata — `hermes update` in quel
  caso aggiorna comunque il codice ma lascia la patch da parte (in
  `git stash`, la trovi con `git stash list` dentro `/opt/hermes-agent`);
  va ripristinata rifacendo un rebuild Docker completo dell'App (non basta
  premere di nuovo "Update").
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
- **`PermissionError` nei log** riferiti a un path sotto `/opt` diverso da
  `/opt/hermes-agent`: agent o dashboard stanno cercando di scrivere in
  una directory d'installazione non pensata per essere scrivibile. Non
  estendere i permessi scrivibili oltre `/opt/hermes-agent`: va trovata la
  variabile d'ambiente giusta per ridirigere quel path sotto `/data`.
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
