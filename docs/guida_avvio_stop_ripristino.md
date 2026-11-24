# QSNO · Avvio, stop e ripristino sulla VM

## Cosa dimostra il collaudo

Si avvia una rete nominale da stato pulito, si verifica il collegamento a Ryu e si osserva su `s1` la decisione di QSNO quando il drone segnala una rete degradata. Si spengono i processi avviati per la prova e si ripete l'avvio. Il test richiede la VM Mininet già predisposta, i due checkout con gli script installati e un utente abilitato a `sudo`. L'helper TLS può restare spento.

Aprire tre terminali Linux nella stessa VM:

| Terminale | Utilizzo |
|---|---|
| A | Ryu in primo piano, checkout `~/qsno-roberto` |
| B | Mininet in primo piano, checkout `~/qsno-roberto`; dopo l'avvio compare `mininet>` |
| C | Controlli, lettore degli eventi ed evidenze, checkout `~/qsno-logica` |

### 1. Controllare lo stato iniziale

Se è ancora attiva una propria prova precedente, chiuderla con la procedura del punto 5. Concordare l'uso della VM se uno switch o un processo appartiene a un'altra sessione. Il servizio di sistema Open vSwitch deve restare attivo durante tutto il collaudo.

Nel **terminale C**, mantenendo la stessa shell fino alla fine:

```bash
cd ~/qsno-logica
run_id="guida-drone-$(date -u +%Y%m%dT%H%M%SZ)"
prove="$HOME/qsno-misure/$run_id"
mkdir -p "$prove"
set -o pipefail
stato_qsno() {
    local bridges links ports
    bridges=$(sudo ovs-vsctl list-br) || return 1
    links=$(ip -o link show) || return 1
    ports=$(ss -H -ltnp '( sport = :6653 or sport = :8080 or sport = :6654 )') || return 1
    if grep -Fxq s1 <<< "$bridges" || grep -Eq '^[0-9]+: (s1|s1-eth[0-9]+)(:|@)' <<< "$links" || [[ -n "$ports" ]]; then
        echo "Risorse presenti. Verificare la sessione che le usa."
        echo "$bridges"
        grep -E '^[0-9]+: (s1|s1-eth[0-9]+)(:|@)' <<< "$links" || true
        echo "$ports"
        return 1
    fi
    echo "OK: s1 e relative interfacce assenti, porte TCP 6653/8080/6654 libere."
}
stato_qsno | tee "$prove/prima.txt"
```

Procedere quando compare `OK`. Se una risorsa è occupata, identificare la sessione tramite i terminali aperti e, per le porte, `sudo ss -ltnp`. Una risorsa sconosciuta va lasciata al suo proprietario. Una pulizia globale della VM può interrompere il lavoro di altri utenti.

### 2. Avviare e verificare la rete

Nel **terminale A**:

```bash
cd ~/qsno-roberto && bash scripts/start_controller.sh
```

Nel **terminale B**, dopo l'avvio di Ryu:

```bash
cd ~/qsno-roberto && bash scripts/start_network.sh nominal
```

Al prompt **mininet>** del terminale B, una riga alla volta:

```text
net
pingall
sh ovs-vsctl show
h_drone tc qdisc show dev h_drone-eth0
h_drone tc class show dev h_drone-eth0
sh ovs-ofctl -O OpenFlow13 dump-flows s1 "cookie=0x1002/0xffffffffffffffff"
```

Attesi: tre host su `s1`, 6 ping su 6, `is_connected: true` per `tcp:127.0.0.1:6653`, ritardo di 5 ms e banda di 10 Mbit/s sul drone. Il filtro del cookie del drone deve restituire zero regole. Se ne esiste già una, sospendere prima di avviare il lettore.

Nel **terminale C**:

```bash
curl --noproxy '*' --max-time 5 -fsS http://127.0.0.1:8080/stats/switches | tee "$prove/switch-avvio-1.json"
```

La lista deve contenere il DPID 1. Se è vuota attendere la connessione dello switch e ripetere. Se la porta 8080 rifiuta la connessione, controllare nel terminale A che sia stato usato lo script del progetto, che carica anche l'app REST.

### 3. Eseguire lo scenario di telemetria

Nel **terminale C** avviare il lettore. Copiare gli eventi *singolarmente* nello stesso processo. Il file JSONL conserva le tre risposte.

```bash
PYTHONPATH="$HOME/qsno-roberto" python3 -B -m orchestrator.risk_events listen "$run_id" drone --minimum CLASSIC --battery 80 --network nominal --client CLASSIC HYBRID --server CLASSIC HYBRID | tee "$prove/eventi.jsonl"
```

**E1.** Con batteria all'80%, rischio basso e rete nominale, QSNO sceglie HYBRID e installa il blocco CLASSIC.

```json
{"event_id":"E1","target_id":"drone","severity":"low","source":"collaudo","timestamp":"2026-11-24T10:00:00Z"}
```

**T1.** Cambia soltanto il valore di rete comunicato a QSNO. Il collegamento Mininet resta nominale. Le date JSON sono dati di scenario; l'attesa è misurata con l'orologio monotono della VM.

```json
{"event_id":"T1","target_id":"drone","severity":"telemetry","source":"collaudo","timestamp":"2026-11-24T10:00:01Z","battery_pct":80,"network":"degraded"}
```

Lasciare aperto C. **Nel terminale B, al prompt mininet>**, controllare il blocco durante l'attesa:

```text
sh ovs-ofctl -O OpenFlow13 dump-flows s1 "cookie=0x1002/0xffffffffffffffff"
```

Deve comparire `priority=100`, TCP da `10.0.0.3` a `10.0.0.1`, porta di destinazione 4433 e `actions=drop`.

**T2.** Trascorsi almeno 10 secondi reali dalla risposta a T1, incollare in **C**:

```json
{"event_id":"T2","target_id":"drone","severity":"telemetry","source":"collaudo","timestamp":"2026-11-24T10:00:12Z","battery_pct":80,"network":"degraded"}
```

| Evento | Evidenza nel JSON |
|---|---|
| E1 | `desired_profile=HYBRID`, `sdn_action=block`, `sdn=RULE_VERIFIED`, versione 1 |
| T1 | `reason=degraded_network`, `event_status=PENDING`, `sdn_action=keep`, versione 1 |
| T2 | `reason=degraded_network`, `desired_profile=CLASSIC`, `sdn_action=unblock`, `sdn=RULE_VERIFIED`, versione 2 |

Con helper indisponibile, E1 e T2 riportano normalmente `outcome=UNKNOWN`. Il successo di questa prova riguarda l'enforcement SDN. Se T2 è arrivato troppo presto, attendere e inviare un altro campione identico con un nuovo ID e un timestamp successivo. Riutilizzare lo stesso ID fa intervenire la deduplicazione.

### 4. Verificare il ripristino e gestire un'interruzione

Nel **terminale B** ripetere il filtro:

```text
sh ovs-ofctl -O OpenFlow13 dump-flows s1 "cookie=0x1002/0xffffffffffffffff"
```

Dopo lo sblocco devono esserci zero regole con quel cookie. Terminare il lettore in **C** con **Ctrl+D su una riga vuota**. Il lettore, il controller e la CLI Mininet sono processi distinti.

Se lo scenario si interrompe prima di T2, chiudere il lettore. Se la regola del drone era assente all'inizio ed è stata creata da questa prova, ripristinare soltanto quel client, con Ryu e lo switch ancora attivi:

```bash
python3 ~/qsno-roberto/controller/sdn_client.py unblock drone --json
```

Attendere `RULE_VERIFIED` e ripetere il filtro in B. Un errore di collegamento o di verifica lascia il ripristino da accertare. Il comando `unblock` conclude il collaudo; il reset dell'allarme nel motore di policy è un evento applicativo distinto.

### 5. Arrestare e verificare il secondo avvio

1. Se il lettore è ancora attivo, chiuderlo in C. Questo scenario non avvia servizi TLS o iperf.
2. Nel proprio terminale **B**, digitare `exit` a `mininet>` e attendere il ritorno del prompt Linux.
3. Nel proprio terminale **A**, premere **Ctrl+C** e attendere il ritorno del prompt Linux.
4. Nel terminale **C**, eseguire il controllo seguente. Si attende `OK`. Se resta una risorsa, esaminare l'output prima di un altro avvio.

```bash
stato_qsno | tee "$prove/dopo-stop-1.txt"
```

5. Ripetere i due comandi di avvio del punto 2, prima A poi B. In B ripetere `pingall` e il filtro del cookie del drone: attesi 6/6 e zero regole. In C eseguire:

```bash
curl --noproxy '*' --max-time 5 -fsS http://127.0.0.1:8080/stats/switches | tee "$prove/switch-avvio-2.json"
```

6. Con DPID 1 di nuovo presente, arrestare di nuovo B con `exit`, poi A con **Ctrl+C**. In C eseguire:

```bash
stato_qsno | tee "$prove/dopo-stop-2.txt"
```

**Criterio di superamento sulla VM.** Stato iniziale pulito, due avvii con DPID 1 e ping 6/6, sequenza E1–T1–T2 coerente con le due letture del cookie, due arresti con controllo `OK`. Conservare il run ID, i file in `$prove` e l'esito delle letture in B. Un secondo operatore può seguire la stessa sequenza con un nuovo run ID.
