# Observabilité : request_id et logging structuré

## Sources

- Talk DjangoCon US 2025 : "Building maintainable Django projects: the difficult teenage years" — Alex Henman
  - Résumé : https://www.better-simple.com/lunch-talks/2026/03/25/building-maintainable-django-projects/
  - Talk : https://2025.djangocon.us/talks/building-maintainable-django-projects-the-difficult-teenage-years/
- Interview de Mike Amundsen (sur l'interopérabilité et l'observabilité des systèmes)
  - https://htmx.org/essays/interviews/mike-amundsen/

## Constat actuel sur Lespass

L'observabilité est **basique** :

**Ce qui existe :**
- Logging Django avec un filtre `tenant_context` (schema_name + domain_url) — c'est bien
- Rotating file handler vers `/logs/Djangologfile` (100 Mo max)
- Sentry configuré en production (30% traces, 30% profiles) — `TiBillet/settings.py` lignes 51-64
- Celery avec `-l INFO`

**Ce qui manque :**
- Aucun `request_id` injecté dans les logs → impossible de corréler les logs d'une même requête
- Pas de logging structuré (JSON) → difficile à parser par un agrégateur
- Nginx ne log pas les temps de réponse ni les noms de vues Django
- Pas de corrélation entre les requêtes HTTP et l'activité DB
- Pas d'instrumentation des tâches Celery (durée, retries, échecs)
- Pas d'agrégation centralisée des logs (ELK, Loki, etc.)

## Ce que recommande le talk

Alex Henman utilise un middleware qui :
1. Injecte un `request_id` unique (UUID) dans chaque requête
2. Propage ce `request_id` dans tous les logs de la requête
3. Expose les noms de vues Django dans les logs nginx
4. Corrèle l'activité base de données avec les requêtes HTTP

## Actions possibles

### 1. Middleware request_id (priorité haute)

Créer un middleware simple qui génère un UUID par requête et l'ajoute
au contexte de logging :

```python
# TiBillet/middleware.py (nouveau fichier)
import uuid
import logging
import threading

# Thread-local storage pour stocker le request_id
# / Thread-local storage for the request_id
_thread_local_storage = threading.local()


def get_current_request_id():
    """Retourne le request_id de la requête en cours, ou None."""
    return getattr(_thread_local_storage, 'request_id', None)


class RequestIdMiddleware:
    """
    Middleware qui ajoute un identifiant unique à chaque requête HTTP.
    Cet identifiant est propagé dans tous les logs de la requête,
    ce qui permet de corréler les logs entre eux.
    / Middleware that adds a unique ID to each HTTP request for log correlation.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Génère un identifiant unique pour cette requête
        # / Generate a unique ID for this request
        request_id = str(uuid.uuid4())[:8]
        _thread_local_storage.request_id = request_id
        request.request_id = request_id

        response = self.get_response(request)

        # Ajoute le request_id dans les headers de la réponse
        # / Add request_id to response headers
        response['X-Request-ID'] = request_id

        # Nettoyage
        _thread_local_storage.request_id = None
        return response
```

### 2. Filtre de logging pour injecter le request_id

```python
# Dans TiBillet/settings.py — ajouter au LOGGING
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_current_request_id() or '-'
        return True
```

### 3. Format de log enrichi

```python
# TiBillet/settings.py — modifier le formatter
'tenant_context': {
    'format': '[%(request_id)s] [%(schema_name)s:%(domain_url)s] %(levelname)s %(asctime)s %(name)s %(message)s'
}
```

## Fichiers concernés

| Fichier | Changement |
|---|---|
| `TiBillet/middleware.py` | Créer (nouveau) — RequestIdMiddleware |
| `TiBillet/settings.py` | Ajouter middleware + filtre logging + format enrichi |
| `nginx/lespass_dev.conf` | Custom log format avec X-Request-ID et $upstream_response_time |
| `nginx_prod/lespass_prod.conf` | Idem |

## Priorité

Haute — le request_id est la brique de base de toute observabilité.
Sans ça, débugger un problème en production multi-tenant est un cauchemar.
Le reste (logging JSON, agrégation) peut venir après.
