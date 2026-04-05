from urllib.parse import parse_qs
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from controlvanne.models import TireuseBec, RfidSession


def sanitize(name: str) -> str:
    name = (name or "").strip().lower()
    return name[:80] or "all"


class PanelConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        name = self.scope.get("url_route", {}).get("kwargs", {}).get("slug")
        print(f"🔌 WS CONNECTION - slug recu: '{name}'")

        if name and name.lower() != "all":
            self.group = f"rfid_state.{name.lower()}"
        else:
            self.group = "rfid_state.all"

        print(f"🔌 WS CONNECTION - abonnement au groupe: '{self.group}'")

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        print(f"🔌 WS CONNECTION - connecte et abonne a '{self.group}'")

        # Envoi de l'état initial au client qui vient de se connecter
        initial = await self._initial_payload(name)
        if initial:
            await self.send_json(initial)

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def state_update(self, event):
        print(f"📡 WS ENVOI au groupe {self.group}: {event['payload']}")
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _initial_payload(self, only_name: str):
        if not only_name or only_name == "all":
            return None
        tb = TireuseBec.objects.filter(uuid=only_name).first()
        if not tb:
            return {
                "tireuse_bec": only_name,
                "liquid_label": "Liquide",
                "present": False,
                "authorized": False,
                "vanne_ouverte": False,
                "volume_ml": 0.0,
                "debit_l_min": 0.0,
                "message": "",
            }

        if not tb.enabled:
            return {
                "tireuse_bec": tb.nom_tireuse,
                "tireuse_bec_uuid": str(tb.uuid),
                "maintenance": True,
                "present": False,
                "authorized": False,
                "vanne_ouverte": False,
                "message": "En Maintenance",
            }

        open_s = (
            RfidSession.objects.filter(tireuse_bec=tb, ended_at__isnull=True)
            .order_by("-started_at")
            .first()
        )
        return {
            "tireuse_bec": tb.nom_tireuse,
            "tireuse_bec_uuid": str(tb.uuid),
            "liquid_label": tb.liquid_label,
            "present": bool(open_s and open_s.uid),
            "authorized": bool(open_s.authorized) if open_s else False,
            "vanne_ouverte": False,
            "volume_ml": float(open_s.volume_end_ml if open_s else 0.0),
            "debit_cl_min": 0.0,
            "reservoir_ml": float(tb.reservoir_ml),
            "reservoir_max_ml": tb.reservoir_max_ml,
            "prix_litre": str(tb.prix_litre),
            "monnaie": tb.monnaie,
            "message": open_s.last_message if open_s else "",
            "uid": open_s.uid if open_s else None,
        }
