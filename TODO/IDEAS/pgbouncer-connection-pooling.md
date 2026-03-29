# PgBouncer : connection pooling pour PostgreSQL

## Sources

- Talk DjangoCon US 2025 : "Building maintainable Django projects: the difficult teenage years" — Alex Henman
  - Résumé : https://www.better-simple.com/lunch-talks/2026/03/25/building-maintainable-django-projects/
  - Talk : https://2025.djangocon.us/talks/building-maintainable-django-projects-the-difficult-teenage-years/

Tim Schilling (auteur du résumé) note lui-même qu'il sous-estimait les capacités
de PgBouncer et qu'il a découvert des fonctionnalités qu'il ne connaissait pas.

## Constat actuel sur Lespass

- **Pas de connection pooling** — Django se connecte directement à PostgreSQL
- Pas de service PgBouncer dans `docker-compose.yml`
- Pas de `CONN_MAX_AGE` → Django ouvre et ferme une connexion à chaque requête
- Gunicorn avec 5 workers → jusqu'à 5 connexions simultanées + Celery (6 workers) = 11+ connexions

Avec django-tenants, chaque changement de schema peut impliquer un `SET search_path`,
ce qui ajoute du overhead sur chaque requête.

## Pourquoi PgBouncer ?

PostgreSQL a un coût élevé par connexion (fork d'un processus par client).
PgBouncer agit comme un proxy léger qui réutilise un pool de connexions
PostgreSQL entre les clients Django/Celery.

Bénéfices :
- Réduit le nombre de connexions PostgreSQL actives
- Accélère les requêtes (pas de handshake TCP à chaque fois)
- Protège PostgreSQL contre la surcharge en cas de pic de trafic
- Particulièrement utile avec Celery (6 workers concurrents)

## Actions possibles

### 1. Ajouter PgBouncer comme service Docker

```yaml
# docker-compose.yml — ajouter un service
lespass_pgbouncer:
  image: edoburu/pgbouncer:1.22.0
  environment:
    DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@lespass_postgres:5432/${POSTGRES_DB}
    POOL_MODE: transaction
    DEFAULT_POOL_SIZE: 20
    MAX_CLIENT_CONN: 100
    SERVER_RESET_QUERY: "DISCARD ALL"
  depends_on:
    - lespass_postgres
  networks:
    - frontend
```

### 2. Pointer Django vers PgBouncer

```python
# TiBillet/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'HOST': os.environ.get('POSTGRES_HOST', 'lespass_pgbouncer'),  # PgBouncer au lieu de postgres
        'PORT': os.environ.get('POSTGRES_PORT', '6432'),  # Port PgBouncer
        # ...
        'CONN_MAX_AGE': 0,  # PgBouncer gère le pooling, Django n'a pas besoin de garder les connexions
    }
}
```

## Attention : django-tenants et POOL_MODE

Avec django-tenants, le `SET search_path` est exécuté à chaque requête.
En mode `transaction` de PgBouncer, le `search_path` est réinitialisé
entre chaque transaction, ce qui est compatible. En mode `session`,
le `search_path` persiste — potentiellement dangereux si deux tenants
partagent la même connexion.

**Recommandation** : utiliser `POOL_MODE=transaction` avec `SERVER_RESET_QUERY=DISCARD ALL`.

## Fichiers concernés

| Fichier | Changement |
|---|---|
| `docker-compose.yml` | Ajouter service lespass_pgbouncer |
| `TiBillet/settings.py` | Modifier HOST/PORT pour pointer vers PgBouncer |
| `env_example` | Ajouter variables PgBouncer |

## Priorité

Basse pour l'instant — le trafic actuel ne justifie probablement pas PgBouncer.
À réévaluer quand le nombre de tenants ou le trafic augmente significativement.
Garder en tête pour le scaling.
