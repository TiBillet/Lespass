# API events : `only_futur` réparé, `next_days` ajouté

## Ce qui a été fait

### Le bug : `?only_futur=1` renvoyait 500 **à tous les coups**

`api_v2/views.py` importait le **module** `datetime` (`import datetime`), puis appelait
`datetime.now()` — qui n'existe que sur la **classe** `datetime.datetime`. Chaque appel levait :

```
AttributeError: module 'datetime' has no attribute 'now'
```

**L'endpoint n'a donc jamais fonctionné.** Constaté en production sur
`universite-populaire-villeurbanne.tibillet.coop`.

### Le second bug, latent — et bien vivant en v1

Juste derrière se cachait :

```python
now = now.replace(day=now.day - 1)
```

Le **1er de chaque mois**, `day - 1` vaut `0` → `ValueError: day is out of range for month`.
La v1 (`ApiBillet/views.py`) n'avait pas l'`AttributeError` (elle importe bien la classe), donc
**ce crash mensuel y était atteignable** : `/api/events/?only_futur=1` plantait **un jour sur
trente**.

Ironie : la méthode `future()` **juste en dessous** dans le même fichier utilisait déjà le bon
pattern (`timezone.now() - timedelta(days=1)`).

### La nouveauté : `next_days=N`

`GET /api/v2/events/?next_days=30` → les événements des **30 prochains jours**.

- Entier entre **1 et 366**. Toute autre valeur → **400** (et non un 500).
- **L'emporte sur `only_futur`** si les deux sont fournis.
- Comme `only_futur`, la fenêtre part d'**hier** : un événement commencé hier soir est encore
  d'actualité (c'est aussi ce que fait l'agenda du site).
- Garde également les événements **en cours** (commencés avant la fenêtre, pas encore terminés —
  un festival d'une semaine). Cette clause `end_datetime` n'existe **pas** dans l'agenda : l'API
  est ici volontairement **plus large**.

### Modifications
| Fichier | Changement |
|---|---|
| `api_v2/views.py` | `EventViewSet.list` : correctif + `next_days` + validation. La conversion vers la timezone du tenant est **retirée** : elle ne changeait rien au filtrage (même instant, seul l'affichage diffère) |
| `ApiBillet/views.py` | Même correctif sur la v1 (le crash du 1er du mois) |
| `api_v2/openapi-schema.yaml` | `listEvents` : `only_futur`, `next_days`, `filter` et la réponse `400` sont enfin documentés (aucun paramètre ne l'était) |
| `tests/pytest/test_api_v2_events_filtres_temps.py` | **Nouveau** — 11 tests |

---

## Tests à réaliser

### Test 1 : en local

```bash
# Recupere une cle API de test
CLE=$(docker exec -e TEST=1 lespass_django poetry run python manage.py test_api_key)

BASE="https://lespass.tibillet.localhost/api/v2/events/"
for P in "" "?only_futur=1" "?next_days=30" "?next_days=7"; do
  echo -n "  $P -> "
  curl -sk -o /dev/null -w "HTTP %{http_code}\n" -H "Authorization: Api-Key $CLE" "$BASE$P"
done
```

**Attendu :** `HTTP 200` partout. Et le nombre d'événements doit **décroître** :
sans filtre ≥ `next_days=30` ≥ `next_days=7`.

### Test 2 : la validation

```bash
for P in "trente" "0" "-5" "5000"; do
  echo -n "  next_days=$P -> "
  curl -sk -o /dev/null -w "HTTP %{http_code}\n" -H "Authorization: Api-Key $CLE" \
    "$BASE?next_days=$P"
done
```

**Attendu :** `HTTP 400` partout — **jamais 500**.

### Test 3 : le bug du 1er du mois (le plus important)

Le crash `ValueError` ne se déclenchait que le **1er**. Pour le reproduire sans attendre :

```bash
docker exec lespass_django poetry run python -c "
from datetime import datetime
premier_du_mois = datetime(2026, 8, 1, 10, 0)
try:
    premier_du_mois.replace(day=premier_du_mois.day - 1)
except ValueError as e:
    print('ANCIEN CODE ->', e)

from datetime import timedelta
print('NOUVEAU CODE ->', premier_du_mois - timedelta(days=1))
"
```

**Attendu :** l'ancien pattern lève `day is out of range for month`, le nouveau donne le
31 juillet.

### Test 4 : en production, après déploiement

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Api-Key <TA_CLE>" \
  "https://universite-populaire-villeurbanne.tibillet.coop/api/v2/events/?only_futur=1"
```

**Attendu : `200`.** Avant le correctif : `500`.

---

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_api_v2_events_filtres_temps.py -v
```

**11 tests**, en lecture seule (que des `GET`). Dont un **oracle** : `next_days=365` doit être
un **sur-ensemble** de `next_days=7` — si ce n'est pas le cas, le filtre de fenêtre est faux.

---

## Limite connue, non corrigée (hors périmètre)

La liste v2 **n'exclut pas** les événements de catégorie `ACTION` (les créneaux de bénévolat),
contrairement à la v1 et à la newsletter. Un consommateur de `next_days` recevra donc des
créneaux de bénévolat mêlés aux vrais événements.

C'est **préexistant** — pas introduit par ce correctif — mais ça mérite une décision : soit les
exclure, soit les exposer explicitement (par exemple via un paramètre).
