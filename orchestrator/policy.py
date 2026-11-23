"""Selezione del profilo QSNO. Una istanza di AdaptivePolicy per prova."""

import argparse
import json

from .helper_result import GROUPS


class AdaptivePolicy:
    def __init__(self, low_battery_pct=30):
        if type(low_battery_pct) not in (int, float) or not 0 <= low_battery_pct <= 100:
            raise ValueError("Soglia batteria fuori intervallo")
        self.low_battery_pct = low_battery_pct
        self.active_alarms = set()

    def decide(self, target, event, *, minimum_profile, battery_pct, network,
               client_profiles, server_profiles):
        """Valuta eventi ordinati. CLASSIC come minimo consente entrambi i profili."""
        if target not in ("iot", "drone") or event not in ("low", "high", "reset"):
            raise ValueError("Target o evento sconosciuto")
        if minimum_profile not in GROUPS or network not in ("nominal", "degraded"):
            raise ValueError("Requisito minimo o profilo di rete sconosciuto")
        if type(battery_pct) not in (int, float) or not 0 <= battery_pct <= 100:
            raise ValueError("Batteria fuori intervallo")
        for profiles in (client_profiles, server_profiles):
            if not isinstance(profiles, (list, tuple, set, frozenset)) or any(
                    p not in GROUPS for p in profiles):
                raise ValueError("Capacità TLS non valide")

        if event == "high":
            self.active_alarms.add(target)
        elif event == "reset":
            self.active_alarms.discard(target)

        if target in self.active_alarms:
            profile, reason = "HYBRID", "high_risk"
        elif minimum_profile == "HYBRID":
            profile, reason = "HYBRID", "service_minimum"
        elif battery_pct < self.low_battery_pct:
            profile, reason = "CLASSIC", "low_battery"
        elif network == "degraded":
            profile, reason = "CLASSIC", "degraded_network"
        else:
            profile, reason = "HYBRID", "default_preference"

        missing = []
        if profile not in client_profiles:
            missing.append(target)
        if profile not in server_profiles:
            missing.append("server")
        result = {"target_id": target, "desired_profile": profile, "reason": reason,
                  "decision": "BLOCK" if missing else "REQUEST_PROFILE"}
        if missing:
            result["unsupported_by"] = missing
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("iot", "drone"))
    parser.add_argument("events", nargs="+", choices=("low", "high", "reset"))
    parser.add_argument("--minimum", required=True, choices=GROUPS)
    parser.add_argument("--battery", required=True, type=float)
    parser.add_argument("--network", required=True, choices=("nominal", "degraded"))
    parser.add_argument("--client", required=True, nargs="+", choices=GROUPS)
    parser.add_argument("--server", required=True, nargs="+", choices=GROUPS)
    args = parser.parse_args()
    policy = AdaptivePolicy()
    for event in args.events:
        try:
            decision = policy.decide(args.target, event, minimum_profile=args.minimum,
                                     battery_pct=args.battery, network=args.network,
                                     client_profiles=args.client, server_profiles=args.server)
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps({"event": event, **decision}))


if __name__ == "__main__":
    main()
