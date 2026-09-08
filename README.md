# QSNO-Quantum-Secure-Network-Orchestrator
An SDN Architecture for Cryptographic Agility and Adaptive Security. The system dynamically orchestrates hybrid and post-quantum encryption to balance security, latency, and power consumption in IoT devices.


PER ORA QUESTO RIMMARRÀ SOLO PER CAPIRE QUALI SONO I BRANCH

## 🌿 Struttura dei Branch del Progetto

Per lavorare in parallelo senza creare conflitti, utilizziamo un sistema di branching strutturato. Ecco come sono organizzati i branch del nostro repository:

| Nome Branch | Scopo del Branch | Regola d'Oro per il Team |
|---|---|---|
| **`main`** | Conterrà solo il codice stabile e funzionante, ovvero la versione del "prodotto finito" da presentare all'esame. | **Intoccabile.** Nessuno ci scrive direttamente; si aggiorna solo tramite merge di codice testato e sicuro. |
| **`develop`** | Il branch di integrazione dove uniremo il nostro lavoro. | Qui uniamo i nostri lavori individuali per testare che tutto il progetto funzioni insieme. |
| **`feature/sdn-infrastructure`** | Il branch dedicato all'impostazione di Mininet e del controller Ryu. *(Assegnato a chi fa la rete)* | Isolato finché la rete non sta in piedi; poi si fa l'unione (merge) su `develop`. |
| **`feature/qsno-logic`** | Il branch dedicato alla logica decisionale che valuterà batteria, rete e minacce. | Da unire a `develop` solo quando l'algoritmo non presenta errori. |
| **`feature/crypto-integration`** | Il branch dove verranno compilate e integrate le librerie come `liboqs` all'interno di IPsec e TLS. *(Assegnato a chi fa la crittografia)* | Modifiche isolate qui finché la compilazione crittografica non va a buon fine. |

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