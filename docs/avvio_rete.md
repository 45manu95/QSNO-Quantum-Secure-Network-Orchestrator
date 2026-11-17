# Avvio della rete QSNO

## Ambiente verificato

- Ubuntu 20.04, Python 3.8.10
- Mininet 2.3.0, Open vSwitch 2.13.1
- Ryu 4.34 in un ambiente virtuale separato
- VM: 2 CPU, circa 4 GiB RAM, disco virtuale 30 GiB

Le dipendenze Python sono registrate in requirements/ryu-py38.txt.

## Preparazione dell'ambiente Ryu

Con python3-venv installato, dalla radice del repository:

```bash
python3 -m venv ~/venvs/qsno-ryu
source ~/venvs/qsno-ryu/bin/activate
python -m pip install "pip==23.3.2" "setuptools==57.5.0" "wheel==0.38.4"
python -m pip install --no-build-isolation -r requirements/ryu-py38.txt
python -m pip check
```

## Avvio

Eseguire una sola istanza Mininet alla volta sulla VM condivisa.

Terminale 1 — controller:

```bash
source ~/venvs/qsno-ryu/bin/activate
ryu-manager --ofp-listen-host 127.0.0.1 --ofp-tcp-listen-port 6653 ryu.app.simple_switch_13
```

Terminale 2 — dalla radice del repository:

```bash
sudo mn --custom topology/qsno_topology.py --topo qsno --switch ovsk --controller remote,ip=127.0.0.1,port=6653
```

## Verifica

Al prompt mininet>:

```text
net
pingall
sh ovs-vsctl show
sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

Risultati attesi:
- h_server, h_iot e h_drone collegati a s1.
- Ping: 6/6 risposte, 0% perdita.
- Controller tcp:127.0.0.1:6653 con is_connected: true.
- Regole di inoltro e regola di priorità 0 verso CONTROLLER.

Test integrato superato il 16 novembre 2026.
La reinstallazione da zero usando il file delle dipendenze resta da verificare.

## Arresto

Digitare exit nella CLI Mininet, poi premere Ctrl+C nel terminale Ryu.

## Ambito attuale

Si usa il controller di esempio simple_switch_13.
Policy QSNO, blocchi selettivi, TLS e profili CPU/rete non sono ancora implementati.
## Avvio tramite script

Dalla radice del repository, in due terminali separati:

Terminale 1 — controller:
```bash
bash scripts/start_controller.sh
```

Terminale 2 — rete:
```bash
bash scripts/start_network.sh
```

Non è necessario attivare manualmente l'ambiente Python:
lo script del controller usa ~/venvs/qsno-ryu/bin/ryu-manager.

Verifica nella CLI Mininet:
```text
pingall
sh ovs-vsctl show
```

Test degli script superato il 16 novembre 2026:
6/6 risposte e controller con is_connected: true.

Per arrestare: exit nella CLI Mininet, poi Ctrl+C nel
terminale del controller. Avviare una sola rete Mininet
alla volta sulla VM condivisa.
## Controlli prima dell'avvio

Lo script start_network.sh verifica:
- presenza del comando mn;
- raggiungibilità TCP del controller su 127.0.0.1:6653;
- disponibilità di Open vSwitch;
- assenza di uno switch s1 già esistente.

Il controllo TCP non verifica da solo il protocollo OpenFlow.
Se s1 esiste, lo script si ferma senza cancellarlo.
Questi controlli non costituiscono un lock contro avvii simultanei.

Test superati:
- controller spento: avvio rifiutato;
- controller acceso: rete funzionante, 6/6 ping;
- rete già attiva: secondo avvio rifiutato;
- dopo il rifiuto: rete originale ancora funzionante, 6/6 ping.

## Verifica delle regole e risultati JSON

Il client legge /stats/flow/1 dopo ogni modifica.

Per il blocco controlla cookie, tabella, priorità, match,
azioni vuote e timeout della regola pari a zero.
Per lo sblocco controlla l'assenza del cookie riservato al client.
Una risposta senza lo switch richiesto viene trattata come errore.

### Utilizzo

```bash
python3 controller/sdn_client.py block iot --json
python3 controller/sdn_client.py unblock iot --json
```

Target supportati: iot e drone.

- RULE_VERIFIED: lo stato richiesto della regola è stato osservato.
- ERROR con rule_state UNKNOWN: operazione non confermata.
- traffic_verified: false: il comando non esegue prove applicative.
- request_and_verification_ms: tempo complessivo della richiesta
  HTTP e della verifica tramite statistiche, misurato con
  orologio monotono. Non è il tempo puro di applicazione OpenFlow.

La funzione set_classic_block restituisce un dizionario in caso
di successo e solleva un'eccezione in caso di errore.
La CLI restituisce 0 per successo, 1 per errore operativo
e 2 per argomenti non validi.

### Test superati il 17 novembre 2026

- Presenza e rimozione della regola IoT verificate automaticamente.
- Blocco drone: drone in timeout, IoT ancora operativo.
- Sblocco drone: HTTP 200 ripristinato.
- Blocchi simultanei: entrambi i client in timeout.
- Sblocco del solo IoT: IoT operativo, drone ancora bloccato.
- Switch scollegato con Ryu attivo: HTTP 404 e uscita 1.
- Output JSON di blocco e sblocco verificato.
- Ryu spento: JSON ERROR/UNKNOWN e uscita 1.

Restano distinte la lettura delle regole, la conferma OpenFlow
tramite barrier e la verifica del traffico applicativo.
## Profili di rete

Avvio dalla radice del repository, con Ryu già attivo:

```bash
bash scripts/start_network.sh nominal
bash scripts/start_network.sh degraded
```

Eseguire un solo profilo alla volta, chiudendo prima Mininet con exit.
Senza argomento viene selezionato nominal.

| Parametro client–switch, per direzione | nominal | degraded |
|---|---:|---:|
| Banda | 10 Mbit/s | 1 Mbit/s |
| Ritardo aggiunto | 5 ms | 40 ms |
| Perdita configurata | 0% | 1% |

Il profilo si applica ai collegamenti di IoT e drone tramite TCLink.
Il collegamento server–switch rimane senza shaping aggiuntivo.

### Verifiche preliminari del 17 novembre 2026

- Nominale: RTT minimo IoT 10,189 ms; drone 10,371 ms.
- Degradato: RTT minimo IoT 80,485 ms; drone 82,162 ms.
- Configurazione tc verificata sul collegamento IoT.
- Throughput TCP IoT → server, misurato dal ricevitore:
  - nominale: 8,28 Mbit/s, 32,3 MiB in 32,7 secondi;
  - degradato: 955 kbit/s, 2,62 MiB in 23,1 secondi.
- Nessuna connessione TCP residua dopo la prova nominale.

Una sola prova di throughput per profilo: non costituisce
un benchmark statistico. La perdita configurata non è stata
stimata sperimentalmente con un campione sufficiente.

La durata richiesta al client era 20 secondi; il ricevitore
ha concluso più tardi. La causa della differenza resta da
approfondire prima della campagna sperimentale.
## Quote CPU dei client

IoT e drone utilizzano CPULimitedHost con scheduler CFS.
Il server non ha una quota CPU aggiuntiva configurata.

La versione installata di Mininet calcola:
quota = periodo × frazione CPU × numero di CPU della VM.

Con 2 CPU e periodo di 100000 microsecondi:
- IoT: cpu=0.1, quota=20000 microsecondi;
- drone: cpu=0.5, quota=100000 microsecondi.

Questi valori equivalgono rispettivamente al 20% e al 100%
di una CPU. Sono limiti aggregati, non riserve né assegnazioni
a core specifici. Cambiando il numero di CPU della VM,
le quote vanno rivalutate.

Le quote restano uguali nei profili nominal e degraded.

### Verifica del 17 novembre 2026

Appartenenza ai cgroup e valori quota/periodo verificati.

Carico sequenziale di circa 5 secondi per client:
- IoT: 5,003 s trascorsi, 1,006 s CPU, utilizzo 20,1%;
- drone: 5,000 s trascorsi, 4,986 s CPU, utilizzo 99,7%.

Contatori cumulativi osservati dopo la prova:
- IoT: nr_throttled=48, throttled_time=3983711990 ns;
- drone: nr_throttled=2, throttled_time=5532964 ns.

Le quote non rappresentano uno specifico dispositivo ARM
e non consentono di dedurre il consumo della batteria.