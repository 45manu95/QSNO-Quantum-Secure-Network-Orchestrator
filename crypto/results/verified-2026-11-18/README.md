# Risultati della VM — 18 novembre 2026

Importati sul Mac e controllati il **19 novembre 2026**. Questi sono risultati di esecuzioni reali nella VM condivisa, non dati generati per esempio.

| File | Contenuto |
|---|---|
| [liboqs-summary.csv](liboqs-summary.csv) | 9 righe: mediana, Q1, Q3, minimo e massimo delle medie di esecuzione |
| [liboqs-measurements.csv](liboqs-measurements.csv) | 270 righe: 3 algoritmi × 30 esecuzioni × 3 operazioni |
| [liboqs-metadata.json](liboqs-metadata.json) | Versione, configurazione, ordine delle prove ed esiti dei tre test funzionali |
| [mininet-tls-report.json](mininet-tls-report.json) | 12 controlli superati; profilo nominale; nessun errore di pulizia |
| [verification.json](verification.json) | Controlli eseguiti all'importazione e checksum dei file selezionati |
| [Archivio completo](../qsno-verifiche-2026-11-18.tar.gz) | Output grezzi, cache CMake, test funzionali e log TLS originali |

I quattro file di risultati qui esposti sono copie inalterate dei rispettivi file nell'archivio. `verification.json` è stato prodotto sul Mac durante il controllo.

Sono stati letti tutti i 90 output di benchmark e confrontati con le misure CSV, inclusi ordine, iterazioni, tempi, deviazioni standard e dimensione dell'ultima firma Falcon quando presente. Le statistiche sono state ricalcolate sulle medie delle esecuzioni e coincidono con il riepilogo. Il report Mininet conferma collegamenti verificati, rifiuti attesi, blocco selettivo IoT e ripristino. Non sono presenti file di chiavi private né blocchi PEM di chiavi private nell'archivio.

SHA-256 dell'archivio ricevuto sul Mac:

```text
49afe3a7b4d49350dc1a181b6f26855fd3eff8696fefcdb9bd0791a846a08e6b
```

Il checksum della copia sulla VM non è stato fornito: non si dichiara un confronto fra i due computer.

## Come leggere queste evidenze

- I tempi delle primitive riguardano la VM x86_64, con 2 CPU virtuali e circa 4 GiB di RAM. Non sono misure di energia o di dispositivi ARM.
- Q1 e Q3 descrivono le **medie fra esecuzioni**, non la distribuzione di latenza delle singole operazioni crittografiche.
- La prova Mininet usa nuove connessioni e una sequenza di azioni prefissata. Non dimostra ancora una decisione adattiva automatica o la transizione di un flusso persistente.
- `probe_elapsed_ms` include avvio processo, TCP, TLS, HTTP e chiusura; non è il tempo del solo handshake.
- Lo scambio chiavi ibrido è X25519MLKEM768; l'autenticazione TLS resta ECDSA.
