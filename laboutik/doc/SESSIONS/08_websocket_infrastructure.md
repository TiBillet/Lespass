# Session 08 — WebSocket infrastructure + badge test

## CONTEXTE

Tu travailles sur `laboutik/` et `wsocket/` (Django Channels + HTMX 2).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

L'infrastructure WebSocket est partiellement en place :
- `daphne` est dans SHARED_APPS (settings.py ~ligne 119)
- `ASGI_APPLICATION = "TiBillet.asgi.application"` est configuré
- `CHANNEL_LAYERS` utilise Redis (`redis:6379`)
- `TiBillet/asgi.py` a un `ProtocolTypeRouter` HTTP + WebSocket
- `'channels'` est **commenté** dans INSTALLED_APPS (ligne ~144)
- `wsocket/consumers.py` contient un POC `ChatConsumer` inutilisé
- HTMX 2.0.6 est chargé dans `laboutik/templates/laboutik/base.html`

Le but : activer Channels, créer un consumer POS, et prouver que ça marche
avec un badge vert "Connecté" au chargement de la caisse.

**IMPORTANT** : `manage.py runserver` remplace automatiquement par la version ASGI
de Daphne quand `daphne` est dans INSTALLED_APPS. **NE PAS utiliser `runserver_plus`**
(Werkzeug ne supporte pas ASGI/WebSocket).

## TÂCHE 1 — Activer channels

Lis `TiBillet/settings.py`. Trouve la ligne `# 'channels',` (~ligne 144).
Décommente-la.

## TÂCHE 2 — Télécharger l'extension HTMX ws

```bash
mkdir -p laboutik/static/js/ext/
curl -o laboutik/static/js/ext/ws.js https://unpkg.com/htmx-ext-ws@2.0.2/ws.js
```

Lis `laboutik/templates/laboutik/base.html`. Après la ligne qui charge `htmx@2.0.6.min.js`,
ajoute : `<script src="{% static 'js/ext/ws.js' %}"></script>`

## TÂCHE 3 — Réécrire le consumer

Lis `wsocket/consumers.py` (POC chat). Remplace entièrement par `LaboutikConsumer` :

```python
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

class LaboutikConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.pv_uuid = self.scope["url_route"]["kwargs"]["pv_uuid"]
        self.pv_group_name = f"laboutik-pv-{self.pv_uuid}"
        await self.channel_layer.group_add(self.pv_group_name, self.channel_name)
        await self.accept()
        logger.info(f"[WS] Caisse connectée au PV {self.pv_uuid}")
        # Envoyer le badge "Connecté"
        html = await sync_to_async(render_to_string)(
            "laboutik/partial/hx_ws_connected.html", {"pv_uuid": self.pv_uuid}
        )
        await self.send(text_data=html)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.pv_group_name, self.channel_name)

    async def receive(self, text_data):
        pass  # Server-push only pour l'instant

    async def jauge_update(self, event):
        await self.send(text_data=event["html"])

    async def notification(self, event):
        await self.send(text_data=event["html"])
```

## TÂCHE 4 — Réécrire le routing

Lis `wsocket/routing.py`. Remplace par :

```python
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/laboutik/(?P<pv_uuid>[0-9a-f-]+)/$', consumers.LaboutikConsumer.as_asgi()),
]
```

## TÂCHE 5 — Template badge "Connecté"

Crée `laboutik/templates/laboutik/partial/hx_ws_connected.html` :

```html
<div id="ws-status" hx-swap-oob="innerHTML">
  <div class="ws-connected-badge" data-testid="ws-connected-badge" role="status">
    <i class="fas fa-wifi" aria-hidden="true"></i>
    {% translate "Connecté" %}
  </div>
</div>
```

Avec CSS inline (petit composant, pas la peine d'extraire) :
- Position fixed, top-right, z-index 9999
- Fond vert, border-radius 20px, animation fade-in + fade-out après 2s

## TÂCHE 6 — Connecter dans common_user_interface.html

Lis `laboutik/templates/laboutik/views/common_user_interface.html`.
Ajoute au niveau le plus haut (englobant tout le contenu) :

```html
<div hx-ext="ws" ws-connect="/ws/laboutik/{{ pv_dict.uuid }}/">
  <div id="ws-status"></div>
  <!-- ... tout le reste du template ... -->
</div>
```

## TÂCHE 7 — Créer broadcast.py

Crée `wsocket/broadcast.py` :

```python
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.template.loader import render_to_string

def broadcast_html(group_name, template_name, context, message_type="notification"):
    html = render_to_string(template_name, context)
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(group_name, {"type": message_type, "html": html})
```

## VÉRIFICATION

### Lancer le serveur

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
```

**Pas `runserver_plus`.** Daphne remplace automatiquement `runserver`.

### Test manuel

1. Ouvrir la caisse dans le navigateur
2. Le badge vert "Connecté" apparaît en haut à droite pendant 2s
3. Vérifier dans la console navigateur : pas d'erreur WebSocket
4. Vérifier dans les logs Django : `[WS] Caisse connectée au PV {uuid}`

### Tests existants

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
cd /home/jonas/TiBillet/dev/Lespass/tests/playwright && npx playwright test tests/laboutik/ --reporter=list
```

### Critère de succès

- [ ] `'channels'` décommenté dans settings.py
- [ ] `ws.js` téléchargé et chargé dans base.html
- [ ] `LaboutikConsumer` connecte et envoie le badge
- [ ] Le badge "Connecté" apparaît et disparaît après 2s
- [ ] `broadcast.py` créé avec `broadcast_html()`
- [ ] Tous les tests existants passent
