# QSNO · Architettura, policy e risultati pilota

Contributo del responsabile A, aggiornato al 24 novembre 2026. La revisione della logica esaminata è `ace809c`; per l'infrastruttura SDN il riferimento consultato è `e8a2dd3`. Questi identificatori descrivono il codice esaminato. I log del pilota del 23 novembre non registrano il commit esatto di ogni esecuzione.

## Dalla decisione al traffico

La VM Ubuntu 20.04 ospita tre nodi Mininet e uno switch Open vSwitch. Il server `10.0.0.1` espone il servizio TLS classico su TCP 4433 e quello ibrido su TCP 4434. IoT (`10.0.0.2`) e drone (`10.0.0.3`) raggiungono il server attraverso `s1`. Sul collegamento di ciascun client il profilo nominale imposta 10 Mbit/s e 5 ms per direzione; quello degradato imposta 1 Mbit/s, 40 ms e una probabilità di perdita dell'1% per direzione. Il collegamento server–switch resta invariato. Su due vCPU le quote misurate corrispondono al 20% di un core per IoT e a un core per il drone. La batteria è un ingresso simulato della policy.

QSNO riceve un evento per il client, valuta il requisito e invia la decisione al client SDN. Ryu espone l'API REST sulla porta locale 8080 e controlla lo switch tramite OpenFlow 1.3 sulla porta locale 6653. Per bloccare il servizio classico, la regola seleziona IPv4, TCP, IP sorgente del client, IP del server e porta di destinazione 4433. La priorità 100 prevale sulle regole di inoltro a priorità 1. Un cookie distinto per IoT (`0x1001`) e drone (`0x1002`) permette di verificare e rimuovere il blocco scelto. Sulla VM il client interessato è andato in timeout, mentre l'altro ha continuato a raggiungere il server. Dopo lo sblocco il primo client ha ricevuto nuovamente HTTP 200.

La lettura delle statistiche OpenFlow produce l'esito `RULE_VERIFIED`. Il gruppo TLS viene invece osservato all'endpoint. Per la transizione completa il chiamante abbina la risposta alla richiesta e verifica profilo, gruppo, certificato, conferma applicativa, connessione e sequenza. In caso di risposta incerta tenta una lettura dello stato dell'helper. Nella prova con socket indisponibile l'esito effettivo è stato `sdn=RULE_VERIFIED` e `outcome=UNKNOWN`. La ripresa dei messaggi sul canale ibrido persistente richiede la prova congiunta con l'helper.

## Ordine delle decisioni

| Condizione, in ordine di priorità | Decisione osservabile |
|---|---|
| Allarme alto attivo per il target | Richiede HYBRID anche con batteria bassa o rete degradata. |
| Servizio con minimo HYBRID | Richiede HYBRID. |
| CLASSIC consentito e batteria inferiore al 30% | Seleziona CLASSIC. Il valore 30% è già fuori da questa condizione. |
| CLASSIC consentito e rete degradata | Seleziona CLASSIC. |
| Rete nominale, batteria sufficiente e nessun vincolo precedente | Preferisce HYBRID. |
| Profilo scelto assente fra le capacità di un peer | Richiede il blocco del classico. Dopo la verifica SDN restituisce BLOCKED e identifica il peer incompatibile. |

L'allarme rimane attivo dopo un evento basso. Un reset esplicito consente una nuova valutazione delle condizioni. Durante una singola esecuzione il lettore distingue la ripetizione dello stesso evento dal riutilizzo dello stesso ID con contenuto diverso. Entrambi i casi evitano una seconda applicazione. Un errore durante la verifica SDN produce UNKNOWN e impedisce l'invio del comando all'helper. La versione della policy è relativa alla prova e al target.

Il lettore attuale acquisisce rete e batteria all'avvio. Il mantenimento della decisione invariata evita comandi ripetuti in alcuni casi; resta da implementare e verificare la permanenza temporale prima di reagire a cambiamenti non urgenti della telemetria. Il modello assume una VM amministrata da utenti fidati, identità dei nodi assegnate dalla topologia e servizi in ascolto sulle porte previste. Il filtro sullo switch distingue i flussi tramite indirizzi e porte. La verifica del gruppo TLS e dell'identità del server appartiene agli endpoint. Gli eventi di rischio sono generati per l'esperimento.

## Misure pilota

I tempi indicati sono mediane. Ogni riga comprende dieci misure valide per ciascuna condizione riportata.

| Misura sul drone | Nominale (ms) | Degradata (ms) |
|---|---:|---:|
| Dalla lettura dell'allarme alla regola CLASSIC verificata su s1 | 6,535 | 6,331 |
| Sonda CLASSIC con X25519 | 66,950 | 386,388 |
| Sonda HYBRID con X25519MLKEM768 | 61,335 | 383,467 |

Il primo intervallo termina prima della chiamata all'helper. La sonda comprende avvio del processo OpenSSL, TCP, TLS, scambio HTTP e chiusura. Il gruppo varia a parità di certificato e cifratura dei dati. Le quattro serie di sonde hanno completato 40 connessioni su 40. Nei due profili crittografici il passaggio alla rete degradata ha aggiunto circa 320 ms alla mediana. La topologia applica insieme ritardo, banda e perdita.

| HYBRID su rete nominale · UDP richiesto (Mbit/s) | UDP ricevuto mediano (Mbit/s) | Mediana sonda (ms) |
|---:|---:|---:|
| 0 | — | 58,338 |
| 5 | 5,240 | 60,293 |
| 9 | 8,435 | 1 349,034 |

Per questo esperimento il riferimento a zero è stato misurato in una serie dedicata. Il drone genera sia il traffico UDP sia le connessioni TLS, condividendo link e quota CPU. La banda ricevuta è calcolata sulla finestra UDP che comprende ciascuna sonda. L'aumento osservato sotto carico elevato descrive la latenza dell'applicazione in queste condizioni. Occorrono misure aggiuntive per attribuirlo separatamente a CPU, code o perdite.

### Provenienza e criteri di inclusione

Lo script `scripts/verifica_pilota.py` elenca i file sorgente per nome, rilegge gli identificatori, controlla numerosità e condizioni e ricalcola le mediane. Produce l'hash SHA-256 dei JSONL inclusi. L'elenco usa le serie che Roberto ha identificato durante l'esperimento. Per la serie da 9 Mbit/s comprende le nove prove coerenti e il recupero `recupero-drone-9m-01`. Restano nei dati grezzi le prime serie UDP con intervalli del ricevitore cumulativi, il campione etichettato 5 nella serie richiesta a 9 e i due tentativi TLS riusciti a 9 con carico non confermato. I conteggi sotto carico descrivono il campione validato. La prova SDN preliminare di 17,09 ms rimane separata.

Dal worktree della logica sulla VM:

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/verifica_pilota.py ~/qsno-misure
```

Nove serie verificate e un elenco `errori` vuoto confermano la corrispondenza fra dati conservati e tabelle. Il controllo può essere ripetuto offline. La campagna finale dovrà registrare revisioni e versioni all'avvio di ogni prova, includere entrambi i client e confrontare CLASSIC fisso, HYBRID fisso e policy adattiva. Il tempo dalla ricezione dell'allarme alla prima risposta applicativa verificata e l'interruzione fra due risposte consecutive restano misure da acquisire con l'helper persistente.
