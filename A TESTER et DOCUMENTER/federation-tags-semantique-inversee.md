# Tags d'un lieu fédéré : sémantique remise à l'endroit

## Ce qui a été fait

Le moteur de l'agenda fédéré appliquait les deux listes de tags d'un `FederatedPlace`
**à l'envers** de ce qu'annoncent les libellés de l'admin.

| Champ | Libellé de l'admin | Avant | Maintenant |
|---|---|---|---|
| `tag_filter` | « N'afficher que ces tags » | **excluait** ces tags | n'affiche **que** ces tags ✅ |
| `tag_exclude` | « Exclure ces tags » | n'affichait **que** ces tags | **exclut** ces tags ✅ |

**La panne était muette.** Quand les deux listes étaient remplies, le moteur excluait ce
qu'on voulait voir puis ne gardait que ce qu'on voulait cacher : l'intersection était vide,
et **le lieu fédéré disparaissait complètement de l'agenda** — sans erreur, sans message.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | `federated_events_filter` : `tag_filter` → `.filter()` conditionnel, `tag_exclude` → `.exclude()`. La fédération auto par tags rangeait ses slugs dans `tag_exclude` (pour exploiter l'inversion) : ils passent dans `tag_filter`. |
| `tests/pytest/test_federation_tags_semantique.py` | **Nouveau** — 3 tests de non-régression. |

> ⚠️ `ruff check --fix` a aussi nettoyé `BaseBillet/views.py` au passage (imports inutilisés,
> f-strings sans placeholder, `not in`). Ces changements sont **sans rapport avec la session**
> mais sont dans le même diff. La suite complète (270 tests) passe. **À arbitrer avant commit.**

---

## Tests à réaliser

### Prérequis
```bash
# Le cache de l'agenda garde l'ANCIEN comportement : le vider avant de tester.
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c \
  "from django.core.cache import cache; cache.clear(); print('cache vide')"
```

### Test 1 : `tag_exclude` exclut vraiment (nominal)

Config du seed : `lespass` fédère `chantefrein` avec `tag_exclude = ['reunion']`.

1. Ouvrir `https://lespass.tibillet.localhost/event/`
2. Repérer les événements marqués *« Consultez l'évènement sur chantefrein… »*
3. **Attendu :** on voit *« Bal trad du vendredi »* et *« Atelier couture — prix libre »*.
   **Aucun** événement de Chantefrein tagué **Réunion** (avant le correctif, c'étaient les
   **seuls** affichés : *AG Ordinaire Chantefrein*, *Point Coop' Chantefrein*).
4. **Attendu aussi :** les réunions de `lespass` **lui-même** (*Assemblée générale annuelle*,
   *Réunion d'équipe*) restent bien visibles — le tenant courant n'a pas de filtre.

### Test 2 : `tag_filter` ne garde que les tags voulus — et le lieu réapparaît

Config du seed : `lespass` fédère `la-maison-des-communs` avec
`tag_filter = ['prix-libre']` et `tag_exclude = ['reunion']`.

1. Sur la même page `/event/`
2. **Attendu :** *« Fête des voisins — prix libre »* apparaît, avec la mention
   *« Consultez l'évènement sur la-maison-des-communs… »* et le tag **Prix libre**.
3. **Avant le correctif, ce lieu était TOTALEMENT ABSENT de l'agenda.** C'est le symptôme
   principal à vérifier : si tu ne vois aucun événement de la Maison des Communs, le
   correctif n'est pas actif (ou le cache n'a pas été vidé).

### Test 3 : cas limites à vérifier à la main dans l'admin

Dans `Administration → Fédération → Espaces fédérés`, sur un `FederatedPlace` :

| Config | Attendu sur `/event/` |
|---|---|
| Les deux listes **vides** | **Tous** les événements publics du voisin remontent |
| `tag_filter` seul | **Seuls** les événements portant ce tag remontent |
| `tag_exclude` seul | Tous les événements **sauf** ceux portant ce tag |
| Les deux remplis | Les événements du filtre, **moins** ceux de l'exclusion |

⚠️ Vider le cache entre chaque changement de config.

### Test 4 : fédération automatique par tags (non-régression)

`Administration → Fédération → Configuration → tags_federation`

Ajouter un tag (ex. `jazz`). **Attendu :** les tenants du réseau ayant un événement public
tagué `jazz` sont ajoutés à l'agenda, et **seuls leurs événements `jazz`** apparaissent
(pas tout leur agenda). Ce comportement est inchangé — mais le code qui le produit a bougé
(les slugs sont passés de `tag_exclude` à `tag_filter`), d'où la vérification.

---

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_federation_tags_semantique.py -v
```

Les 3 tests sont en **lecture seule** et s'appuient sur le seed `demo_data_v2` ; ils se
mettent en `skip` (et non en échec) si le seed est absent.

**Vérifié :** ces tests **échouent bien** si l'on ré-inverse le moteur (2 échecs sur 3 — le
troisième, `test_le_voisin_filtre_par_tags_reste_visible`, existe précisément parce que les
deux autres passent « à vide » quand le voisin a disparu).

Suite complète : **270 tests passés**.

---

## Données de production

**Aucune migration de données n'est appliquée**, et c'est délibéré.

Un gestionnaire ne voit que les libellés de l'admin : il a donc configuré ses tags selon la
sémantique **documentée**. Après le correctif, sa configuration se met simplement à faire ce
qu'il demandait. `demo_data_v2.py` fait d'ailleurs la même hypothèse.

Le cas contraire — un gestionnaire qui aurait constaté l'inversion et rangé ses tags « à
l'envers » — est **peu plausible** : cela l'aurait obligé à s'accommoder d'une configuration
qui fait *disparaître* le lieu qu'il voulait fédérer.

**À faire avant de déployer** — compter les `FederatedPlace` réellement configurés en prod :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import FederatedPlace
total, avec_tags = 0, 0
for t in Client.objects.exclude(schema_name='public'):
    with tenant_context(t):
        for fp in FederatedPlace.objects.prefetch_related('tag_filter', 'tag_exclude'):
            total += 1
            f = [x.slug for x in fp.tag_filter.all()]
            e = [x.slug for x in fp.tag_exclude.all()]
            if f or e:
                avec_tags += 1
                print(f'{t.schema_name} -> {fp.tenant.schema_name} | filter={f} | exclude={e}')
print(f'TOTAL={total} | avec tags={avec_tags}')
"
```

- `avec_tags == 0` → rien à faire, le correctif est gratuit.
- `avec_tags > 0` → demander aux gestionnaires concernés ce qu'ils voulaient obtenir.
  Ils sont probablement une poignée.

**Au déploiement : vider le cache** (l'agenda met en cache la page 1 et les pages par date).

Détail complet : `TECH_DOC/SESSIONS/NEWSLETTER/CHANTIER-01-semantique-tags-federes.md`.
