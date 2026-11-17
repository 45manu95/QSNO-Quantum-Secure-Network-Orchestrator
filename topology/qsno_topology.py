"""Topologia minima QSNO: tre host e uno switch OpenFlow 1.3."""

from mininet.topo import Topo
from mininet.link import TCLink


NETWORK_PROFILES = {
    "nominal": {"bw": 10, "delay": "5ms", "loss": 0},
    "degraded": {"bw": 1, "delay": "40ms", "loss": 1},
}

class QsnoTopology(Topo):
    def build(self, profile="nominal"):
        if profile not in NETWORK_PROFILES:
            raise ValueError(f"Profilo di rete sconosciuto: {profile}")

        link_options = NETWORK_PROFILES[profile]
        switch = self.addSwitch(
            "s1",
            protocols="OpenFlow13",
            failMode="secure",
        )

        server = self.addHost(
            "h_server",
            ip="10.0.0.1/24",
            mac="00:00:00:00:00:01",
        )
        iot = self.addHost(
            "h_iot",
            ip="10.0.0.2/24",
            mac="00:00:00:00:00:02",
        )
        drone = self.addHost(
            "h_drone",
            ip="10.0.0.3/24",
            mac="00:00:00:00:00:03",
        )

        # Collegamento server invariato, senza shaping aggiuntivo.
        self.addLink(server, switch)

        # Banda, ritardo e perdita applicati in entrambe le direzioni.
        self.addLink(iot, switch, cls=TCLink, **link_options)
        self.addLink(drone, switch, cls=TCLink, **link_options)


topos = {"qsno": QsnoTopology}