# Contribuire

Grazie per l'interesse. Questo repository contiene **solo** l'integrazione di
[Hermes Agent](https://github.com/NousResearch/hermes-agent) con Home
Assistant OS: il codice dell'agente non è qui, viene clonato in fase di
build. Se il problema che hai riguarda il comportamento dell'agente (modello,
skill, canali), la sede giusta è il repository di NousResearch.

## Prima di iniziare: leggi il contratto di progetto

[`CLAUDE.md`](CLAUDE.md) elenca le regole del progetto e **perché** esistono.
Non sono preferenze di stile: ognuna chiude un problema concreto, e quasi
tutte nascono dallo stesso scarto — Hermes Agent è pensato per la postazione
di uno sviluppatore (servito dalla radice di un dominio, raggiungibile in
loopback, libero di scrivere e installare), Home Assistant è l'opposto.

Il [`CHANGELOG`](hermes_agent/CHANGELOG.md) documenta la **causa** di ogni
correzione, non solo cosa è cambiato. Prima di rimettere mano a nginx, ai
servizi s6 o al build, leggilo: parecchie soluzioni apparentemente ovvie sono
già state provate e scartate, con la spiegazione.

## La convenzione più importante

> Ogni affermazione "funziona" va accompagnata da **come** è stata
> verificata. Se non è verificabile senza il dispositivo, dirlo
> esplicitamente.

Questa regola nasce da un errore reale: una correzione applicata su
un'ipotesi non verificata si è rivelata completamente inerte, e a scoprirlo
è stato solo il log diagnostico aggiunto insieme. Nelle pull request,
scrivi cosa hai eseguito e cosa hai osservato — non "testato", ma "ho
lanciato X e ho visto Y".

## Verifiche locali

```bash
# test di render_config.py (non richiedono Docker)
python -m pytest tests/

# script dei servizi
shellcheck hermes_agent/rootfs/etc/s6-overlay/scripts/init-hermes.sh

# Dockerfile
hadolint hermes_agent/Dockerfile

# configurazione nginx, con lo stesso pacchetto dell'immagine
docker run --rm -v "$PWD/hermes_agent/rootfs/etc/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" \
  debian:bookworm-slim sh -c 'apt-get update -qq && apt-get install -y -qq nginx-light && nginx -t'

# build completa (su x86 richiede QEMU per aarch64)
docker build --platform linux/arm64 -t hermes-ha:test hermes_agent/
```

Alcuni comportamenti si possono osservare solo sul dispositivo: il prefisso
di Ingress, il token del Supervisor che cambia a ogni avvio, la supervisione
s6. Se una modifica li riguarda, dichiara che la verifica è avvenuta (o non è
avvenuta) su hardware reale.

## Modifiche che richiedono particolare attenzione

- **`nginx.conf`** — regge Ingress: traduzione di `X-Ingress-Path`,
  riscrittura di `Host` e `Origin` per i WebSocket, allow-list al
  Supervisor. Ogni riga ha un commento che spiega quale sintomo previene.
  Non aggiungere il prefisso di Ingress all'access log: contiene il token
  di sessione.
- **Servizi s6** (`rootfs/etc/s6-overlay/`) — il gateway è un servizio
  *statico* per una ragione precisa: la registrazione dinamica richiederebbe
  di rendere scrivibile la scandir del supervisore, cioè una scorciatoia da
  utente non privilegiato a root.
- **`render_config.py`** — applica i vincoli al `config.yaml` di Hermes a
  ogni avvio. Deve restare **idempotente** e **non deve toccare** le chiavi
  che non gestisce (modello, provider, preferenze salvate dall'utente). I
  test coprono questa proprietà: aggiungine se introduci una chiave nuova.
- **Opzioni del manifest** — cambiare un default cambia il comportamento
  delle installazioni esistenti al primo aggiornamento. Se il default ha
  implicazioni di sicurezza, discutine in una issue prima di aprire la PR.

## Pull request

- Un cambiamento per PR, con una descrizione che dica **quale sintomo**
  risolve.
- Aggiorna [`CHANGELOG.md`](hermes_agent/CHANGELOG.md) spiegando la causa,
  e alza la `version` in `config.yaml` (il Supervisor mostra
  l'aggiornamento solo se la versione cambia).
- Se la modifica si vede dall'utente, aggiorna anche
  [`DOCS.md`](hermes_agent/DOCS.md): è la pagina mostrata dentro Home
  Assistant.
- Testi rivolti all'utente in italiano (con `translations/en.yaml`
  allineato).

## Sicurezza

Per vulnerabilità sfruttabili non aprire una issue pubblica: vedi
[`SECURITY.md`](SECURITY.md).
