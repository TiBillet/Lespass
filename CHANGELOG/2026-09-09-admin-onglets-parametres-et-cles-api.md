# Paramètres en onglets, et « Clés API » enfin atteignable
/ Settings as tabs, and "API keys" finally reachable

**Date :** 2026-09-09
**Migration :** Non

## Resume / Summary

**Quoi / What :** la page Paramètres range ses quatre sections en onglets, et
la barre d'onglets s'affiche enfin sur cette page — ce qui rend « Clés API » et
« Webhooks » atteignables autrement que par la recherche.
/ The Settings page groups its four sections into tabs, and its tab bar finally
  renders, making "API keys" and "Webhooks" reachable.

## Volet 1 — le bug : « Clés API » etait un cul-de-sac

Le groupe d'onglets `Paramètres / Clés API / Webhooks` existait, mais **la barre
ne s'affichait jamais sur la page Paramètres** — la seule des trois presente
dans le rail. Les deux autres pages n'etaient donc atteignables que par la
recherche.

Mesure avant/apres (`#tabs-wrapper` dans le HTML) :

| Page | Avant | Apres |
|---|---|---|
| `/admin/BaseBillet/configuration/` | **0** | 1 |
| `/admin/BaseBillet/formbricksconfig/` | **0** | 1 |
| `/admin/BaseBillet/externalapikey/` | 1 | 1 |
| `/admin/BaseBillet/webhook/` | 1 | 1 |
| `/admin/BaseBillet/formbricksforms/` | 1 | 1 |

### La cause

`unfold/templatetags/unfold.py`, `_get_tabs_list` :

```python
if isinstance(tab_model, str):
    if str(opts) == tab_model and page == "changelist":   # changelist SEULEMENT
        ...
elif isinstance(tab_model, dict) and str(opts) == tab_model["name"]:
    is_detail = tab_model.get("detail", False)
    if (page == "changeform" and is_detail) or ...
```

Une entree **ecrite en chaine** ne vaut que pour une *changelist*. Or
`Configuration` est un **singleton django-solo** : il rend un **formulaire** a
l'URL de liste. La chaine `"BaseBillet.configuration"` ne pouvait donc jamais
correspondre.

**Correctif** : une entree `{"name": ..., "detail": True}` a cote de la chaine,
dans `_onglets_hors_modules()`. Applique aux **deux** singletons du releve —
`Configuration` et `FormbricksConfig` — car corriger un cul-de-sac en laissant
l'autre n'aurait pas eu de sens.

## Volet 2 — les quatre onglets

Les quatre sections de `ConfigurationAdmin` existaient deja ; elles deviennent
des onglets, sur le modele de `PriceAdmin` (`Administration/admin/prices.py`),
seul precedent de `"classes": ["tab"]` dans le projet.

- la premiere section, **anonyme**, recoit un nom : Unfold n'accepte comme
  onglet qu'un fieldset portant `classes:["tab"]` **ET un nom** (filtre `tabs`).
  Sans nom elle se serait rendue **au-dessus** de la barre ;
- `'Options générales'` et `'Personnalisation'` etaient des **chaines brutes**,
  jamais vues par `makemessages` : elles passent en `_()` ;
- `autocomplete_fields = ['federated_with']` est **retire** : le champ n'etant
  dans aucun fieldset, l'autocompletion ne s'appliquait a rien.

**Aucun champ n'est ajoute ni retire.** Les 45 champs invisibles de
`Configuration` (cles d'API, modules, champs legaux) le restent : les exposer
est une decision distincte, deliberement hors de ce lot. Verifie : **24 champs
avant, 24 apres**.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `_onglets_hors_modules()` : entrees `detail` pour les deux singletons |
| `Administration/admin_tenant.py` | `ConfigurationAdmin.fieldsets` en onglets ; titres en `_()` ; `autocomplete_fields` mort retire |
| `tests/pytest/test_admin_configuration_onglets.py` | **neuf** — 6 tests |

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_configuration_onglets.py -v
```

Le test le plus important est generique :
`test_aucun_onglet_declare_n_est_inatteignable` echoue des qu'**un** modele cite
dans un groupe d'onglets ne rend pas la barre sur sa propre page. Il attrape la
classe entiere du bug, y compris sur un groupe ajoute demain, et y compris si
quelqu'un ajoute un singleton en oubliant l'entree `detail`.

Les 6 tests ont ete **rejoues contre le code d'avant** : ils echouent.
