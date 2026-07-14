# CHANTIER 01 — Redresser la sémantique des tags fédérés

> **Hub :** [INDEX.md](INDEX.md)
> **Statut : FAIT** (2026-07-13). Corrigé, testé (270 tests verts), vérifié dans le navigateur.
> Reste à trancher avant déploiement : les données de production (§6).
> **Prérequis de [SPEC.md](SPEC.md)** (la newsletter).
> **Nature :** correction de bug. **Change le comportement de l'agenda public.**
>
> **Livré :** `BaseBillet/views.py` (le moteur) · `tests/pytest/test_federation_tags_semantique.py`
> (3 tests de non-régression) · `CHANGELOG.md` ·
> `A TESTER et DOCUMENTER/federation-tags-semantique-inversee.md`

---

## 1. Le bug

`FederatedPlace` porte deux champs M2M, dont les `help_text` (visibles dans l'admin) disent :

| Champ | `help_text` — ce que lit le gestionnaire |
|---|---|
| `tag_filter` | « Show only these tags. » → **n'afficher que** ces tags |
| `tag_exclude` | « Exclude those tags. » → **exclure** ces tags |

Le moteur de l'agenda fédéré fait **exactement l'inverse** (`BaseBillet/views.py:1966-1988`) :

```python
.exclude(
    tag__slug__in=tenant['tag_filter']      # tag_filter EXCLUT
)
...
if len(tenant['tag_exclude']) > 0:
    events = events.filter(
        tag__slug__in=tenant['tag_exclude']) # tag_exclude n'affiche QUE ces tags
```

L'inversion est même **assumée en commentaire** (`views.py:1957-1961`) :

> « tag_exclude = INCLURE uniquement ces tags (sémantique historique inversée du moteur) »

## 2. Pourquoi c'est un bug, et non une convention

Trois sources indépendantes disent la sémantique **documentée**. Une seule dit l'inverse :

| Source | Sémantique |
|---|---|
| `help_text` du modèle (`models.py:3661-3665`) | documentée |
| L'admin Unfold (`FederatedPlaceAdmin`) — le gestionnaire ne voit **que** ces libellés | documentée |
| Le générateur de données de démo (`demo_data_v2.py:2165` : *« Tags: include (tag_filter) et exclude (tag_exclude) »*) | documentée |
| **Le moteur** (`views.py:1976`, `:1986-1988`) | **inversée** |

Le gestionnaire qui configure un `FederatedPlace` n'a sous les yeux que les libellés de l'admin.
**Il configure donc selon la sémantique documentée — et obtient le résultat inverse.**

C'est une régression silencieuse, pas une convention historique volontaire.

## 3. Décision

**Corriger le moteur.** La sémantique devient celle des `help_text`, partout. La newsletter
(SPEC.md) est ensuite écrite directement sur la sémantique correcte.

Alternatives écartées :
- *Aligner la newsletter sur le moteur inversé* → pérennise le bug et le duplique.
- *Extraire un helper partagé sans corriger* → une seule source de vérité, mais toujours fausse.

## 4. Le périmètre du code — il est petit

L'inversion n'est **appliquée** qu'à un seul endroit. Tout le reste ne fait que lire ou
afficher les champs.

| Fichier | Lignes | Changement |
|---|---|---|
| `BaseBillet/views.py` | `1976` | `.exclude(tag__slug__in=tenant['tag_filter'])` → devient un `.filter(...)` **conditionnel** (n'afficher que ces tags, si la liste est non vide) |
| `BaseBillet/views.py` | `1986-1988` | `if tag_exclude: .filter(...)` → devient `.exclude(tag__slug__in=tenant['tag_exclude'])` |
| `BaseBillet/views.py` | `1956-1962` | Fédération auto par tags : les slugs sont aujourd'hui rangés dans `tag_exclude` (pour exploiter l'inversion et n'inclure que ces tags). Ils passent dans **`tag_filter`**. Le commentaire « sémantique historique inversée » disparaît. |

Comportement cible, pour chaque tenant fédéré :

```
si tag_filter est non vide  → ne garder que les events portant au moins un de ces tags
si tag_exclude est non vide → jeter les events portant au moins un de ces tags
```

Le matching reste **par slug** (les `Tag` sont des objets par tenant).

## 5. Le bug, observé en vrai sur la base de dev

Vérifié le 2026-07-13 sur l'instance de développement (données issues de `demo_data_v2.py`,
qui suit la sémantique **documentée** : `include_tags` → `tag_filter`, `exclude_tags` →
`tag_exclude`).

**4 `FederatedPlace` sur 6 ont des tags configurés.** Deux cas suffisent à tout démontrer.

### Cas 1 — `lespass` fédère `chantefrein` : `tag_exclude=['reunion']`

**Intention :** ne PAS montrer les réunions de Chantefrein.
**Réalité, sur l'agenda `https://lespass.tibillet.localhost/event/` :** les **seuls** événements
de Chantefrein affichés sont « AG Ordinaire Chantefrein » et « Point Coop' Chantefrein » —
**les deux tagués `Réunion`**. Exactement l'inverse.

### Cas 2 — `lespass` fédère `la-maison-des-communs` : `tag_filter=['prix-libre']`, `tag_exclude=['reunion']`

**Intention :** ne montrer QUE les événements à prix libre, sans les réunions.

| | Événements affichés |
|---|---|
| **Moteur actuel** (inversé) | **0** — le lieu fédéré est **totalement invisible** sur l'agenda |
| **Sémantique voulue** | **1** — « Fête des voisins — prix libre », précisément l'événement visé |

> **Le mode de défaillance est silencieux.** Quand `tag_filter` **et** `tag_exclude` sont tous
> deux remplis, le moteur ne montre **aucun** événement de ce voisin : il exclut ce qu'on voulait
> voir, puis ne garde que ce qu'on voulait cacher — l'intersection est vide. Un lieu fédéré
> **disparaît**, sans erreur, sans avertissement. C'est probablement pourquoi le bug n'a jamais
> été signalé : il n'affiche rien de faux, il efface.

## 6. Les données de production — le point à trancher avant de coder

**La démonstration ci-dessus porte sur la base de DEV.** La base de production est une autre base :
la même vérification doit y être faite.

Deux cas de figure pour les `FederatedPlace` qui y ont réellement des tags :

| Si le gestionnaire a configuré… | Alors, après correction du code… |
|---|---|
| **selon les libellés de l'admin** (l'hypothèse très probable — c'est tout ce qu'il voit, et c'est ce que fait `demo_data_v2.py`) | sa configuration **se met enfin à faire ce qu'il voulait**. **Aucune migration de données.** |
| **en s'étant adapté au comportement réel** (il aurait constaté l'inversion et rangé ses tags « à l'envers ») | son agenda **bascule**. Il faudrait alors **permuter** `tag_filter` ↔ `tag_exclude` chez lui. |

**Le second cas est peu plausible** au vu du §5 : personne ne « s'adapte » à une configuration
qui fait disparaître le lieu qu'il voulait fédérer. Mais il faut regarder les données avant de
conclure.

### La commande à lancer sur la production

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

### L'arbre de décision

- **`avec_tags == 0`** (le cas le plus probable) → **la question est sans objet.** On corrige le
  moteur, aucune migration, aucun risque. C'est gratuit.
- **`avec_tags > 0`** → il faut **demander à chaque gestionnaire concerné** ce qu'il voulait
  obtenir. Ils sont probablement une poignée. Une migration de permutation ne se justifie que
  s'ils s'étaient adaptés au bug.

**Ne pas écrire de migration de données « au cas où » : elle casserait le cas le plus probable.**

## 7. Tests

Dans `tests/pytest/`, sur l'agenda fédéré :

- `tag_filter` non vide → **seuls** les events portant un de ces tags remontent (et non l'inverse) ;
- `tag_exclude` non vide → les events portant un de ces tags **ne remontent pas** ;
- les deux ensemble → l'intersection attendue ;
- les deux vides → tous les events du voisin remontent (non-régression) ;
- le matching se fait bien **par slug**, avec des objets `Tag` distincts dans chaque schéma ;
- fédération auto par tags (`FederationConfiguration.tags_federation`) → seuls les events
  portant ces tags remontent des tenants thématiques (non-régression après le passage de
  `tag_exclude` à `tag_filter`).

## 8. Effets de bord à surveiller

- **Le cache de l'agenda.** `federated_events_filter` cache la page 1 et les pages par date
  (`views.py:1894-1905`), avec un jeton de version par tenant réécrit à chaque `Event.save()`.
  Après correction, **les entrées en cache portent l'ancien comportement** jusqu'à expiration du
  TTL ou changement du jeton. Prévoir un vidage du cache au déploiement.
- `demo_data_v2.py` suit déjà la sémantique documentée : **rien à y changer**, il deviendra juste
  enfin cohérent avec le moteur.
