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