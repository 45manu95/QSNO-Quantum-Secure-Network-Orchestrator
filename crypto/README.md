# Prove crittografiche QSNO

## Ambiente verificato sulla VM

- Ubuntu 20.04.1 LTS, x86_64, kernel 5.4.0-42-generic.
- 2 CPU virtuali e circa 4 GiB di RAM.
- OpenSSL 3.5.9 in `/home/mininet/qsno-crypto/openssl-3.5.9`.
- OpenSSL compilato con `-DOPENSSL_USE_IPV6=0`: la VM non rende disponibile IPv6. La suite di test e il controllo successivo dell'installazione sono riusciti.
- TLS 1.3 verificato con X25519 e X25519MLKEM768, certificato del server controllato e AEAD TLS_AES_256_GCM_SHA384 in entrambi i casi.
- Le firme del certificato e dell'handshake TLS restano ECDSA: la prova riguarda la transizione dello scambio chiavi.
- liboqs 0.16.0, commit `5a1a854b0dc9f2141bdc771c555ee60c37950183`, compilazione Release, shared, distribuzione x86_64 e funzioni simmetriche interne (`OQS_USE_OPENSSL=OFF`).
- Selezione minima: ML-KEM-768, ML-DSA-44 e Falcon-512.

Queste informazioni derivano dagli output della VM condivisi in chat il 18 novembre 2026. Le misure seguenti sono pilota, una singola esecuzione di circa un secondo per operazione. I tre test di correttezza liboqs sono stati eseguiti dallo script prima della serie ripetuta completata, riportata più avanti.

| Algoritmo | Generazione chiavi, us | Encapsulation / firma, us | Decapsulation / verifica, us |
|---|---:|---:|---:|
| ML-KEM-768 | 16.181 | 15.578 | 16.637 |
| ML-DSA-44 | 27.453 | 76.433 | 25.844 |
| Falcon-512 | 6821.673 | 296.833 | 51.586 |

Le colonne riportano operazioni diverse per KEM e firme; non costituiscono una classifica comune di sicurezza o velocità. I tempi sono quelli della VM x86_64 con le accelerazioni disponibili, non di un sensore o drone reale.

ML-DSA-44 riporta firme di 2420 byte. Falcon-512 riporta una lunghezza massima di 752 byte e 654 byte per l'ultima firma generata in quella prova: 654 non è la media delle dimensioni delle firme.

## Serie ripetuta

`benchmark_primitives.py` usa soltanto Python 3.8 o successivo, senza pacchetti aggiuntivi. Va eseguito sulla VM con la compilazione liboqs già presente. Non avvia Mininet, non modifica installazioni e non copia chiavi private.

Esempio, dopo avere copiato lo script nella cartella di lavoro della VM:

```bash
python3 /home/mininet/qsno-crypto/benchmark_primitives.py --output /home/mininet/qsno-crypto/results/liboqs-series-01
```

La cartella di output deve essere nuova; lo script non sostituisce risultati preesistenti. Per una seconda campagna scegliere un nome diverso.

Il programma:

1. Controlla versione del codice e impostazioni della compilazione.
2. Esegue e salva i test funzionali dei tre algoritmi; si ferma se uno fallisce.
3. Ripete ogni benchmark 30 volte, per circa un secondo per operazione, con ordine mescolato e seed registrato.
4. Conserva 90 output grezzi e produce 270 righe di misure, oltre a un riepilogo di 9 righe.
5. Registra configurazione, commit, eventuali modifiche ai file sorgente tracciati ed esito della campagna.

Eseguire la serie quando il collega non sta compilando o misurando sulla stessa VM; la durata attesa è dell'ordine di cinque minuti, con possibili variazioni.

File prodotti:

- `checks/`: output dei tre test funzionali.
- `raw/`: output completi dei benchmark, comprese dimensioni e informazioni sulla CPU.
- `metadata.json` e `CMakeCache.txt`: provenienza e configurazione effettiva.
- `measurements.csv`: un record per operazione e per esecuzione.
- `summary.csv` e `summary.txt`: mediana, Q1 e Q3 delle medie ottenute nelle esecuzioni.

Il riepilogo descrive la variabilità fra le medie delle esecuzioni, non i percentili dei tempi delle singole operazioni. La deviazione standard all'interno di ogni esecuzione rimane nel CSV. La dimensione dell'ultima firma Falcon, quando riportata, rimane una singola osservazione, non una media.

Un errore o timeout ferma la campagna e viene salvato nei metadati. I log già prodotti vengono conservati e non viene pubblicato un riepilogo incompleto come se fosse valido. Lo script legge la configurazione dalla cache CMake: la presenza della scritta `OQS_LIBJADE_BUILD` nell'intestazione dei benchmark 0.16.0 non prova, da sola, che l'opzione sia attiva.

### Prima serie completata: 18 novembre 2026

L'archivio originale della VM è stato ricevuto sul Mac il 19 novembre e controllato: tutti i 90 output grezzi corrispondono alle 270 righe delle misure; le 9 righe di riepilogo sono state ricalcolate e coincidono con quelle archiviate. Il [riepilogo originale](results/verified-2026-11-18/liboqs-summary.csv), le [misure](results/verified-2026-11-18/liboqs-measurements.csv) e i [metadati](results/verified-2026-11-18/liboqs-metadata.json) sono consultabili direttamente. Il precedente `results/primitives_vm_summary_2026-11-18.csv` conserva la trascrizione arrotondata condivisa in chat.

| Algoritmo | Operazione | Mediana delle medie, us | Q1, us | Q3, us |
|---|---|---:|---:|---:|
| ML-KEM-768 | keygen | 16.068 | 16.006 | 16.158 |
| ML-KEM-768 | encaps | 15.388 | 15.333 | 15.452 |
| ML-KEM-768 | decaps | 16.495 | 16.458 | 16.522 |
| ML-DSA-44 | keypair | 27.856 | 27.689 | 28.116 |
| ML-DSA-44 | sign | 76.068 | 75.349 | 76.507 |
| ML-DSA-44 | verify | 25.996 | 25.952 | 26.117 |
| Falcon-512 | keypair | 6982.045 | 6894.490 | 7122.486 |
| Falcon-512 | sign | 295.060 | 294.312 | 295.667 |
| Falcon-512 | verify | 51.462 | 51.379 | 51.547 |

In questa VM Falcon impiega circa 3,88 volte il tempo di ML-DSA per firmare, a fronte di firme più piccole. Queste mediane non determinano da sole la scelta del profilo TLS, la durata dell'handshake o il consumo energetico. La vicinanza di Q1 e Q3 descrive la stabilità delle medie fra esecuzioni; non dimostra che le singole operazioni abbiano sempre la stessa latenza.

## Servizi TLS e interfaccia per QSNO

`qsno_tls.py` usa soltanto Python 3.8+ e il binario OpenSSL installato. Riusa i certificati già generati in `/home/mininet/qsno-crypto/tls-lab`; non li modifica. È una base per verificare i profili da un orchestratore. Ogni comando `probe` apre una nuova connessione e invia una richiesta HTTP al servizio di prova OpenSSL.

Avvio del servizio classico, nel primo terminale SSH:

```bash
python3 /home/mininet/qsno-crypto/qsno_tls.py serve --profile classic
```

Verifica dal secondo terminale SSH:

```bash
python3 /home/mininet/qsno-crypto/qsno_tls.py probe --profile classic
```

Per l'ibrido usare `--profile hybrid` in entrambi i comandi. Le porte predefinite sono 4433 per il classico e 4434 per l'ibrido. Il servizio rimane in primo piano fino a Ctrl+C. Per tenere attivi entrambi i servizi occorre avviarli in due processi/terminali distinti.

Il comando `probe` stampa soltanto un oggetto JSON sullo standard output. Restituisce codice 0 esclusivamente quando: OpenSSL termina senza errori, il certificato è verificato, il protocollo è TLS 1.3, il gruppo osservato corrisponde al profilo richiesto, la cipher suite è TLS_AES_256_GCM_SHA384 e arriva una risposta HTTP 200. Un errore restituisce codice 1 con `ok: false` e un motivo; parametri CLI non validi restituiscono codice 2. I log e il risultato sono conservati sotto `/home/mininet/qsno-crypto/results/tls-probes`.

Campi principali per il collega A:

- `request_id`: identificativo da associare alla richiesta/policy.
- `profile_requested`, `group_requested`, `group_observed`: richiesta e risultato osservato.
- `certificate_verified`, `application_response_ok`, `ok`: verifiche eseguite e successo complessivo.
- `openssl_returncode`, `error_code`, `error_detail`: esito del processo e motivo dell'errore.
- `probe_elapsed_ms`: durata complessiva della prova, inclusi avvio processo, TCP, TLS, richiesta/risposta HTTP e chiusura. Non è una misura del solo handshake.

Esempio di esecuzione da un client Mininet, dopo che A ha predisposto indirizzi e connettività:

```bash
python3 /home/mininet/qsno-crypto/qsno_tls.py probe --profile hybrid --host 10.0.0.1 --request-id policy-001 --openssl /home/mininet/qsno-crypto/openssl-3.5.9/bin/openssl --ca /home/mininet/qsno-crypto/tls-lab/ca.crt --log-dir /home/mininet/qsno-crypto/results/tls-probes
```

Il server deve ascoltare su un indirizzo raggiungibile, usando `serve --profile hybrid --bind 10.0.0.1` sul nodo server e specificando anche i percorsi assoluti tramite `--openssl`, `--cert` e `--key`. I percorsi espliciti servono quando Mininet esegue i programmi come root con una home diversa. Il certificato viene verificato rispetto al nome `qsno-server`, indipendentemente dall'indirizzo di connessione. L'indirizzo `10.0.0.1` è quello della topologia pubblicata da A; i collegamenti TLS da IoT e drone in questa topologia sono stati verificati il 18 novembre 2026.

Prove negative con il server ibrido attivo:

```bash
python3 /home/mininet/qsno-crypto/qsno_tls.py probe --profile classic --port 4434
python3 /home/mininet/qsno-crypto/qsno_tls.py probe --profile hybrid --server-name nome-sbagliato
```

Sono attesi rispettivamente `handshake_failed` e `certificate_verify_failed`, con `ok: false` e codice di uscita 1. Un `connection_failed` indicherebbe invece un servizio non raggiungibile e non dimostrerebbe il rifiuto del gruppo o del certificato.

Questo strumento non modifica regole OpenFlow, non applica policy globali, non migra una connessione persistente e non dichiara protetto un flusso soltanto perché è stata inviata una richiesta. Enforcement SDN e gestione della transizione rimangono attività di integrazione del QSNO. Le firme di autenticazione TLS restano classiche.

### Verifica del componente

Il 18 novembre 2026 lo strumento è stato verificato localmente con OpenSSL 3.6.3 mediante connessioni TCP/TLS reali: profilo classico e ibrido, verifica del certificato e risposta HTTP. Sono stati verificati anche rifiuto del gruppo incompatibile, nome del server errato, CA non attendibile, servizio assente e timeout. Controlli sul risultato escludono successi con gruppo inatteso, verifica non confermata o risposta HTTP non valida.

Il 18 novembre 2026 l'utente ha confermato anche sulla VM Ubuntu con OpenSSL 3.5.9 il superamento dei quattro controlli del componente: collegamento classico, collegamento ibrido, rifiuto del gruppo incompatibile e rifiuto del nome del server errato. È poi riuscita anche la prima integrazione in Mininet, descritta nella sezione seguente.

## Primo controllo integrato Mininet

`check_mininet_tls.py` riusa senza modificarli la topologia e il client SDN del collega A, alla revisione `e8a2dd3fc7c5baa3e1c084a068064e592761f706` del branch `feature/sdn-infrastructure`. Il controllo va eseguito sulla VM Ubuntu con `sudo python3`, con il controller Ryu già avviato e nessun'altra rete Mininet attiva.

Lo script rifiuta l'avvio se esiste già `s1` o se il controller gestisce già switch. Questa verifica non è un lock con gli script del collega: concordare una finestra esclusiva sulla VM prima di avviare la prova. Non esegue `mn -c`, non ferma il controller e termina soltanto i propri processi e la rete che ha creato. Un errore conserva il report e attiva la pulizia delle risorse della prova.

La copia della rete va preparata in una directory distinta dal lavoro del collega:

```bash
git clone --single-branch --branch feature/sdn-infrastructure https://github.com/45manu95/QSNO-Quantum-Secure-Network-Orchestrator.git /home/mininet/qsno-crypto/network-check
git -C /home/mininet/qsno-crypto/network-check checkout --detach e8a2dd3fc7c5baa3e1c084a068064e592761f706
```

Avviare il controller in un terminale SSH:

```bash
bash /home/mininet/qsno-crypto/network-check/scripts/start_controller.sh
```

In un secondo terminale SSH, con i due script crittografici copiati nella cartella di lavoro:

```bash
sudo python3 /home/mininet/qsno-crypto/check_mininet_tls.py --network-repo /home/mininet/qsno-crypto/network-check --output /home/mininet/qsno-crypto/results/mininet-tls-01
```

Il controller è quello già preparato da A in `/home/mininet/venvs/qsno-ryu`. Non avviare anche `start_network.sh`: il controllo crea e arresta autonomamente la propria rete. La cartella dei risultati deve essere nuova; per una prova successiva scegliere un altro nome.

Sono previsti 12 controlli:

1. TLS classico dall'IoT.
2. TLS ibrido dall'IoT.
3. TLS classico dal drone.
4. TLS ibrido dal drone.
5. Rifiuto del classico sul servizio ibrido.
6. Rifiuto del nome del server errato.
7. Regola di blocco IoT osservata nelle statistiche dello switch.
8. Traffico classico dell'IoT in timeout dopo il blocco.
9. TLS ibrido dell'IoT ancora operativo.
10. TLS classico del drone ancora operativo.
11. Rimozione del blocco IoT osservata nelle statistiche.
12. TLS classico dell'IoT ripristinato.

Il 18 novembre 2026 la prova sulla VM ha restituito tutti i 12 esiti `PASS`, il riepilogo `COMPLETATO: 12/12 controlli superati` e codice di uscita 0. È stato usato il profilo nominale predefinito. Il [report completo importato dalla VM](results/verified-2026-11-18/mininet-tls-report.json), controllato il 19 novembre, conferma i 12 esiti e l'assenza di errori nella pulizia finale. I log originali sono conservati nell'archivio dei risultati.

`report.json` conserva gli esiti; `probe-logs/` conserva i risultati TLS dettagliati e i log dei server sono separati per profilo. Lo script passa percorsi assoluti a OpenSSL e ai certificati perché i processi Mininet sono eseguiti come root e possono avere una home diversa da `/home/mininet`.

Questa è una verifica funzionale con nuove connessioni, non una campagna di prestazioni o una migrazione di un flusso persistente. Gli esiti delle regole e quelli del traffico rimangono registrati separatamente; non si attribuisce alla lettura delle statistiche una conferma OpenFlow barrier.

Prima della consegna dello script sono stati controllati il rifiuto di una rete già presente, la sequenza delle 12 verifiche con componenti simulati, la pulizia dopo errori e il ripristino dopo un blocco parzialmente applicato. La successiva esecuzione reale sulla VM ha confermato il funzionamento integrato di TLS, della topologia e del blocco selettivo.

## Conservazione del punto verificato

La serie di primitive e la prima prova Mininet vanno conservate con i loro output originali. Dalla sessione SSH della VM, creare un archivio selezionando soltanto le due cartelle dei risultati:

```bash
mkdir -p /home/mininet/qsno-crypto/exports
sudo tar -C /home/mininet/qsno-crypto/results -czf - liboqs-series-01 mininet-tls-01 > /home/mininet/qsno-crypto/exports/qsno-verifiche-2026-11-18.tar.gz
sha256sum /home/mininet/qsno-crypto/exports/qsno-verifiche-2026-11-18.tar.gz
```

La redirezione finale viene eseguita dall'utente SSH, così l'archivio rimane leggibile da `mininet` anche quando i log Mininet sono di proprietà di root. L'archivio include solo le due directory indicate sotto `results`: i certificati e le chiavi della directory `tls-lab` non vengono inclusi. Se la serie di primitive è stata salvata con un nome diverso, utilizzare quel nome al posto di `liboqs-series-01`.

Il file è stato copiato sul Mac tramite SCP il 19 novembre. Il controllo locale ha letto l'intero archivio e verificato coerenza dei risultati e assenza di file di chiavi private. La [nota sui risultati](results/verified-2026-11-18/README.md) descrive i controlli e riporta il checksum locale; non è stato fornito un checksum della VM da confrontare.

Il punto verificato comprende installazione OpenSSL, primitive liboqs, serie di misure ripetute, collegamenti TLS e blocco SDN selettivo. Codice e risultati sono raccolti sul branch crittografico. La prossima attività della parte crittografica è il client con traffico continuativo e riconnessione; insieme al collega va definita l'interfaccia con la policy automatica del QSNO.

## Riferimenti

- [Release liboqs 0.16.0](https://github.com/open-quantum-safe/liboqs/releases/tag/0.16.0).
- [Configurazione minima](https://github.com/open-quantum-safe/liboqs/blob/0.16.0/CONFIGURE.md).
- [Benchmark KEM](https://github.com/open-quantum-safe/liboqs/blob/0.16.0/tests/speed_kem.c) e [benchmark firme](https://github.com/open-quantum-safe/liboqs/blob/0.16.0/tests/speed_sig.c).
- [Intestazione del report](https://github.com/open-quantum-safe/liboqs/blob/0.16.0/tests/system_info.c#L270) e [valore generato per Libjade](https://github.com/open-quantum-safe/liboqs/blob/0.16.0/src/oqsconfig.h.cmake#L498).
- [OpenSSL s_server](https://docs.openssl.org/3.5/man1/openssl-s_server/) e [s_client](https://docs.openssl.org/3.5/man1/openssl-s_client/): profili, gruppi e verifica dei certificati.
