# Intégration CrowdSec LAPI — Whitelist dynamique depuis Django

## Objectif

Permettre à Lespass (Django) d'ajouter/retirer dynamiquement des IPs dans la whitelist CrowdSec via l'API REST (LAPI), sans passer par `docker exec` ni le socket Docker.

## Principe

CrowdSec expose une API REST locale (LAPI) sur le port 8080. On expose ce port sur le bridge Docker (`172.17.0.1:8080`) pour que les conteneurs du réseau `backend` puissent l'appeler directement via HTTP.

```
lespass_django (backend)
       |
       +-- requests.post("http://172.17.0.1:8080/v1/allowlists/...")
       |
       +-- via bridge Docker (172.17.0.1)
       |
       v
crowdsec:8080 (frontend, wildcard_conf)
```

## Prérequis

### 1. Exposer le port LAPI de CrowdSec

Dans `wildcard_conf/docker-compose.yml`, ajouter le port 8080 sur le loopback uniquement (pas exposé sur Internet) :

```yaml
crowdsec:
    image: crowdsecurity/crowdsec:latest
    container_name: crowdsec
    ports:
      - "127.0.0.1:8080:8080"   # LAPI accessible uniquement en local
    # ... reste de la config
```

Le `127.0.0.1:` est important — sans ce préfixe, le port serait ouvert sur toutes les interfaces (Internet inclus). Avec, seuls les process locaux et les conteneurs via `172.17.0.1` peuvent y accéder.

### 2. Créer une clé API pour Django

```bash
docker exec crowdsec cscli bouncers add lespass-django
```

Cette clé est distincte de celle du plugin Traefik. La stocker dans le `.env` de Lespass :

```
CROWDSEC_LAPI_URL=http://172.17.0.1:8080
CROWDSEC_LAPI_KEY=la_cle_generee
```

## Endpoints LAPI utiles

Documentation : https://crowdsecurity.github.io/api_doc/

### Allowlists (whitelist)

| Action | Methode | Endpoint | Body |
|--------|---------|----------|------|
| Creer une allowlist | `POST` | `/v1/allowlists` | `{"name": "...", "description": "..."}` |
| Lister les allowlists | `GET` | `/v1/allowlists` | — |
| Voir une allowlist | `GET` | `/v1/allowlists/{name}` | — |
| Ajouter une IP | `PUT` | `/v1/allowlists/{name}` | `{"items": [{"value": "1.2.3.4", "comment": "..."}]}` |
| Retirer une IP | `DELETE` | `/v1/allowlists/{name}/items/{ip}` | — |
| Supprimer l'allowlist | `DELETE` | `/v1/allowlists/{name}` | — |

### Decisions (bans)

| Action | Methode | Endpoint |
|--------|---------|----------|
| Lister les bans actifs | `GET` | `/v1/decisions` |
| Bannir une IP | `POST` | `/v1/decisions` |
| Debannir une IP | `DELETE` | `/v1/decisions?ip={ip}` |

### Authentification

Toutes les requetes utilisent le header :

```
X-Api-Key: <CROWDSEC_LAPI_KEY>
```

## Implementation Django

### Service CrowdSec (`crowdsec_service.py`)

```python
import logging
import ipaddress

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

LAPI_URL = getattr(settings, "CROWDSEC_LAPI_URL", "http://172.17.0.1:8080")
LAPI_KEY = getattr(settings, "CROWDSEC_LAPI_KEY", "")
ALLOWLIST_NAME = "tibillet_whitelist"
TIMEOUT = 5


def _headers():
    return {"X-Api-Key": LAPI_KEY}


def _validate_ip(ip: str) -> str:
    """Valide une IP ou un CIDR. Leve ValueError si invalide."""
    ipaddress.ip_network(ip, strict=False)
    return ip


def ensure_allowlist():
    """Cree l'allowlist si elle n'existe pas."""
    resp = requests.get(
        f"{LAPI_URL}/v1/allowlists/{ALLOWLIST_NAME}",
        headers=_headers(),
        timeout=TIMEOUT,
    )
    if resp.status_code == 404:
        resp = requests.post(
            f"{LAPI_URL}/v1/allowlists",
            headers=_headers(),
            json={"name": ALLOWLIST_NAME, "description": "IPs whitelistees par TiBillet/Lespass"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Allowlist '%s' creee dans CrowdSec", ALLOWLIST_NAME)


def whitelist_add(ip: str, comment: str = ""):
    """Ajoute une IP ou un CIDR a la whitelist."""
    ip = _validate_ip(ip)
    ensure_allowlist()
    resp = requests.put(
        f"{LAPI_URL}/v1/allowlists/{ALLOWLIST_NAME}",
        headers=_headers(),
        json={"items": [{"value": ip, "comment": comment}]},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("CrowdSec whitelist: %s ajoute (%s)", ip, comment)


def whitelist_remove(ip: str):
    """Retire une IP de la whitelist."""
    ip = _validate_ip(ip)
    resp = requests.delete(
        f"{LAPI_URL}/v1/allowlists/{ALLOWLIST_NAME}/items/{ip}",
        headers=_headers(),
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("CrowdSec whitelist: %s retire", ip)


def whitelist_list() -> list:
    """Retourne la liste des IPs whitelistees."""
    ensure_allowlist()
    resp = requests.get(
        f"{LAPI_URL}/v1/allowlists/{ALLOWLIST_NAME}",
        headers=_headers(),
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def ban_ip(ip: str, duration: str = "24h", reason: str = "banned by lespass"):
    """Bannit une IP."""
    ip = _validate_ip(ip)
    resp = requests.post(
        f"{LAPI_URL}/v1/decisions",
        headers=_headers(),
        json=[{
            "duration": duration,
            "origin": "lespass",
            "reason": reason,
            "scope": "ip",
            "type": "ban",
            "value": ip,
        }],
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("CrowdSec ban: %s pour %s (%s)", ip, duration, reason)


def unban_ip(ip: str):
    """Retire le ban d'une IP."""
    ip = _validate_ip(ip)
    resp = requests.delete(
        f"{LAPI_URL}/v1/decisions",
        headers=_headers(),
        params={"ip": ip},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("CrowdSec unban: %s", ip)
```

### Management command (`manage.py crowdsec`)

```python
# management/commands/crowdsec.py
from django.core.management.base import BaseCommand
from myapp.crowdsec_service import (
    whitelist_add, whitelist_remove, whitelist_list,
    ban_ip, unban_ip,
)


class Command(BaseCommand):
    help = "Gestion CrowdSec : whitelist et bans"

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action")

        add_cmd = sub.add_parser("whitelist-add")
        add_cmd.add_argument("ip")
        add_cmd.add_argument("--comment", default="")

        rm_cmd = sub.add_parser("whitelist-remove")
        rm_cmd.add_argument("ip")

        sub.add_parser("whitelist-list")

        ban_cmd = sub.add_parser("ban")
        ban_cmd.add_argument("ip")
        ban_cmd.add_argument("--duration", default="24h")
        ban_cmd.add_argument("--reason", default="banned by lespass")

        unban_cmd = sub.add_parser("unban")
        unban_cmd.add_argument("ip")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "whitelist-add":
            whitelist_add(options["ip"], options.get("comment", ""))
        elif action == "whitelist-remove":
            whitelist_remove(options["ip"])
        elif action == "whitelist-list":
            for item in whitelist_list():
                self.stdout.write(f"  {item['value']}  {item.get('comment', '')}")
        elif action == "ban":
            ban_ip(options["ip"], options["duration"], options["reason"])
        elif action == "unban":
            unban_ip(options["ip"])
        else:
            self.print_help("manage.py", "crowdsec")
```

### Utilisation

```bash
# Depuis le conteneur lespass_django
poetry run python manage.py crowdsec whitelist-add 192.168.1.100 --comment "serveur de backup"
poetry run python manage.py crowdsec whitelist-add 10.0.0.0/8 --comment "reseau interne"
poetry run python manage.py crowdsec whitelist-remove 192.168.1.100
poetry run python manage.py crowdsec whitelist-list
poetry run python manage.py crowdsec ban 1.2.3.4 --duration 48h --reason "brute force"
poetry run python manage.py crowdsec unban 1.2.3.4
```

```python
# Depuis le code Django (vue, signal, celery task...)
from myapp.crowdsec_service import whitelist_add, ban_ip

# Whitelister l'IP d'un partenaire
whitelist_add("203.0.113.50", comment="API partenaire XYZ")

# Bannir apres 5 tentatives echouees
ban_ip(request.META["REMOTE_ADDR"], duration="1h", reason="trop de tentatives")
```

## Cas d'usage concrets pour TiBillet

- **Whitelist automatique des serveurs Fedow** : au deploiement, Lespass whitelist l'IP de son Fedow
- **Whitelist des IPs de monitoring** : Sentry, uptime checks, etc.
- **Ban applicatif** : si Django detecte un comportement suspect (scan de NFC tags, brute force sur l'API), il peut bannir directement sans attendre que CrowdSec le detecte dans les logs
- **Whitelist temporaire** : pour un debug en prod, whitelister une IP le temps de l'intervention puis la retirer

## Securite

- Le port 8080 est expose uniquement sur `127.0.0.1` — pas accessible depuis Internet
- La clé LAPI est distincte de celle du bouncer Traefik (principe de moindre privilege)
- Valider les IPs avec `ipaddress.ip_network()` avant tout appel pour eviter les injections
- Logger tous les appels pour audit

## A faire

- [ ] Exposer le port 8080 de CrowdSec dans wildcard_conf/docker-compose.yml
- [ ] Creer une cle bouncer dediee pour Django
- [ ] Ajouter `CROWDSEC_LAPI_URL` et `CROWDSEC_LAPI_KEY` au .env de Lespass
- [ ] Implementer le service dans le code Lespass
- [ ] Ajouter la management command
- [ ] Tester depuis le conteneur lespass_django
