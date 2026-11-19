# QSNO: cosa stiamo costruendo e come mostrarne l'avanzamento

Stato al 19 novembre 2026; prove sulla VM del 18 novembre. Consegna interna: 10 gennaio 2027. Disponibilità: 8 ore settimanali per studente, comprese scrittura, revisione e preparazione dei report.

## Il prodotto finale

QSNO sarà un programma che gestisce comunicazioni sicure in una rete emulata. Riceve le condizioni di un dispositivo/rete e un evento di rischio; decide un profilo ammesso; fa applicare la decisione a rete ed endpoint; verifica il risultato e conserva le misure.

Esempio dimostrativo previsto: l'IoT invia messaggi numerati con un profilo classico consentito. Arriva un evento di rischio alto. QSNO impone il profilo ibrido, fa bloccare il classico per quel dispositivo e fa aprire una nuova connessione ibrida verificata. I messaggi riprendono e il programma misura la pausa e l'esito. Se l'ibrido non è supportato o fallisce, il sistema registra il problema e mantiene il blocco richiesto.

## Il confronto con il progetto BB84

Il repository `45manu95/Quantum-Computing-Project` contiene il motore dei protocolli in `src/` e un'applicazione `main.py` con parametri, scenari, log, grafici ed esportazione CSV. La stessa organizzazione a livelli è utile per QSNO:

| Livello | BB84/E91 | QSNO |
|---|---|---|
| Input | Parametri del canale e presenza di un attaccante | Capacità dei dispositivi, rete, batteria simulata e rischio |
| Motore | Simulazione del protocollo con Qiskit | Motore di policy e orchestrazione degli endpoint/rete |
| Ambiente | Circuiti e modelli di rumore simulati | Host e link emulati con Mininet, con processi TLS reali |
| Esperimenti | Variazione dei parametri e raccolta delle metriche | Tre policy, due condizioni di rete, due profili client |
| Output | Log, tabelle, grafici ed esportazione | Log delle decisioni, tempi, esiti, traffico e grafici |

QSNO non richiede di simulare qubit. La parte post-quantistica usa algoritmi eseguiti su CPU convenzionali. Il contributo del progetto è il software di orchestrazione e la sua valutazione sperimentale, usando primitive crittografiche disponibili nelle librerie.

Un pannello grafico per scegliere gli scenari può essere aggiunto dopo la prima demo completa. Il primo risultato applicativo deve essere avviabile e ripetibile anche da terminale.

## Cosa esiste oggi

| Componente | Stato verificato | Dove si trova |
|---|---|---|
| Topologia, quote CPU, profili rete e client SDN | Presenti; integrazione TLS riuscita | Branch `feature/sdn-infrastructure` |
| OpenSSL e liboqs | Installati e verificati | VM Ubuntu condivisa |
| `crypto/qsno_tls.py` | Server/prove TLS, esito JSON, certificato e gruppo verificati | Branch `feature/crypto-integration` e copia sulla VM |
| `crypto/benchmark_primitives.py` | Esegue test e misure ripetute; prima serie completata | Branch `feature/crypto-integration` e copia sulla VM |
| `crypto/check_mininet_tls.py` | Verifica l'integrazione in una sequenza prefissata; 12/12 controlli superati | Branch `feature/crypto-integration` e copia sulla VM |
| Motore decisionale e orchestratore | Non ancora presenti nel codice applicativo verificato | Da implementare/integrarsi |
| Traffico continuativo e misure della transizione | Da implementare | Parte crittografica/endpoints, con integrazione comune |
| Campagna finale e grafici | Da completare; disponibili primi microbenchmark | Lavoro sperimentale comune |

Codice, istruzioni e [risultati originali verificati](../crypto/results/verified-2026-11-18/README.md) sono raccolti sul branch della crittografia per la revisione comune. Il controllo dell'archivio ha confermato 90 output grezzi, 270 misure, 9 righe statistiche e 12/12 controlli Mininet. Il programma che decide automaticamente quando e come intervenire rimane il prossimo obiettivo centrale.

## Il codice applicativo da sviluppare adesso

I nomi seguenti sono proposti per moduli futuri, non file già esistenti:

- `policy.py`: decide il profilo consentito in base a requisiti, capacità e contesto. È il motore decisionale.
- `orchestrator.py`: riceve un evento, consulta la policy, coordina regola SDN e riconnessione, controlla l'esito e aggiorna lo stato.
- `traffic_client.py`: invia messaggi numerati, riceve la richiesta di cambio profilo e permette di misurare la pausa di servizio.
- `run_scenarios.py`: esegue scenari ripetibili e salva risultati senza interventi manuali durante ogni prova.
- `plot_results.py`: legge i dati e produce le figure per la relazione.

Per ogni modulo il lavoro deve partire da una spiegazione breve di input, output e comportamento, proseguire con lettura/scrittura del codice e concludersi con una prova chiara. Gli studenti devono poter spiegare il codice e distinguere ciò che hanno progettato da ciò che viene fornito da librerie e framework.

## Divisione del lavoro

**Studente A:** topologia, controller e regole SDN; implementazione principale del motore di policy e dello stato dell'orchestratore. L'interfaccia con la parte B viene definita insieme.

**Studente B:** servizi TLS e gestione dei collegamenti; client con traffico continuativo e riconnessione; misure delle primitive e dei collegamenti; elaborazione dei dati e contributo ai grafici.

**Insieme:** regole di sicurezza, scenario automatico, gestione dei fallimenti, confronti sperimentali, relazione e demo. Eventuali parti già sviluppate localmente da A e non pubblicate vanno verificate prima di duplicarne il lavoro.

## Le prove finali

La matrice principale confronta:

- Classico fisso, ibrido fisso e QSNO adattivo.
- IoT e drone, con quote CPU documentate.
- Rete nominale e degradata.
- Almeno 30 ripetizioni per combinazione: 360 prove.

Il generatore deve produrre traffico applicativo confrontabile e un evento di rischio in un istante noto. Le misure devono mostrare sia il costo sia la conformità al requisito di sicurezza, e includere anche errori e timeout.

Le figure principali mostreranno costo di apertura dei canali, byte trasferiti, tempo evento→profilo verificato e interruzione del servizio. CPU/RAM possono essere aggiunte quando effettivamente misurate. La batteria è un parametro di scenario, non una misura energetica della VM.

I microbenchmark ML-KEM/ML-DSA/Falcon già svolti sono una baseline delle primitive, distinta dalla campagna dei collegamenti e dalla valutazione dell'orchestratore. Nel prototipo TLS attuale cambia il gruppo di scambio chiavi; le firme di autenticazione restano ECDSA.

## Scadenze e aggiornamenti al docente

| Scadenza | Risultato da rendere visibile |
|---|---|
| Entro il 23 novembre — report 1 | Codice dei componenti condiviso, architettura, baseline e integrazione 12/12; conferma del perimetro con il docente |
| Entro il 29 novembre | Regole di policy definite e client continuativo in sviluppo; componenti organizzati nel repository |
| Entro il 6 dicembre — report il 7 | Primo scenario automatico completo: evento, decisione, blocco selettivo, riconnessione verificata |
| Entro il 13 dicembre | Demo stabile e casi di errore verificati; esperimenti pronti da eseguire |
| Entro il 20 dicembre — report il 21 | Campagna principale, primi grafici e congelamento delle funzionalità |
| Entro il 3 gennaio — report il 4 | Analisi e relazione complete, versione candidata, slide e demo registrata |
| 10 gennaio | Versione finale, verifica della riproducibilità e prove d'esame |

I report sono congiunti, con un breve elenco dei contributi di ciascuno, salvo diversa indicazione del docente. Preparazione e revisione richiedono circa 30–45 minuti complessivi, già inclusi nel tempo di documentazione/coordinamento.

Ogni report deve rispondere a cinque domande: cosa volevamo ottenere, quale codice abbiamo realizzato, quale prova lo dimostra, cosa abbiamo imparato e cosa faremo nelle due settimane successive.

## Perimetro da confermare nel primo report

Il piano operativo propone TLS come dimostrazione centrale, evento IDS simulato e benchmark separati delle firme. La proposta iniziale considera anche IPsec. Bisogna ottenere un riscontro del docente su questo perimetro prima di trattare IPsec o IDS reale come semplici estensioni. Il prototipo attuale non dimostra autenticazione TLS interamente post-quantistica né migrazione senza interruzione.

## Fonti del confronto

- [BB84/E91: applicazione](https://github.com/45manu95/Quantum-Computing-Project/blob/809fe28d47fa74f8742d1bba829550f6b5835ea2/main.py).
- [BB84: motore del protocollo](https://github.com/45manu95/Quantum-Computing-Project/blob/809fe28d47fa74f8742d1bba829550f6b5835ea2/src/bb84_protocol.py).
- [QSNO: rete e verifiche del collega A](https://github.com/45manu95/QSNO-Quantum-Secure-Network-Orchestrator/blob/e8a2dd3fc7c5baa3e1c084a068064e592761f706/docs/avvio_rete.md).
