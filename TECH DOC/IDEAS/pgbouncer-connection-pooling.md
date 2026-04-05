# PgBouncer : connection pooling pour PostgreSQL

## Sources

- Talk DjangoCon US 2025 : "Building maintainable Django projects: the difficult teenage years" — Alex Henman
  - Résumé : https://www.better-simple.com/lunch-talks/2026/03/25/building-maintainable-django-projects/
  - Talk : https://2025.djangocon.us/talks/building-maintainable-django-projects-the-difficult-teenage-years/
  - Tim Schilling (auteur du résumé) note qu'il sous-estimait les capacités de PgBouncer et a découvert des fonctionnalités qu'il ne connaissait pas.

- "Scale your Django app to millions: Master-Slave PostgreSQL Replication with Nginx Load Balancing"
  - https://medium.com/@sizanmahmud08/scale-your-django-app-to-millions-master-slave-postgresql-replication-with-nginx-load-balancing-e7c1d42809e9
  - Couvre la réplication master/slave PostgreSQL + routing Django multi-bases + Nginx (voir section dédiée ci-dessous)

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

## Étape suivante : Réplication PostgreSQL Master/Slave

PgBouncer optimise les **connexions** vers une seule base. La réplication va plus loin :
elle distribue la **charge de lecture** sur plusieurs serveurs PostgreSQL.

Les deux sont complémentaires et s'empilent naturellement :

```
Django → PgBouncer (pool de connexions)
           ├── Master PostgreSQL  (écritures : INSERT, UPDATE, DELETE)
           └── Slave PostgreSQL   (lectures : SELECT)
```

### Pourquoi c'est pertinent pour Lespass

La plupart des apps ont **80-95% de lectures, 5-20% d'écritures**.
Les pages publiques de Lespass (programmes, événements, billetterie) sont massivement
en lecture. Le maître est sollicité surtout pour les réservations et paiements.

### Concepts clés à connaître

**WAL (Write-Ahead Logging)** — le journal de transactions de PostgreSQL.
Chaque modification est d'abord écrite dans le WAL avant d'être appliquée.
C'est ce flux WAL que le slave lit pour se synchroniser avec le master.

**Réplication asynchrone** (défaut) — le master confirme la transaction sans
attendre que le slave l'ait appliquée. Léger décalage possible (réplication lag).
Un lag < 10 MB est considéré comme sain.

**Réplication synchrone** — le master attend la confirmation du slave avant
de confirmer la transaction au client. Zéro perte de données possible, mais
latence accrue. Rarement nécessaire sauf pour des données critiques.

**Replication slots** — mécanisme qui force le master à conserver les fichiers WAL
tant que le slave ne les a pas consommés. Évite la perte de données si le slave
est temporairement déconnecté. Attention : peut faire grossir le disque du master
si un slave est absent longtemps.

**Hot standby** — mode du slave qui lui permet de répondre aux requêtes SELECT
pendant qu'il applique les changements WAL. Activé avec `hot_standby = on`.

### Configuration PostgreSQL — Master

```ini
# postgresql.conf sur le master
wal_level = replica          # Active le WAL pour la réplication
max_wal_senders = 3          # Nombre maximum de slaves connectés simultanément
wal_keep_size = 64           # Conserve 64 MB de WAL pour les slaves lents (en MB depuis PG13)
```

```
# pg_hba.conf sur le master — autoriser le slave à se connecter
host    replication     replication_user    192.168.1.20/32    md5
```

```sql
-- Créer l'utilisateur de réplication sur le master
CREATE USER replication_user WITH REPLICATION ENCRYPTED PASSWORD 'mot_de_passe_fort';
```

### Configuration PostgreSQL — Slave

```bash
# Copie initiale de l'état du master vers le slave
# À exécuter sur le slave, après avoir arrêté PostgreSQL et vidé le répertoire data
pg_basebackup \
  --host=192.168.1.10 \        # IP du master
  --username=replication_user \
  --pgdata=/var/lib/postgresql/data \
  --wal-method=stream \         # Transférer le WAL en temps réel pendant la copie
  --progress \
  --verbose
```

```ini
# postgresql.conf sur le slave
hot_standby = on   # Permet les SELECT pendant la réplication
```

### Vérifier que la réplication fonctionne

```sql
-- Sur le master : voir les slaves connectés et leur lag
SELECT
    client_addr AS adresse_slave,
    state AS etat,
    sent_lsn AS wal_envoye,
    replay_lsn AS wal_applique,
    (sent_lsn - replay_lsn) AS lag_en_octets
FROM pg_stat_replication;

-- lag_en_octets < 10 MB = réplication en bonne santé
```

### Routing Django : écrire sur le master, lire sur le slave

Django supporte nativement plusieurs bases via un **database router**.

```python
# TiBillet/settings.py — déclarer les deux bases
DATABASES = {
    # Base principale : toutes les écritures vont ici
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': os.environ.get('POSTGRES_DB'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': os.environ.get('POSTGRES_MASTER_HOST', 'lespass_postgres_master'),
        'PORT': '5432',
    },
    # Base réplica : toutes les lectures vont ici
    'replica': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': os.environ.get('POSTGRES_DB'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': os.environ.get('POSTGRES_SLAVE_HOST', 'lespass_postgres_slave'),
        'PORT': '5432',
        'TEST': {
            'MIRROR': 'default',  # En test, le replica pointe vers le default
        },
    },
}
```

```python
# TiBillet/database_router.py — router qui dirige les requêtes
class MasterSlaveRouter:
    """
    Router PostgreSQL qui envoie les écritures vers le master
    et les lectures vers le slave.

    Django appelle db_for_read() pour chaque SELECT,
    et db_for_write() pour chaque INSERT/UPDATE/DELETE.
    """

    def db_for_read(self, model, **hints):
        """
        Toutes les lectures vont vers le replica (slave).
        """
        return 'replica'

    def db_for_write(self, model, **hints):
        """
        Toutes les écritures vont vers le master.
        """
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """
        Autorise les relations entre objets des deux bases
        (même cluster PostgreSQL physiquement).
        """
        les_deux_bases_connues = {'default', 'replica'}
        if obj1._state.db in les_deux_bases_connues and obj2._state.db in les_deux_bases_connues:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Les migrations ne s'appliquent que sur le master.
        Le slave se met à jour via la réplication WAL automatiquement.
        """
        return db == 'default'
```

```python
# TiBillet/settings.py — activer le router
DATABASE_ROUTERS = ['TiBillet.database_router.MasterSlaveRouter']
```

### Attention : le réplication lag et les lectures après écriture

Le slave a un léger décalage sur le master. Si un utilisateur crée une réservation
(écriture sur le master) et que Django fait aussitôt un SELECT pour afficher la
confirmation (lecture sur le slave), le slave peut ne pas encore avoir la donnée.

Pour forcer une lecture sur le master ponctuellement :

```python
# Forcer la lecture sur le master pour une vue critique
# (ex: page de confirmation de paiement)
from django.db import connections

ma_reservation = Reservation.objects.using('default').get(pk=reservation_id)
```

Ou utiliser les hints Django dans le router :

```python
def db_for_read(self, model, **hints):
    # Si le code demande explicitement le master, on respecte
    if hints.get('using') == 'default':
        return 'default'
    return 'replica'
```

### Attention : django-tenants et la réplication

Avec django-tenants, le `SET search_path` est exécuté à chaque connexion pour
pointer vers le bon schema de tenant. La réplication WAL réplique **toutes les données
de tous les tenants** sur le slave — c'est le comportement attendu et souhaité.

Le router `MasterSlaveRouter` s'applique normalement, django-tenants fait son
`SET search_path` sur whichever base Django utilise.

### Ordre logique d'implémentation pour Lespass

1. **Maintenant** : rien, le trafic actuel ne justifie pas encore
2. **Quand les connexions DB saturent** : ajouter PgBouncer (voir section ci-dessus)
3. **Quand les lectures ralentissent** : ajouter un slave PostgreSQL + le router Django
4. **Quand un slave ne suffit plus** : ajouter plusieurs slaves + Nginx en load balancer devant

## Priorité

Basse pour l'instant — le trafic actuel ne justifie pas encore ces optimisations.
À réévaluer par étapes :
- PgBouncer d'abord (connexions qui saturent)
- Réplication ensuite (lectures qui ralentissent)
- Plusieurs slaves + Nginx en dernier recours
