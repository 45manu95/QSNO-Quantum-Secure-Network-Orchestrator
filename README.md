# QSNO — Quantum Secure Network Orchestrator

Progetto del corso di Network Security di Manuel Ganino e Roberto Di Bella. L'obiettivo è realizzare un orchestratore SDN che adatti i profili crittografici alle capacità dei dispositivi, alla rete e a eventi di rischio simulati. Consegna interna: **10 gennaio 2027**.

## Stato del prototipo — 19 novembre 2026

Sono disponibili i componenti TLS classico/ibrido, i benchmark delle primitive e una prima verifica integrata Mininet/SDN con **12 controlli superati su 12**. Il motore decisionale automatico e il client con traffico continuativo sono i prossimi componenti da sviluppare.

- [Codice crittografico e istruzioni](crypto/README.md).
- [Proposta di contratto QSNO ↔ helper v1](docs/CONTRATTO_QSNO_HELPER_V1.md) e [messaggi di esempio](contracts/qsno-helper-v1.examples.json), per lo sviluppo comune; helper persistente ancora da implementare.
- [Risultati originali verificati del 18 novembre](crypto/results/verified-2026-11-18/README.md): 90 esecuzioni di benchmark, 270 misure e report Mininet.
- [Cosa stiamo costruendo e divisione del lavoro](docs/QUADRO_PROGETTO_E_REPORT.md).
- [Piano fino all'esame](docs/PIANO_PROGETTO_GENNAIO_2027.md).
- [Bozza del primo report al docente, 23 novembre](docs/REPORT_01_2026-11-23.md).

Questi file sono condivisi sul branch `feature/crypto-integration`. La rete del collaboratore è sul branch `feature/sdn-infrastructure`; il controllo integrato usa la revisione fissata nelle istruzioni crittografiche. L'integrazione comune avviene su `develop` dopo la revisione delle modifiche.

Il prototipo TLS usa X25519 e X25519MLKEM768 con autenticazione ECDSA. ML-DSA e Falcon sono valutati separatamente; IPsec e IDS reale richiedono un riscontro del docente sul perimetro della prima consegna.

## 🌿 Struttura dei Branch del Progetto

Per lavorare in parallelo senza creare conflitti, utilizziamo un sistema di branching strutturato. Ecco come sono organizzati i branch del nostro repository:

| Nome Branch | Scopo del Branch | Regola d'Oro per il Team |
|---|---|---|
| **`main`** | Conterrà solo il codice stabile e funzionante, ovvero la versione del "prodotto finito" da presentare all'esame. | **Intoccabile.** Nessuno ci scrive direttamente; si aggiorna solo tramite merge di codice testato e sicuro. |
| **`develop`** | Il branch di integrazione dove uniremo il nostro lavoro. | Qui uniamo i nostri lavori individuali per testare che tutto il progetto funzioni insieme. |
| **`feature/sdn-infrastructure`** | Il branch dedicato all'impostazione di Mininet e del controller Ryu. *(Assegnato a chi fa la rete)* | Isolato finché la rete non sta in piedi; poi si fa l'unione (merge) su `develop`. |
| **`feature/qsno-logic`** | Il branch dedicato alla logica decisionale che valuterà batteria, rete e minacce. | Da unire a `develop` solo quando l'algoritmo non presenta errori. |
| **`feature/crypto-integration`** | Servizi TLS, gestione dei collegamenti, benchmark liboqs e raccolta dei risultati. *(Assegnato a chi fa la crittografia)* | Da unire a `develop` dopo revisione e prove di integrazione. |

---

## 🚀 Istruzioni per il Team: Come utilizzare i branch

Una volta che i branch sono stati pubblicati, segui questi passi per lavorarci sul tuo PC:

1. **Aggiorna la lista dei branch dal server GitHub:**
   ```bash
   git fetch origin
   ```
   *(Sostituisci `origin` con `QSNO` se hai chiamato così il tuo remote).*

2. **Spostati sul branch su cui devi lavorare** (ad esempio, quello della crittografia):
   ```bash
   git checkout feature/crypto-integration
   ```

3. **Lavora al codice, poi salva le tue modifiche:**
   ```bash
   git add .
   git commit -m "Aggiunta descrizione delle modifiche"
   ```

4. **Invia le modifiche al server in modo che tutti possano vederle:**
   ```bash
   git push
   ```

> **Nota:** Non fare mai il push diretto su `main`. Quando una feature è pronta, uniscila prima su `develop` per testarla con il lavoro degli altri!
