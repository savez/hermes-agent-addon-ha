# Linee guida del progetto — hermes-ha-app

Add-on locale per Home Assistant OS che esegue
[Hermes Agent](https://github.com/NousResearch/hermes-agent) con la sua
dashboard nativa come pannello Ingress e una CLI raggiungibile via SSH.
Target di riferimento: Raspberry Pi 5 (aarch64) con HA OS, immagine
costruita dal Supervisor sul dispositivo.

Questo file è il contratto di progetto: spiega **cosa** è stato deciso e
soprattutto **perché**. Serve a chi contribuisce e agli assistenti di
programmazione che lavorano su questo repo. Le modifiche utente sono
documentate in [`hermes_agent/DOCS.md`](hermes_agent/DOCS.md), la storia
delle correzioni in [`hermes_agent/CHANGELOG.md`](hermes_agent/CHANGELOG.md).

## Principio di fondo

Hermes Agent è nato per la postazione di uno sviluppatore: si aspetta di
essere servito dalla radice di un dominio, raggiungibile in loopback, libero
di scrivere dove serve e di installare dipendenze al primo uso. Home
Assistant è l'opposto: proxy su sotto-path, processo non privilegiato,
immagine immutabile. **Quasi tutti i problemi di questo add-on nascono da
quello scarto**, e il `CHANGELOG` è in buona parte il diario di quegli
scontri. Prima di dare la colpa a Ingress o a s6, cerca l'assunzione
implicita.

## Regole

Ognuna chiude un problema concreto. Non cambiarle senza capire cosa
proteggono; dove una regola è un compromesso, il compromesso è dichiarato.

1. **Build sempre locale, nessuna immagine precompilata.** Niente chiave
   `image:` in `config.yaml`: il Supervisor costruisce l'immagine dal
   `Dockerfile` sul dispositivo. Niente `curl | sh`.
2. **`hermes-agent` non è pinnato a un commit.** Il build clona l'**ultimo
   tag di release** risolto al momento della costruzione. È un compromesso
   dichiarato: si ottengono le correzioni upstream senza intervento, si
   accetta che un tag manomesso entrerebbe al primo rebuild senza revisione.
   Chi preferisce il controllo può fissare `HERMES_REF` a un tag e
   verificarne il commit.
3. **Il canale di aggiornamento è `stable`**, imposto da `render_config.py`.
   Per un'installazione da sorgente il default di Hermes è seguire il branch
   di sviluppo: un Update reale ha portato il checkout migliaia di commit
   dopo l'ultimo tag, rompendo l'assistente. Non rimuovere quella chiave.
4. **Agent, dashboard e sessioni SSH girano come utente non privilegiato**
   (`hermes`, uid 1000), mai root. `/opt` è di root e non scrivibile,
   **eccetto `/opt/hermes-agent`**, che deve restare scrivibile perché
   l'aggiornamento in-place di Hermes lavora lì. Non estendere l'eccezione.
5. **L'unico ingresso è nginx sulla porta di Ingress**, con allow-list al
   solo Supervisor (`allow 172.30.32.2; allow 127.0.0.1; deny all;`). La
   dashboard ascolta esclusivamente su `127.0.0.1`. Ingress è preferito a una
   porta pubblica perché è l'unico modo di avere l'identità dell'utente di
   Home Assistant a monte dell'add-on.
6. **nginx tocca solo ciò che serve a far funzionare Ingress**: rimuove
   l'header di frame-blocking, traduce `X-Ingress-Path` nello standard
   `X-Forwarded-Prefix`, e riscrive `Host` e `Origin` verso `127.0.0.1:8788`.
   Quest'ultimo non è cosmetico: la dashboard ripete un controllo
   anti-DNS-rebinding sull'`Origin` per le sole rotte WebSocket, dove il
   middleware HTTP non gira, e senza la riscrittura terminale e pannello
   laterale vengono rifiutati con 403. La Content-Security-Policy non si
   tocca. L'access log **non** deve contenere il prefisso di Ingress, che
   include il token di sessione.
7. **La dashboard non ha una password propria**: l'unica barriera è il login
   di Home Assistant, dietro cui sta il pannello Ingress. È il compromesso
   più importante da conoscere prima di installare: chi ha un account su
   quell'istanza di Home Assistant, **anche non amministratore**, arriva a
   una shell nel container, al token di HA e alle chiavi API dei provider.
   Se l'istanza ha più utenti, valuta prima `panel_admin` e la separazione
   degli account.
8. **Default prudenti sull'accesso a Home Assistant**: `ha_access: mcp`
   (solo le entità esposte ad Assist, solo intent) e
   `allow_shell_tools: false`. Con i toolset `terminal`, `code_execution` e
   `file` disattivati l'agente non può leggere il token di HA da
   `/data/hermes/.env`. La modalità `full` aggiunge l'API REST completa di
   Core — qualsiasi servizio, qualsiasi entità — e va scelta sapendolo.
9. **Nessuna installazione di pacchetti a runtime**
   (`security.allow_lazy_installs: false`, `HERMES_DISABLE_LAZY_INSTALLS=1`).
   È il prezzo dell'immagine immutabile: i provider si aggiungono con l'ARG
   `HERMES_EXTRAS` e un rebuild. Diverse funzioni di Hermes contano invece
   sul "lazy install" (i canali di messaggistica sono nell'extra `messaging`,
   escluso da `all` a monte): se qualcosa risulta "requirements not met", la
   risposta è un extra in più, non allentare questa regola.
10. **Il token di HA non compare nei file di configurazione**: l'MCP usa
    `${HERMES_HA_TOKEN}`, che Hermes interpola dall'ambiente leggendo
    `/data/hermes/.env`. Il token del Supervisor cambia a ogni avvio, quindi
    `init-hermes.sh` lo riscrive — in tutti i profili, non solo nel
    principale.
11. **sshd: solo chiave, solo utente `hermes`**, `authorized_keys` fuori da
    `/data/hermes` e di proprietà di root; unico port-forwarding permesso
    `127.0.0.1:8788`. Senza chiavi configurate, sshd non parte affatto.
12. **I servizi sono gestiti da s6-overlay** (`rootfs/etc/s6-overlay/s6-rc.d`),
    non da loop bash in background. Il gateway è il servizio **statico**
    `main-hermes`: Hermes proverebbe a registrarsi da sé come servizio
    dinamico scrivendo nella scandir del supervisore, che è di root —
    aprirla sarebbe una scorciatoia da utente non privilegiato a root, perché
    s6 esegue come root qualunque servizio trovi lì. Il servizio statico deve
    esportare `HERMES_S6_SUPERVISED_CHILD=1`, altrimenti `gateway run`
    rimbalza proprio su quella registrazione. Conseguenza: senza lo slot
    dinamico il controllo preliminare di Hermes si rifiuta di multiplexare i
    profili, per questo `render_config.py` dichiara
    `gateway.multiplex_profiles: true` — lecito qui perché il gateway è
    garantito unico.

## Convenzioni

- Testi rivolti all'utente (log, `DOCS.md`, traduzioni `it`) in italiano;
  identificatori, nomi di file e commenti nel codice in italiano o inglese
  purché coerenti col file.
- Script dei servizi: shebang `#!/command/with-contenv bashio`.
- I permessi di esecuzione si impostano nel `Dockerfile`: non fare
  affidamento sui bit dei file sorgente, si perdono copiando via Samba.
- **Ogni affermazione "funziona" va accompagnata da come è stata
  verificata.** Se non è verificabile senza il dispositivo, dirlo. Questa
  regola nasce da un fix applicato su un'ipotesi non verificata che si è
  rivelato completamente inerte: il log diagnostico aggiunto insieme è ciò
  che ha permesso di scoprirlo.
