# Correctif : 500 sur la page Parametres / Fix: 500 on the Settings page

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** `/admin/BaseBillet/configuration/` renvoyait une **500** sur
les lieux dont le champ « Nom du collectif » est vide.
/ The Settings page returned a 500 on venues with an empty organisation name.

**Pourquoi / Why :** `Configuration.__str__` renvoyait `_('Settings')`.
`gettext_lazy` ne renvoie pas une chaine mais un objet paresseux
(`__proxy__`). Or Django appelle `str(objet)` pour fabriquer le sous-titre de
la page de modification (`django/contrib/admin/options.py`), et Python exige
alors une VRAIE chaine :

```
TypeError: __str__ returned non-string (type __proxy__)
```

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Configuration.__str__` : `str()` explicite sur les deux branches, + docstring expliquant le piege |
| `tests/pytest/test_configuration_str.py` | **neuf** — 3 tests de non-regression |

Aucune migration : seule une methode `__str__` change, pas un champ.

## Pourquoi le bug est reste invisible si longtemps

L'ancien code avait deux branches :

```python
if self.organisation:
    return _("Settings for ") + self.organisation   # marchait
return _('Settings')                                 # plantait
```

La **concatenation** de la premiere branche resout le proxy toute seule et
rend un vrai `str`. Seule la seconde branche etait cassee — donc seuls les
lieux **sans nom** declenchaient la 500. Sur les 6 lieux de la base de dev,
un seul est concerne (`meta`).

## Le correctif

```python
if self.organisation:
    return str(_("Settings for ")) + self.organisation
return str(_("Settings"))
```

Les `str()` sont mis sur les **deux** branches, meme si la premiere marchait :
laisser une branche implicite et l'autre explicite invite un futur lecteur a
« nettoyer » le `str()` qui semble superflu, et a reintroduire le bug. La
docstring de la methode explique le piege.

**Les `msgid` sont inchanges** (`"Settings"` et `"Settings for "`, tous deux
deja presents dans `locale/fr`) : aucune retraduction n'est necessaire, pas
de `makemessages` a lancer.

`str()` force la resolution au moment de l'appel, donc dans la langue active :
verifie, `fr` rend « Parametres » et `en` rend « Settings ».

## Portee du probleme

Un balayage AST de tout le depot (hors migrations et dependances) a cherche
les `__str__` qui retournent directement une chaine paresseuse :
**une seule occurrence**, celle-ci. Rien d'autre a corriger.

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_configuration_str.py -v
```

Les trois tests couvrent : lieu avec nom, **lieu sans nom** (la branche qui
plantait), et le maintien de la traduction.

Ces tests ont ete verifies contre l'ANCIEN code : deux d'entre eux echouent
bien dessus. Un test de non-regression qui passe aussi sur le code bugue ne
protege de rien.

Controle direct de la page :

```
/admin/BaseBillet/configuration/  ->  200   (500 avant le correctif)
```
