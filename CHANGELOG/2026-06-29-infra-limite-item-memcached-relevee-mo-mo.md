# Infra : limite item Memcached relevée (1 Mo → 8 Mo) pour l'agrégat SEO / Memcached item size raised for the SEO aggregate

**Date :** 2026-06-29
**Migration :** Non / No (infra — recréation du conteneur memcached)

**Quoi / What :** Le service `lespass_memcached` est lancé avec `-I 8m -m 256`
(au lieu des défauts 1 Mo / 64 Mo).

**Pourquoi / Why :** L'agrégat SEO `AGGREGATE_EVENTS` pèse ~687 o/event et contient
tous les events futurs publiés du réseau. À ~1500 events futurs il atteint la limite
Memcached par défaut (1 Mo) ; au-delà le `set` L1 échoue silencieusement → la page
relit la DB à chaque fois (cache inutile). `-I 8m` repousse le mur à ~12 000 events
futurs ; `-m 256` donne la mémoire totale pour ces gros items sans évictions.
Alternative durable (non faite) : borner l'agrégat aux N prochains mois.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `docker-compose.yml` | `lespass_memcached` : `command: ["memcached", "-m", "256", "-I", "8m"]` |
| `docker-compose.pre-prod.yml` | idem |
| `docker-compose.v1.pre-prod.yml` | idem |

### Application / Apply
- **Recréer le conteneur** (vide le cache, reconstruit au prochain rebuild/MISS) :
  `docker compose up -d lespass_memcached` (et `-f docker-compose.pre-prod.yml` en prod).
- Ajuster `-m 256` selon la RAM du serveur.
