"""Topologia minima QSNO: tre host e uno switch OpenFlow 1.3."""

from mininet.topo import Topo


class QsnoTopology(Topo):
    def build(self):
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

        self.addLink(server, switch)
        self.addLink(iot, switch)
        self.addLink(drone, switch)


topos = {"qsno": QsnoTopology}