# Modello di sicurezza

Questo add-on fa girare un agente AI con accesso a Home Assistant dentro la
propria rete domestica. Vale la pena leggere questa pagina **prima** di
installarlo: alcune scelte sono compromessi deliberati, non dimenticanze.

## Cosa protegge l'add-on

| Misura | Come |
|---|---|
| Un solo ingresso | La dashboard ascolta esclusivamente su `127.0.0.1`. L'unico punto d'accesso è nginx sulla porta di Ingress, con allow-list al solo Supervisor (`allow 172.30.32.2; allow 127.0.0.1; deny all;`). |
| Nessun processo privilegiato | Agent, dashboard, gateway e sessioni SSH girano come utente `hermes` (uid 1000). `/opt` è di root e non scrivibile, con l'unica eccezione di `/opt/hermes-agent`, necessaria all'aggiornamento in-place. |
| Immagine costruita in locale | Nessuna chiave `image:` nel manifest: il Supervisor costruisce dal `Dockerfile`. Nessun `curl \| sh`, nessun binario scaricato senza verifica. |
| Nessuna installazione a runtime | `security.allow_lazy_installs: false` e `HERMES_DISABLE_LAZY_INSTALLS=1`. I provider si aggiungono con un extra nel build. Due endpoint della dashboard che aggiravano questo vincolo sono bloccati a livello di reverse proxy. |
| Segreti fuori dai file di configurazione | Il token di Home Assistant è interpolato dall'ambiente (`${HERMES_HA_TOKEN}`, letto da `/data/hermes/.env`), mai scritto nel `config.yaml` di Hermes. |
| Default prudenti sull'accesso a HA | `ha_access: mcp` espone solo le entità che dichiari ad Assist, in sola modalità intent. `allow_shell_tools: false` disattiva i toolset `terminal`, `code_execution` e `file`, senza i quali l'agente non può leggere il token di HA dal disco. |
| SSH solo a chiave | Mai password, mai `root`, `authorized_keys` di proprietà di root e fuori da `/data/hermes` (l'agente non può autorizzarsi da sé). Unico port-forwarding permesso: `127.0.0.1:8788`. Senza chiavi configurate, sshd non parte. |
| Log senza segreti | L'access log di nginx non registra il prefisso di Ingress, che contiene il token di sessione. |

## Compromessi deliberati

Questi sono i punti da valutare consapevolmente. Sono i **default attuali**
del progetto, scelti per un'istanza a uso personale.

**1. La dashboard non ha una password propria.** L'unica barriera è il login
di Home Assistant, dietro cui sta il pannello Ingress. Conseguenza: chi ha
un account su quell'istanza — **anche non amministratore** — arriva a una
shell nel container, al token di Home Assistant e alle chiavi API dei
provider configurati. Su un'istanza a uso familiare o condiviso, valuta la
separazione degli account e l'opzione `panel_admin`.

**2. SSH è pubblicato sulla rete locale** (porta 2222) quando aggiungi una
chiave. È comodo per diagnosticare, ma è una superficie in più: un errore di
configurazione della rete domestica la espone. Per spegnerlo basta svuotare
`ssh_authorized_keys`; l'alternativa prudente è passare da un jump host
(vedi `hermes_agent/DOCS.md`).

**3. Hermes Agent non è pinnato a un commit verificato.** Ogni build clona
l'ultimo tag di release: si ottengono le correzioni upstream senza
intervento, ma un tag manomesso entrerebbe al primo rebuild senza revisione.
Chi preferisce il controllo può fissare il riferimento nel `Dockerfile` e
verificarne il commit.

**4. L'aggiornamento in-place dalla dashboard è abilitato.** Il codice
dell'agente può cambiare senza passare da un rebuild, su richiesta di chi
arriva al pannello. Il canale è forzato su `stable` proprio per limitare il
danno: senza quella impostazione il default di Hermes segue il branch di
sviluppo, e un solo click può portare il codice migliaia di commit oltre
l'ultima release — è già accaduto.

**5. `allow_shell_tools: true` dà all'agente una shell nel container.** È
disattivato di default. Attivandolo, l'agente può leggere `/data/hermes/.env`
e quindi il token di Home Assistant e le chiavi dei provider. Da tenere
presente soprattutto se l'agente riceve messaggi da canali esterni: il
contenuto di un messaggio è input non fidato che l'agente interpreta.

## Cosa NON è protetto

- **Prompt injection.** Un agente che legge pagine web, email o messaggi può
  essere indotto a compiere azioni. I toolset disattivati per default e
  l'esposizione minima delle entità limitano il danno, non lo escludono.
- **L'host, oltre il container.** L'add-on non chiede `hassio_api` né
  privilegi sull'host. Non disattivare la *protection mode* del Supervisor
  per comodità di accesso: vale per tutti i container, non solo per questo.
- **I backup.** Lo stato in `/data` include `.env` con i token e rientra nei
  backup standard di Home Assistant. Chi ha accesso ai backup ha accesso a
  quei segreti.
- **La rete locale.** Nulla qui difende da chi è già sulla LAN, oltre al
  login di Home Assistant.

## Segnalare una vulnerabilità

Apri una issue per problemi di configurazione o documentazione. Per una
vulnerabilità sfruttabile, **non aprire una issue pubblica**: usa la
segnalazione privata di GitHub (*Security → Report a vulnerability*) così che
possa essere corretta prima di essere resa nota.

Le vulnerabilità di **Hermes Agent** vanno segnalate a
[NousResearch](https://github.com/NousResearch/hermes-agent), non qui: questo
repository contiene solo l'integrazione con Home Assistant.
