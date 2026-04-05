# Tuning production : Nginx, Gunicorn, PostgreSQL

## Sources

- DigitalOcean — "Set Up Django with Postgres, Nginx, and Gunicorn on Ubuntu (Advanced Performance Optimizations)" :
  https://www.digitalocean.com/community/tutorials/how-to-set-up-django-with-postgres-nginx-and-gunicorn-on-ubuntu#advanced-performance-optimizations
- DigitalOcean — "How To Optimize Nginx Configuration" :
  https://www.digitalocean.com/community/tutorials/how-to-optimize-nginx-configuration
- "Powering Django: CPU Cores, Threads, Gunicorn Workers, and Unix Sockets" — chadura.com :
  https://chadura.com/blogs/powering-django-a-deep-dive-into-cpu-cores-threads-gunicorn-workers-and-unix-sockets-for-high-performance-deployment
- "PostgreSQL Performance Tuning Best Practices 2025" — mydbops.com :
  https://www.mydbops.com/blog/postgresql-parameter-tuning-best-practices
- "How to Tune shared_buffers and work_mem in PostgreSQL" — oneuptime.com :
  https://oneuptime.com/blog/post/2026-01-25-postgresql-shared-buffers-work-mem-tuning/view
- PostgreSQL Wiki — Tuning Your PostgreSQL Server :
  https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server

---

## 1. Gunicorn

### Formule pour le nombre de workers

La règle universelle en production :

```
nombre_de_workers = (2 × nombre_de_cœurs_CPU) + 1
```

| Cœurs CPU | Workers recommandés |
|-----------|---------------------|
| 1 cœur    | 3 workers           |
| 2 cœurs   | 5 workers           |
| 4 cœurs   | 9 workers           |
| 8 cœurs   | 17 workers          |

**Pourquoi ce chiffre ?** Chaque worker est un processus Python indépendant avec sa
propre mémoire. Le +1 couvre les pics pendant les changements de contexte CPU.

### Worker class : sync vs gevent

Par défaut, Gunicorn utilise des workers **sync** (un seul thread par worker,
bloquant). Pour Django, qui est I/O-bound (beaucoup d'attente : DB, Stripe, Fedow,
Redis), passer à **gevent** peut augmenter le throughput de 3 à 5x.

**Gevent** utilise des green threads (coroutines coopératives). Un seul worker
gevent peut gérer des centaines de connexions en attente d'I/O simultanément,
sans bloquer.

```bash
pip install gevent
```

```ini
# gunicorn.service avec gevent
ExecStart=... gunicorn \
    --workers 4 \
    --worker-class gevent \
    --worker-connections 1000 \   # connexions simultanées par worker gevent
    --bind unix:/run/gunicorn/lespass.sock \
    TiBillet.wsgi:application
```

**Avec gevent** : moins de workers suffisent (4 au lieu de 2×CPU+1) car chaque
worker gère beaucoup de connexions concurrentes. Ajuster `--worker-connections`
selon le trafic attendu.

**Attention** : gevent ne fonctionne pas avec du code vraiment CPU-bound
(calculs lourds). Lespass est majoritairement I/O-bound → gevent est adapté.

### Prévention des fuites mémoire : --max-requests

Les processus Python qui tournent longtemps accumulent de la mémoire (fuites
mémoire dans les libs tierces, fragmentation). `--max-requests` redémarre
proprement les workers après N requêtes.

```ini
--max-requests 1000         # redémarre le worker après 1000 requêtes
--max-requests-jitter 100   # ajoute un délai aléatoire (0-100) pour éviter
                             # que tous les workers redémarrent en même temps
```

Sans `--max-requests-jitter`, tous les workers redémarreraient simultanément
après exactement 1000 requêtes → bref pic de latence. Le jitter étale les
redémarrages dans le temps.

### Keep-alive et timeout

```ini
--timeout 30        # tue les workers qui ne répondent pas en 30s
                    # (adapter aux opérations les plus lentes : export PDF, etc.)
--keep-alive 2      # garde la connexion HTTP ouverte 2s après la réponse
                    # réduit l'overhead de reconnexion pour les clients multi-requêtes
```

### Threads par worker (alternative à gevent)

Si gevent cause des problèmes de compatibilité, les threads sont une alternative
plus simple :

```
threads_par_worker = 2 à 4
```

Avec threads, le nombre de workers peut être réduit :

```
workers_avec_threads = (cœurs CPU / 2) + 1   # ex: 4 cœurs → 3 workers × 4 threads
```

### Config systemd complète pour Lespass (avec toutes les optimisations)

```ini
# /etc/systemd/system/gunicorn.service
[Unit]
Description=Gunicorn daemon pour Lespass
Requires=gunicorn.socket
After=network.target

[Service]
User=lespass
Group=www-data
WorkingDirectory=/home/lespass/Lespass
ExecStart=/home/lespass/venv/bin/gunicorn \
    --access-logfile - \
    --error-logfile - \
    --workers 4 \
    --worker-class gevent \
    --worker-connections 1000 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout 30 \
    --keep-alive 2 \
    --bind unix:/run/gunicorn/lespass.sock \
    TiBillet.wsgi:application

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/gunicorn.socket
[Unit]
Description=Socket Gunicorn pour Lespass

[Socket]
ListenStream=/run/gunicorn/lespass.sock
SocketUser=www-data

[Install]
WantedBy=sockets.target
```

### Seuils pour augmenter les ressources

Surveiller ces métriques — si elles dépassent ces seuils régulièrement, augmenter :

| Métrique          | Seuil d'alerte |
|-------------------|----------------|
| CPU               | > 70% constant |
| RAM               | ~100% utilisée |
| Latence réponse   | > 500ms p95    |
| Requêtes DB lentes| > 100ms moyen  |

---

## 2. Nginx

### Configuration de base optimisée

```nginx
# /etc/nginx/nginx.conf

user www-data;

# auto = un worker Nginx par cœur CPU
worker_processes auto;

# Augmenter si "too many open files" dans les logs
worker_rlimit_nofile 65535;

events {
    # Connexions simultanées par worker
    # worker_processes × worker_connections = connexions totales max
    worker_connections 1024;

    # Accepter plusieurs connexions en une fois (meilleur débit)
    multi_accept on;
}

http {

    # --- Timeouts ---
    # Temps max pour recevoir les headers d'une requête client
    client_header_timeout 12;

    # Temps max pour recevoir le body d'une requête client
    client_body_timeout 12;

    # Ferme les connexions inactives après 15 secondes
    # (15s = bon compromis entre keep-alive et libération des ressources)
    keepalive_timeout 15;

    # Temps max pour envoyer une réponse au client
    send_timeout 10;

    # --- Buffers ---
    # Taille du buffer pour les headers de requête client
    client_header_buffer_size 1k;

    # Taille max d'un fichier uploadé (à adapter selon les besoins)
    client_max_body_size 10m;

    # Optimise l'envoi de fichiers statiques (bypass user-space)
    sendfile on;

    # Envoie les headers HTTP en une seule fois (réduit les paquets réseau)
    tcp_nopush on;

    # Désactive le buffering Nagle pour les petits paquets (réduit la latence)
    tcp_nodelay on;

    # --- Compression gzip ---
    gzip on;
    gzip_vary on;           # Ajoute le header Vary: Accept-Encoding
    gzip_min_length 1024;   # Ne pas compresser les fichiers < 1 Ko (overhead inutile)
    gzip_comp_level 6;      # Niveau 6 = bon compromis vitesse/compression (1=rapide, 9=max)
    gzip_types
        text/plain
        text/css
        text/javascript
        application/json
        application/javascript
        application/x-javascript
        image/svg+xml;

    # --- Cache des fichiers statiques ---
    # Garde les descripteurs de fichiers ouverts en mémoire (évite les open() répétés)
    open_file_cache max=1000 inactive=20s;
    open_file_cache_valid 30s;
    open_file_cache_min_uses 2;
    open_file_cache_errors on;

    include /etc/nginx/sites-enabled/*;
}
```

### Configuration du vhost Lespass

```nginx
# /etc/nginx/sites-available/lespass

# Zone de cache proxy Nginx (optionnel — voir section Cache Nginx ci-dessous)
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=lespass_cache:10m
                 max_size=100m inactive=60m use_temp_path=off;

upstream lespass_gunicorn {
    # Socket Unix — plus rapide que 127.0.0.1:8000
    server unix:/run/gunicorn/lespass.sock fail_timeout=0;
}

server {
    listen 80;
    server_name lespass.example.com;
    # Redirection HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name lespass.example.com;

    # --- Headers de sécurité ---
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # --- Compression gzip ---
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;           # Compresser aussi les réponses proxifiées
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;

    # --- Fichiers statiques : cache navigateur 1 an ---
    # "immutable" = le navigateur ne re-vérifie jamais tant que l'URL ne change pas
    # Django ajoute un hash dans les URLs des statics → safe
    location = /favicon.ico {
        access_log off;
        log_not_found off;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /static/ {
        alias /home/lespass/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;         # Ne pas logger les requêtes de statics (bruit)
    }

    location /media/ {
        alias /home/lespass/media/;
        expires 1M;             # 1 mois pour les médias (peuvent changer)
        add_header Cache-Control "public";
    }

    # --- Application Django via Gunicorn ---
    location / {
        proxy_pass http://lespass_gunicorn;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts alignés avec --timeout de Gunicorn
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
```

### Load balancing Nginx (scaling horizontal)

Si plusieurs instances Gunicorn tournent (sur plusieurs serveurs ou ports),
Nginx peut distribuer la charge avec la stratégie `least_conn` (le plus
efficace pour des requêtes de durées variables comme les requêtes Django) :

```nginx
upstream lespass_backend {
    least_conn;                         # Route vers le serveur avec le moins de connexions actives
    server 127.0.0.1:8001 weight=3;     # weight = capacité relative du serveur
    server 127.0.0.1:8002 weight=3;
    server 127.0.0.1:8003 weight=2;
    keepalive 32;                       # Maintient 32 connexions persistantes vers les backends
}
```

Stratégies disponibles :
- `round_robin` (défaut) : distribue en tourniquet, simple mais ignore la charge
- `least_conn` : recommandé pour Django (requêtes de durées variables)
- `ip_hash` : même client → même serveur (utile pour les sessions non-Redis)

### Cache proxy Nginx (pour les pages publiques)

Pour les pages publiques sans authentification (programme, liste d'événements),
Nginx peut cacher directement les réponses Django sans même appeler Gunicorn :

```nginx
location / {
    proxy_cache lespass_cache;
    proxy_cache_valid 200 302 10m;      # Cache les 200 et 302 pendant 10 minutes
    proxy_cache_valid 404 1m;           # Cache les 404 pendant 1 minute
    proxy_cache_use_stale               # Sert le cache expiré si Gunicorn est lent
        error timeout updating
        http_500 http_502 http_503 http_504;
    proxy_cache_lock on;                # Un seul worker revalide le cache à la fois
                                        # (évite les "thundering herd" sur cache miss)
    add_header X-Cache-Status $upstream_cache_status;  # Debug : HIT/MISS/BYPASS

    proxy_pass http://lespass_gunicorn;
    # ... autres proxy_set_header
}
```

**Attention** : ne pas cacher les URLs authentifiées (admin, panier, paiement).
Ajouter une exclusion :

```nginx
# Ne pas cacher si cookie de session présent (utilisateur connecté)
set $cache_bypass 0;
if ($http_cookie ~* "sessionid") {
    set $cache_bypass 1;
}
proxy_cache_bypass $cache_bypass;
proxy_no_cache $cache_bypass;
```

---

## 3. PostgreSQL

### Paramètres de tuning — règles empiriques

Les valeurs par défaut de PostgreSQL sont très conservatrices (conçues pour un
Raspberry Pi, pas un serveur de prod). Ces paramètres sont à ajuster dans
`/etc/postgresql/XX/main/postgresql.conf`.

#### `shared_buffers` — cache en mémoire de PostgreSQL

PostgreSQL alloue ce bloc de mémoire pour mettre en cache les données
fréquemment lues. Plus c'est grand, moins il va chercher sur le disque.

```ini
# Règle : 25% de la RAM totale (max utile ~40%)
# Exemples :
# Serveur 2 Go RAM  → shared_buffers = 512MB
# Serveur 4 Go RAM  → shared_buffers = 1GB
# Serveur 8 Go RAM  → shared_buffers = 2GB
# Serveur 16 Go RAM → shared_buffers = 4GB
shared_buffers = 1GB
```

#### `effective_cache_size` — estimation du cache OS

Indique au query planner combien de mémoire est disponible pour le cache
(PostgreSQL + OS combinés). N'alloue pas réellement la mémoire — c'est
juste un hint pour l'optimiseur de requêtes. Impacte le choix entre
index scan (rapide) et sequential scan (lent).

```ini
# Règle : 50-75% de la RAM totale
# Exemples :
# Serveur 4 Go RAM  → effective_cache_size = 3GB
# Serveur 8 Go RAM  → effective_cache_size = 6GB
effective_cache_size = 3GB
```

#### `work_mem` — mémoire par opération de tri/hash

Mémoire allouée par opération (tri, hash join, etc.). **Attention** : une seule
requête complexe peut utiliser `work_mem` plusieurs fois, et plusieurs connexions
concurrentes multiplient l'usage.

```ini
# Règle : (RAM - shared_buffers) / (max_connections × 3)
# Exemples avec 4 Go RAM, 100 connexions :
# (4096 - 1024) / (100 × 3) = ~10 MB
# Ne jamais dépasser 64 MB sans surveiller la mémoire totale
work_mem = 10MB
```

#### `maintenance_work_mem` — pour VACUUM, CREATE INDEX, etc.

```ini
# Règle : 5-10% de la RAM, max 1 GB
# Exemples :
# Serveur 4 Go RAM  → maintenance_work_mem = 256MB
# Serveur 8 Go RAM  → maintenance_work_mem = 512MB
maintenance_work_mem = 256MB
```

#### `wal_buffers` — buffer pour les Write-Ahead Logs

```ini
# Règle : au moins 16 MB en production
# Si beaucoup de connexions concurrentes → augmenter jusqu'à 64 MB
wal_buffers = 16MB
```

#### `max_connections` — connexions simultanées max

```ini
# Règle : ne pas monter trop haut — chaque connexion coûte ~5-10 MB de RAM
# Avec PgBouncer devant, on peut se permettre de baisser ce chiffre
# (PgBouncer gère le pool, PostgreSQL ne voit que les connexions actives)
# Sans PgBouncer : 100-200
# Avec PgBouncer : 50-100 suffisent
max_connections = 100
```

#### Paramètres d'écriture sur SSD

```ini
# Désactiver fsync sur SSD NVMe modernes avec batterie de secours
# (dangereux sans batterie — risque de corruption en cas de crash)
# random_page_cost = 1.1  # (défaut = 4, conçu pour HDD)
random_page_cost = 1.1

# Checkpoint : écrire plus souvent pour des writes plus lisses
checkpoint_completion_target = 0.9
```

### Logging PostgreSQL — détecter les requêtes lentes et les modifications

```ini
# Loguer toutes les modifications (INSERT, UPDATE, DELETE)
# Utile pour le debug et l'audit de sécurité
log_statement = 'mod'

# Loguer les requêtes qui prennent plus de 1 seconde
# (1000ms = valeur DigitalOcean, adapter à 100ms pour un audit plus fin)
log_min_duration_statement = 1000

# Format des lignes de log — inclut timestamp, PID, user, DB, client IP
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

### Exemple complet pour un serveur 4 Go RAM dédié à Lespass

```ini
# /etc/postgresql/16/main/postgresql.conf — section performance

# Mémoire
shared_buffers = 1GB                    # 25% de 4 Go
effective_cache_size = 3GB              # 75% de 4 Go
work_mem = 10MB                         # (4096-1024) / (100×3) ≈ 10 MB
maintenance_work_mem = 256MB            # Pour VACUUM, CREATE INDEX
wal_buffers = 16MB                      # Buffer WAL minimum recommandé

# Connexions
max_connections = 100                   # Baisser à 50 si PgBouncer est installé
listen_addresses = 'localhost'          # Ne jamais exposer sur 0.0.0.0 en prod

# Performance SSD
random_page_cost = 1.1                  # Défaut = 4 (pour HDD), 1.1 pour SSD
checkpoint_completion_target = 0.9     # Étale les writes sur 90% de l'intervalle

# Logging
log_statement = 'mod'
log_min_duration_statement = 1000      # Loguer les requêtes > 1s
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

### Vérifier les gains après modification

```sql
-- Vérifier le taux de hit du cache (shared_buffers)
-- Un bon taux est > 99%
SELECT
    sum(heap_blks_hit) AS blocs_lus_depuis_cache,
    sum(heap_blks_read) AS blocs_lus_depuis_disque,
    round(
        sum(heap_blks_hit)::numeric /
        (sum(heap_blks_hit) + sum(heap_blks_read) + 0.001) * 100,
        2
    ) AS taux_de_hit_cache_pourcentage
FROM pg_statio_user_tables;

-- Détecter les requêtes qui créent des fichiers temporaires (work_mem trop bas)
SELECT query, temp_files, temp_bytes
FROM pg_stat_statements
WHERE temp_files > 0
ORDER BY temp_bytes DESC
LIMIT 10;
```

---

## 4. Django settings pour HTTPS / production

Ces settings Django sont à activer en production (dans `settings/prod.py`
ou via variable d'environnement). Ils complètent la config Nginx SSL.

```python
# TiBillet/settings.py — section sécurité HTTPS

# Redirige toutes les requêtes HTTP vers HTTPS
# (Nginx le fait déjà, mais Django sert de filet de sécurité)
SECURE_SSL_REDIRECT = True

# HSTS : dit aux navigateurs de ne jamais faire de HTTP vers ce domaine
# 31536000 = 1 an en secondes
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True   # S'applique aussi aux sous-domaines
SECURE_HSTS_PRELOAD = True              # Permet l'ajout dans la liste HSTS preload

# Empêche les navigateurs de deviner le type MIME (protection XSS)
SECURE_CONTENT_TYPE_NOSNIFF = True

# Protection XSS du navigateur (header X-XSS-Protection)
SECURE_BROWSER_XSS_FILTER = True

# Cookie de session uniquement en HTTPS (ne jamais envoyer en clair)
SESSION_COOKIE_SECURE = True

# Cookie CSRF uniquement en HTTPS
CSRF_COOKIE_SECURE = True
```

---

## 5. Monitoring et profiling

Pour identifier les vraies lenteurs avant de tuner quoi que ce soit,
installer ces outils en développement et staging :

```bash
pip install django-silk django-debug-toolbar
```

```python
# settings/dev.py
INSTALLED_APPS += [
    'silk',                 # Profiling détaillé requêtes/SQL
    'debug_toolbar',        # Panneau de debug en overlay
]

MIDDLEWARE = [
    'silk.middleware.SilkyMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
] + MIDDLEWARE

INTERNAL_IPS = ['127.0.0.1']

# Silk : active le profiling Python (pas seulement SQL)
SILKY_PYTHON_PROFILER = True
```

**django-silk** profite particulièrement pour Lespass : il montre les requêtes SQL
par vue, leur durée, et les requêtes en doublon (N+1 détection visuelle).

---

## 6. Ordre de priorité pour Lespass

| Étape | Action | Impact | Difficulté |
|-------|--------|--------|------------|
| 1 | Passer Gunicorn sur Unix socket | Perf + sécu | Faible |
| 2 | Ajouter `--worker-class gevent` | Throughput ×3-5 | Faible |
| 3 | Ajouter `--max-requests 1000 --max-requests-jitter 100` | Fuites mémoire | Faible |
| 4 | Ajouter gzip Nginx | Bande passante -60% | Faible |
| 5 | Cache navigateur statics (`expires 1y + immutable`) | Charge serveur | Faible |
| 6 | Tuner `shared_buffers` + `effective_cache_size` PostgreSQL | Lectures DB | Faible |
| 7 | Activer `log_min_duration_statement` + `log_statement = 'mod'` | Détection lenteurs | Faible |
| 8 | Settings Django HTTPS (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, etc.) | Sécurité | Faible |
| 9 | Installer `django-silk` en staging → auditer les N+1 | Perf requêtes | Moyenne |
| 10 | Ajouter PgBouncer | Connexions | Moyenne |
| 11 | Cache proxy Nginx sur pages publiques | Charge Gunicorn | Moyenne |
| 12 | Load balancing Nginx (plusieurs instances Gunicorn) | Scaling horizontal | Haute |
| 13 | Réplication master/slave PostgreSQL | Lectures massives | Haute |

## Priorité

Moyenne — les étapes 1 à 6 sont des modifications de config (pas de code).
Une demi-journée de travail pour des gains immédiats en production.
À faire avant d'attaquer PgBouncer ou la réplication.
