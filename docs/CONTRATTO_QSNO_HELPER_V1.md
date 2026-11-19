# Contratto QSNO ↔ helper — proposta v1

Data: **19 novembre 2026**. Destinatari: A (orchestratore e SDN), B (helper e collegamenti TLS).

**Stato:** proposta operativa da rivedere insieme. Il servizio helper persistente descritto qui deve ancora essere implementato. `crypto/qsno_tls.py probe` funziona già, ma apre e chiude una singola connessione: il suo JSON non è una conferma di migrazione del traffico continuativo. Gli [esempi JSON](../contracts/qsno-helper-v1.examples.json) sono dati di esempio, non risultati sperimentali.

## 1. Che cosa concordiamo

QSNO decide **quale profilo richiedere**. L'helper, eseguito nel client IoT o drone, gestisce **la connessione TLS e i messaggi applicativi**. La regola SDN resta responsabilità di A.

Il contratto permette ad A di scrivere subito il chiamante e un helper simulato, mentre B realizza il servizio vero. Una risposta simulata verifica la logica dell'orchestratore; la prova TLS/Mininet reale resta un controllo successivo.

| Operazione | Domanda di QSNO | Compito dell'helper |
|---|---|---|
| `get_status` | «Che cosa stai facendo?» | Restituire stato e capacità configurate; nessun cambio di connessione |
| `set_profile` | «Usa questo profilo per questa policy» | Interrompere il vecchio collegamento se necessario, aprire/verificare quello richiesto e rispondere |
| `stop` | «Smetti di trasmettere» | Fermare il traffico e chiudere il collegamento; il servizio di controllo resta attivo |

L'helper non decide il rischio, non sceglie un profilo alternativo e non invia comandi a Ryu.

## 2. Trasporto proposto per il laboratorio

- Un socket Unix con nome nel filesystem per ciascun helper: `/run/qsno/<run_id>/iot.sock` e `/run/qsno/<run_id>/drone.sock`.
- Il processo di avvio crea la directory della prova con permessi `0700`; socket `0600`. QSNO e helper vengono eseguiti con identità autorizzate ad accedervi; nella prima prova Mininet sono processi amministrati da root.
- Apre la connessione QSNO. Una connessione di controllo trasporta **una richiesta e una risposta**, ciascuna su una riga JSON UTF-8 terminata da `\n`. Poi viene chiusa.
- Massimo **16 384 byte per riga**, incluso `\n`. Rifiutare JSON con chiavi duplicate, valori non finiti e campi non previsti dalla v1. Per UTF-8/JSON non decodificabile, riga troppo lunga o incompleta: chiudere senza applicare comandi; il chiamante registra un errore di protocollo.
- Il listener di controllo può gestire `get_status` durante una transizione. L'helper accetta una sola operazione che modifica lo stato alla volta; un'altra riceve `busy` e non cambia lo stato.
- Una volta accettato, il comando termina entro il proprio timeout anche se QSNO chiude il socket: la perdita della risposta non provoca un ritorno al classico.

Il socket è il canale di gestione locale della VM e non attraversa i link dell'esperimento. La comunicazione applicativa TLS continua invece a passare nella rete Mininet. Va verificato il collegamento tramite socket con i processi nei rispettivi namespace durante la prima integrazione. Non si espone un nuovo servizio HTTP sulla rete.

## 3. Profili e configurazione

| Valore nel contratto | Valore nella CLI esistente | Gruppo TLS atteso | Servizio del laboratorio |
|---|---|---|---|
| `CLASSIC` | `classic` | `X25519` | `10.0.0.1:4433` |
| `HYBRID` | `hybrid` | `X25519MLKEM768` | `10.0.0.1:4434` |

Entrambi richiedono TLS 1.3, `TLS_AES_256_GCM_SHA384` e verifica del certificato rispetto a CA di laboratorio e nome `qsno-server`. L'autenticazione resta ECDSA.

L'helper riceve all'avvio `run_id`, `target_id`, percorsi di OpenSSL/CA, indirizzo del server e configurazione dei profili. QSNO non trasmette percorsi di chiavi, comandi shell o algoritmi arbitrari nei messaggi. `supported_profiles` dichiara la configurazione disponibile e non garantisce la raggiungibilità del server.

## 4. Richieste

Campi comuni obbligatori:

| Campo | Tipo e significato |
|---|---|
| `schema_version` | Intero, esattamente `1` |
| `message_type` | Stringa, esattamente `request` |
| `request_id` | Identificativo della singola richiesta; collega richiesta e risposta |
| `run_id` | Identificativo della prova, fissato all'avvio di QSNO e helper |
| `target_id` | Esattamente `iot` oppure `drone`; deve coincidere con l'helper contattato |
| `action` | `get_status`, `set_profile` oppure `stop` |

`request_id`, `run_id` e `policy_id` sono stringhe di 1–64 caratteri appartenenti a `A–Z`, `a–z`, `0–9`, `.`, `_`, `-`. Ogni nuova lettura di stato usa un nuovo `request_id`.

Solo `set_profile` e `stop` aggiungono obbligatoriamente:

| Campo | Tipo e significato |
|---|---|
| `policy_id` | Identificativo scelto da QSNO per collegare decisione, comando e log |
| `policy_version` | Intero positivo, crescente per quel target nella stessa prova |
| `timeout_ms` | Intero fra `100` e `30000`; limite dell'intera operazione nell'helper |
| `reason` | Stringa di 1–256 caratteri per spiegare il comando nei log |

Solo `set_profile` aggiunge `required_profile`, obbligatoriamente `CLASSIC` oppure `HYBRID`. `get_status` non contiene campi di policy; `stop` non contiene `required_profile`.

Esempio: QSNO richiede l'ibrido all'IoT.

```json
{
  "schema_version": 1,
  "message_type": "request",
  "request_id": "req-iot-002",
  "run_id": "demo-001",
  "target_id": "iot",
  "action": "set_profile",
  "policy_id": "policy-iot-002",
  "policy_version": 2,
  "required_profile": "HYBRID",
  "timeout_ms": 10000,
  "reason": "Evento di rischio alto simulato"
}
```

Qui i JSON sono indentati per leggerli; sul socket ciascun oggetto occupa una sola riga.

## 5. Risposta

Ogni risposta a una richiesta riconoscibile contiene:

| Campo | Significato |
|---|---|
| `schema_version`, `message_type` | `1` e `response` |
| `request_id`, `run_id`, `target_id`, `action` | Copia dei corrispondenti campi della richiesta |
| `ok` | Booleano: la richiesta è stata eseguita con successo |
| `state` | Stato corrente o stato al completamento della richiesta, descritto sotto |
| `duration_ms` | Numero finito ≥ 0, misurato con orologio monotono dall'helper; durata di gestione del comando, non tempo del solo handshake |
| `error` | `null` se `ok=true`; altrimenti oggetto con `code` e `detail` |

Campi obbligatori di `state`:

| Campo | Tipo / valori |
|---|---|
| `status` | `IDLE`, `TRANSITION`, `CLASSIC_ACTIVE`, `HYBRID_ACTIVE`, `BLOCKED` |
| `policy_id` | Ultima policy accettata, oppure `null` all'avvio |
| `policy_version` | Versione dell'ultima policy accettata; `0` all'avvio |
| `desired_profile` | `CLASSIC`, `HYBRID` oppure `null` |
| `observed_profile` | `CLASSIC`/`HYBRID` solo per una connessione attiva verificata; altrimenti `null` |
| `observed_group` | `X25519`/`X25519MLKEM768` per la connessione attiva; altrimenti `null` |
| `certificate_ok` | Booleano, verifica del certificato della connessione attiva |
| `application_ack` | Booleano, ricevuta risposta applicativa valida sulla connessione attiva |
| `connection_id` | Identificativo della connessione gestita dall'helper, oppure `null` |
| `last_acked_seq` | Ultimo numero di messaggio confermato nel corso della prova, oppure `null` se nessuno; non viene azzerato dalla riconnessione |
| `supported_profiles` | Lista senza duplicati dei profili configurati, sottoinsieme di `CLASSIC`, `HYBRID` |

`state.policy_id` e `state.policy_version` indicano **la policy effettivamente accettata dall'helper**, non una copia automatica della richiesta. In caso di comando rifiutato rimangono quelli precedenti.

Esempio di risposta dopo una transizione riuscita:

```json
{
  "schema_version": 1,
  "message_type": "response",
  "request_id": "req-iot-002",
  "run_id": "demo-001",
  "target_id": "iot",
  "action": "set_profile",
  "ok": true,
  "state": {
    "status": "HYBRID_ACTIVE",
    "policy_id": "policy-iot-002",
    "policy_version": 2,
    "desired_profile": "HYBRID",
    "observed_profile": "HYBRID",
    "observed_group": "X25519MLKEM768",
    "certificate_ok": true,
    "application_ack": true,
    "connection_id": "conn-iot-002",
    "last_acked_seq": 42,
    "supported_profiles": ["CLASSIC", "HYBRID"]
  },
  "duration_ms": 185.4,
  "error": null
}
```

Il valore temporale e il numero di messaggio sono inventati per illustrare il formato.

## 6. Quando dichiarare il successo

Per `set_profile`, `ok=true` richiede tutte queste condizioni:

1. La policy della risposta coincide con ID e versione richiesti.
2. Il gruppo **osservato** coincide con quello del profilo richiesto, il protocollo è TLS 1.3 e la cipher suite è quella fissata.
3. Certificato, catena rispetto alla CA e nome del server sono verificati.
4. Sulla connessione viene ricevuta una risposta al messaggio applicativo di verifica, con il numero di sequenza atteso.
5. La connessione rimane gestita dall'helper per il traffico successivo: non è stata chiusa dopo una singola prova.

Se il profilo è già attivo e verificato, non occorre riaprire TLS: serve comunque una nuova conferma applicativa entro il timeout e l'aggiornamento della policy accettata. Non registrare questo caso come nuovo handshake. In una transizione i numeri di sequenza restano crescenti; un messaggio non confermato viene registrato come tale, senza ripresentarlo con lo stesso numero come se fosse nuovo.

`get_status` restituisce l'ultima situazione conosciuta, senza eseguire un nuovo handshake o imporre una nuova verifica. Può quindi avere `ok=true` e `state.status=BLOCKED`: è riuscita la lettura dello stato, non il collegamento. I campi relativi alla connessione attiva sono azzerati quando l'helper ne rileva la caduta; `last_acked_seq` rimane storico.

Per `stop`, il successo significa traffico fermato e collegamento chiuso: stato `IDLE`, profili desiderato/osservato `null`, gruppo e `connection_id` `null`, verifiche booleane `false`. Restano ID/versione della policy di stop e ultimo messaggio confermato.

## 7. Ordine, duplicati e fallimenti

- QSNO invia al massimo una modifica alla volta per target. `policy_version` deve superare l'ultima accettata; una versione precedente o uguale con un nuovo `request_id` produce `stale_policy`, senza effetti.
- Un nuovo `set_profile` valido viene accettato registrando policy e versione. L'helper passa a `TRANSITION`, interrompe l'uso del collegamento precedente e cerca il profilo richiesto. Se quest'ultimo è già attivo, si applica la verifica senza riapertura descritta sopra.
- Un profilo riconosciuto ma non disponibile, un timeout o un errore TLS dopo l'accettazione fermano il traffico e chiudono i collegamenti della transizione: `ok=false`, stato `BLOCKED`, `desired_profile` richiesto, profilo/gruppo/connessione osservati `null`, verifiche `false`. La policy accettata resta registrata. **Nessun ripiego automatico sul classico.**
- Input non valido, prova/target errati, conflitto di ID, versione obsoleta o `busy` rifiutano il comando senza modificare connessione e policy correnti. Un profilo scritto male è input non valido; `HYBRID` correttamente richiesto ma non disponibile è invece un fallimento della policy accettata.
- L'helper conserva in memoria le ultime 128 richieste completate e risposte. Ripetere lo stesso `request_id` con contenuto identico restituisce la risposta conservata, senza ripetere l'operazione. La risposta può descrivere uno stato passato: per conoscere quello attuale usare un nuovo `get_status`. Riutilizzare un ID conservato con contenuto diverso produce `request_id_conflict`. Se l'originale è ancora in corso, il duplicato riceve `busy` senza riavviare l'operazione.
- Un comando vecchio non più in cache resta innocuo grazie alla verifica della versione di policy. Dopo un riavvio del servizio si avvia una nuova prova con un nuovo `run_id`; la v1 non ripristina sessioni o cache da disco.
- QSNO attende al massimo `timeout_ms + 2000` ms per la risposta di una modifica; per `get_status` attende 2000 ms. Una risposta assente o non valida significa **esito sconosciuto**, non successo e neppure prova che il vecchio traffico sia fermo. QSNO conserva il blocco SDN richiesto, registra l'incertezza e interroga lo stato quando possibile. Le risposte tardive non possono confermare una policy diversa da quella attesa.

Errori previsti in `error.code`:

| Codici | Significato |
|---|---|
| `malformed_request`, `unsupported_schema` | Formato/campi/versione non accettati; nessun comando applicato |
| `wrong_target`, `wrong_run` | Helper o prova diversi da quelli richiesti |
| `stale_policy`, `request_id_conflict`, `busy` | Comando obsoleto, ID riutilizzato male o modifica già in corso |
| `unsupported_profile`, `configuration_error` | Profilo riconosciuto non disponibile o configurazione TLS mancante |
| `connection_failed`, `handshake_failed`, `timeout` | Connessione/TLS non completati entro il limite |
| `certificate_verify_failed`, `unexpected_group`, `unexpected_tls_version`, `unexpected_ciphersuite` | Verifiche del canale fallite |
| `application_ack_failed` | Risposta applicativa assente o incoerente |
| `internal_error` | Errore interno; non dichiarare un collegamento attivo senza evidenza |

`error.detail` è testo diagnostico; il software prende decisioni in base a `code`, non cercando parole nel testo.

## 8. Sequenza comune di integrazione

1. A/B avviano i servizi e gli helper nella nuova prova, inizialmente `IDLE`.
2. A legge stato/capacità e invia `set_profile CLASSIC` se ammesso dalla policy; attende la conferma reale.
3. Arriva un evento alto simulato. A registra la decisione e applica/verifica il blocco SDN selettivo del classico.
4. A invia `set_profile HYBRID` con nuova policy/versione. B interrompe il vecchio collegamento e verifica il nuovo.
5. A dichiara completata la transizione solo dopo una risposta coerente e tutte le verifiche. Per dichiarare applicata l'intera policy occorre anche la verifica dell'enforcement SDN.
6. Su errore o helper irraggiungibile, A mantiene il blocco richiesto e registra fallimento/incertezza. La sola scritta `BLOCKED` dell'helper significa traffico applicativo fermato dall'helper, non regola OpenFlow verificata.

Lo switch non trasforma una connessione classica in ibrida. Le due responsabilità sono fermare il percorso vietato (SDN) e aprire/verificare il collegamento richiesto (helper).

## 9. Compatibilità con il lavoro già verificato

L'adattatore futuro potrà riusare le verifiche di `crypto/qsno_tls.py`, ma non deve trasformare un suo `probe` riuscito in una risposta `HYBRID_ACTIVE`: quel comando chiude la connessione. Nella CLI esistente `profile_requested` è minuscolo e il gruppo si chiama `group_observed`; il nuovo contratto usa i nomi e valori espliciti delle sezioni precedenti. `probe_elapsed_ms` non diventa una misura del solo handshake.

Prima di dichiarare implementata la v1 servono prove reali di: stato iniziale; avvio classico; passaggio ibrido con messaggi numerati; certificato errato; profilo non disponibile; timeout; stop; duplicato senza seconda riconnessione; vecchia policy rifiutata; risposta persa/lettura dello stato; accesso ai socket da QSNO e dai namespace Mininet.

**Consegna immediata ad A:** questo documento e gli esempi JSON permettono di implementare chiamante, validazione degli esiti e scenari simulati. **Consegna successiva di B:** helper conforme e prove reali. L'approvazione congiunta dei nomi/campi fissa la v1; una modifica incompatibile successiva richiede una nuova versione del contratto.
