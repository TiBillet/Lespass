# La N+1 silencieuse des `list_sections` / The silent N+1 in list_sections

**Date :** 2026-09-09
**Migration :** Non

## Resume / Summary

**Quoi / What :** une changelist portant des sections coutait une requete SQL
par ligne et par section, meme si personne ne depliait jamais rien. Deux de ces
requetes sont supprimees.
/ A changelist with sections cost one query per row per section, even when
  nobody expanded anything.

**Mesure :** `/admin/BaseBillet/event/` passe de **75 a 55 requetes** pour 21
lignes (une changelist sans section en coute 19).

## Une correction de plan, au passage

Le plan de restylage annoncait « rendre les `list_sections` repliables ». **Cette
affirmation etait fausse** : `unfold/templates/admin/change_list_results.html:15`
porte deja `x-data="{rowOpen: false}"` et un chevron `expand_more` qui pivote.
Les sections sont repliees et fermees par defaut depuis toujours. La docstring
de notre propre `SousPagesSection` le disait d'ailleurs.

Le vrai defaut etait ailleurs, et il ne se voyait qu'en comptant les requetes.
/ The plan claimed sections needed collapsing; they were already collapsed. The
  real defect was a query cost, visible only by counting.

## La cause

`{% render_section %}` est **a l'interieur de la boucle sur les lignes**, et
`x-show="rowOpen"` ne fait que **cacher cote navigateur** du HTML deja produit.
Le serveur rend donc toutes les sections de toutes les lignes, a chaque
affichage.

Deux sections interrogeaient la base une fois par ligne :

| Section | Ce qu'elle faisait | Correctif |
|---|---|---|
| `ChildActionsSummaryTable` | `children.exists()` par ligne, juste pour decider de se masquer | annotation `section_children_count` dans `EventAdmin.get_queryset()` |
| `SousPagesSection.nb_blocs` | `blocs.count()` **par sous-page** — une N+1 imbriquee | property annotee `Page.enfants_pour_section` |

Les deux gardent un **repli defensif** : hors changelist annotee (fiche, appel
direct), l'ancien comportement reprend. Meme motif que
`EventPricesSummaryTable`, qui l'employait deja.

## Ce qu'on n'a PAS corrige, et pourquoi

`Event.pricesold_for_sections` (`BaseBillet/models.py`) est une **property** qui
construit un queryset filtre sur `self` : par construction, une requete par
evenement, impossible a precharger. La corriger demanderait de reecrire une
requete a fenetres (`Window` / `Count` / `Sum`) qui alimente un affichage
**comptable**. Le risque de regression sur des montants ne valait pas le gain.
Un **test de constat** fige ce cout restant pour qu'une aggravation se voie.
/ Deliberately kept; a characterization test pins the remaining cost.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `+ Count('children')` dans `EventAdmin.get_queryset()` ; la section lit l'annotation |
| `pages/models.py` | `+` property `enfants_pour_section` (annotee) |
| `pages/admin.py` | `related_name` pointe dessus ; `nb_blocs` lit l'annotation |
| `tests/pytest/test_admin_sections_requetes.py` | **neuf** — 6 tests |

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_sections_requetes.py -v
```

Deux corrections faites sur les tests eux-memes, qui valent d'etre notees :

- un premier test d'echelle etait **faux** — il mesurait aussi la requete gardee
  volontairement. Remplace par un test de constat ;
- deux tests **se sautaient** faute de sous-pages sur le lieu de dev. Ils creent
  desormais leurs donnees (transaction annulee) : **un test qui se saute ne
  protege rien**.
