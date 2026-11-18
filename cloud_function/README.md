# WhatsApp Webhook - Google Cloud Function

Cloud Function che riceve messaggi da WhatsApp Cloud API e li inoltra a un endpoint Windows configurato.

## Deploy su Google Cloud Functions

### Prerequisiti
- Google Cloud SDK installato e configurato
- Progetto Google Cloud attivo
- Billing abilitato sul progetto

### Comando di Deploy

```bash
gcloud functions deploy whatsapp_webhook \
  --runtime python310 \
  --trigger-http \
  --allow-unauthenticated \
  --region=europe-west1 \
  --entry-point whatsapp_webhook \
  --set-env-vars WINDOWS_ENDPOINT_URL="https://il-tuo-endpoint-windows.com/api/whatsapp" \
  --memory 256MB \
  --timeout 10s \
  --max-instances 10
```

**Nota:** Sostituisci `https://il-tuo-endpoint-windows.com/api/whatsapp` con l'URL reale del tuo endpoint Windows.

### Variabili d'Ambiente

- `WINDOWS_ENDPOINT_URL`: URL dell'endpoint Windows che riceverà i messaggi inoltrati. Se non configurato, la funzione logga un warning ma continua a funzionare.

## Configurazione Webhook su Meta Developer Console

1. **Accedi a Meta for Developers**: https://developers.facebook.com/
2. **Seleziona la tua App** e vai su "WhatsApp" > "Configuration"
3. **Webhook**:
   - **Callback URL**: Inserisci l'URL della Cloud Function (es. `https://europe-west1-PROJECT-ID.cloudfunctions.net/whatsapp_webhook`)
   - **Verify Token**: Scegli un token segreto (es. `your_secret_token_123`)
   - **Webhook Fields**: Seleziona `messages`
4. **Verifica il Webhook**: Meta invierà una richiesta GET per verificare il webhook. La Cloud Function deve gestire anche questa verifica (attualmente la funzione risponde sempre "ok", quindi potrebbe essere necessario aggiungere logica di verifica se richiesto da Meta).

### Token di Verifica (Opzionale)

Se Meta richiede la verifica del token, puoi aggiungere una variabile d'ambiente `VERIFY_TOKEN` e modificare la funzione per gestire le richieste GET di verifica.

## Test della Funzione

### Test con curl

```bash
# Test con payload minimo
curl -X POST https://europe-west1-PROJECT-ID.cloudfunctions.net/whatsapp_webhook \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "393471234567",
            "text": {
              "body": "Test messaggio WhatsApp"
            }
          }]
        }
      }]
    }]
  }'
```

### Test con payload completo (esempio reale)

```bash
curl -X POST https://europe-west1-PROJECT-ID.cloudfunctions.net/whatsapp_webhook \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
      "changes": [{
        "value": {
          "messaging_product": "whatsapp",
          "metadata": {
            "display_phone_number": "393471234567",
            "phone_number_id": "PHONE_NUMBER_ID"
          },
          "contacts": [{
            "profile": {
              "name": "Mario Rossi"
            },
            "wa_id": "393471234567"
          }],
          "messages": [{
            "from": "393471234567",
            "id": "wamid.XXX",
            "timestamp": "1234567890",
            "text": {
              "body": "Ciao, vorrei un preventivo per marmo Carrara"
            },
            "type": "text"
          }]
        },
        "field": "messages"
      }]
    }]
  }'
```

### Verifica Logs

```bash
# Visualizza logs in tempo reale
gcloud functions logs read whatsapp_webhook --limit 50 --region europe-west1

# Filtra per messaggi WhatsApp
gcloud functions logs read whatsapp_webhook --limit 50 --region europe-west1 | grep "\[WHATSAPP\]"
```

## Struttura Payload Inoltrato

La funzione inoltra al tuo endpoint Windows un JSON con questa struttura:

```json
{
  "from": "393471234567",
  "message": "Testo del messaggio ricevuto",
  "raw": {
    // JSON completo ricevuto da WhatsApp Cloud API
  }
}
```

## Troubleshooting

- **Errore 500**: Controlla i logs della Cloud Function per dettagli
- **Messaggi non inoltrati**: Verifica che `WINDOWS_ENDPOINT_URL` sia configurato correttamente e che l'endpoint Windows sia raggiungibile
- **Timeout**: Aumenta il timeout con `--timeout 30s` se necessario

## Estensioni Future

- Aggiungere autenticazione per l'endpoint Windows
- Implementare retry logic per inoltri falliti
- Aggiungere supporto per messaggi multimediali (immagini, documenti)
- Implementare rate limiting
- Aggiungere metriche e monitoring

