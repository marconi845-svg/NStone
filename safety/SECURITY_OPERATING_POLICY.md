# Security Operating Policy

Version: 1.0  
Owner: CTO / Security Owner  
Scope: backend FastAPI, desktop app, Rust core, integrazioni esterne  
Environments: dev, staging, prod

## 1) Regole non negoziabili

- Segreti (api_key, password, token) mai in file versionati.
- Segreti solo via variabili ambiente o secret manager.
- Log senza dati sensibili in chiaro.
- Ambienti separati con credenziali distinte.
- Nessun rilascio senza checklist sicurezza completa.

## 2) Rotazione credenziali

- Token critici: rotazione ogni 30-60 giorni.
- Password applicative: rotazione ogni 60-90 giorni.
- Rotazione immediata in caso di sospetto leak, cambio personale, incidente.
- Ogni segreto deve avere owner, ultima rotazione, scadenza.

## 3) Logging e redazione dati

Vietato loggare:
- password, token, api_key
- Authorization header e cookie di sessione
- email e telefono completi

Obbligo masking:
- email: m***@dominio
- telefono: *******123

## 4) Separazione ambienti

- Segreti diversi per dev/staging/prod.
- Config ambiente non riusabile cross-env.
- Promozione in prod solo dopo validazione in staging.

## 5) Security gate release (Go/No-Go)

Release consentita solo se:
- nessun segreto in repo
- redaction log attiva
- configurazione ambiente corretta
- health e metriche operative
- test minimi superati
- rollback plan disponibile

Se un punto e' KO => No-Go.

## 6) Runbook incidente segreti

T0-T5:
1. Identifica segreto compromesso.
2. Revoca immediata.
3. Genera nuovo segreto.

T5-T15:
4. Aggiorna runtime e redeploy.
5. Verifica health e funzionalita'.

T15-T30:
6. Audit accessi/log.
7. Post-mortem.
8. Azioni preventive.

## 7) Ruoli (RACI)

- CTO/Security Owner: approva policy e chiusura incidenti.
- Service Owner: rotazione segreti del servizio.
- Release Owner: applica Go/No-Go.
- Backup Owner: copertura in assenza owner principale.

## 8) KPI minimi

- Segreti in repo: 0
- Segreti scaduti: 0
- Release con gate completo: 100%
- Tempo revoca+rotazione incidente: < 30 min
- Violazioni redaction log: 0
