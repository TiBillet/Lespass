# Protection contre les requêtes DB lentes (statement_timeout)

## Source

- Talk DjangoCon US 2025 : "Building maintainable Django projects: the difficult teenage years" — Alex Henman
  - Résumé : https://www.better-simple.com/lunch-talks/2026/03/25/building-maintainable-django-projects/
  - Talk : https://2025.djangocon.us/talks/building-maintainable-django-projects-the-difficult-teenage-years/

## Constat actuel sur Lespass

La configuration de la base de données dans `TiBillet/settings.py` (lignes 254-263) n'a
aucune protection contre les requêtes lentes :

- Pas de `statement_timeout` dans les OPTIONS PostgreSQL
- Pas de middleware qui intercepte les requêtes longues pour renvoyer un 503 gracieux
- Pas de `CONN_MAX_AGE` configuré (Django ferme la connexion après chaque requête par défaut)
- Gunicorn dans `start.sh` n'a pas de `--timeout` explicite (défaut : 30s)
- Nginx n'a pas de `proxy_read_timeout` configuré

## Ce que recommande le talk

Alex Henman configure un `statement_timeout` côté PostgreSQL couplé à un middleware
custom et un backend de base de données modifié. Résultat : les requêtes qui dépassent
le timeout sont transformées en réponses 503 gracieuses plutôt qu'en timeouts silencieux.

## Actions possibles

### 1. Ajouter statement_timeout dans les OPTIONS de la DB

```python
# TiBillet/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        # ... config existante ...
        'OPTIONS': {
            'options': '-c statement_timeout=30000',  # 30 secondes
        },
    }
}
```

### 2. Ajouter CONN_MAX_AGE

```python
DATABASES = {
    'default': {
        # ...
        'CONN_MAX_AGE': 600,  # Réutiliser les connexions pendant 10 minutes
    }
}
```

### 3. Configurer les timeouts Gunicorn

```bash
# start.sh
poetry run gunicorn TiBillet.wsgi --log-level=info -w 5 -b 0.0.0.0:8002 --timeout 60
```

### 4. Configurer les timeouts Nginx

```nginx
# nginx/lespass_dev.conf et nginx_prod/lespass_prod.conf
proxy_connect_timeout 60s;
proxy_send_timeout 60s;
proxy_read_timeout 60s;
```

## Fichiers concernés

| Fichier | Changement |
|---|---|
| `TiBillet/settings.py` | Ajouter OPTIONS avec statement_timeout et CONN_MAX_AGE |
| `start.sh` | Ajouter --timeout à gunicorn |
| `nginx/lespass_dev.conf` | Ajouter proxy timeouts |
| `nginx_prod/lespass_prod.conf` | Ajouter proxy timeouts |
| `docker-compose.yml` | Éventuellement ajouter config PostgreSQL custom |

## Priorité

Moyenne — pas de problème connu en prod actuellement, mais c'est une protection
préventive importante pour la stabilité à mesure que le trafic augmente.
