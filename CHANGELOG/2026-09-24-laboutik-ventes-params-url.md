# LaBoutik Ventes : les paramètres GET ne disparaissent plus de l'URL / LaBoutik Sales: GET params no longer vanish from the URL

**Date :** 2026-09-24
**Migration :** Non

## Resume / Summary

**Quoi / What :** sur l'écran Ventes (`/laboutik/caisse/recap-en-cours/`), l'URL perdait
parfois `uuid_pv`, `tag_id_cm` et `type_app`. Elle devenait `?vue=toutes&`.
/ On the Sales screen, the URL sometimes lost `uuid_pv`, `tag_id_cm` and `type_app`.

**Pourquoi / Why :** les onglets Ventes font un `hx-push-url` avec
`?vue=...&{{ params_ventes }}`. Le bouton **Fond de caisse** du Ticket X appelait
`fond-de-caisse/` **sans aucun paramètre**. Son bouton **Retour** rechargeait donc le
Ticket X avec `params_ventes` vide. L'URL avait encore l'air correcte (le Retour ne
pousse pas l'URL). Mais au clic suivant sur un onglet, l'URL poussée n'avait plus
aucun paramètre. D'où l'impression d'un bug aléatoire.
/ The Cash float button called `fond-de-caisse/` with no params. Its Back button then
reloaded Ticket X with an empty `params_ventes`, and the next tab click pushed a URL
without any param.

Autres pertes du même type corrigées / Other similar losses fixed :
- **Sortie de caisse** ne passait que `uuid_pv` : `tag_id_cm` était perdu au Retour,
  et aussi après validation d'une sortie (le formulaire POST n'envoyait que `uuid_pv`).
- **`type_app`** n'était jamais dans `params_ventes` : il disparaissait dès le premier onglet.

La query string est maintenant construite à un seul endroit :
`_construire_params_ventes(uuid_pv, tag_id_cm, type_app)` dans `laboutik/views.py`.
/ The query string is now built in one place.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Nouveau helper `_construire_params_ventes()` (avec `urlencode`). Utilisé par `fond_de_caisse`, `sortie_de_caisse`, `creer_sortie_de_caisse`, `_construire_contexte_ventes` (+ `url_retour_pv`). `sortie_de_caisse` passe `tag_id_cm` et `type_app` au template. |
| `laboutik/templates/laboutik/partial/hx_recap_en_cours.html` | Boutons Fond de caisse et Sortie de caisse : `?{{ params_ventes }}`. |
| `laboutik/templates/laboutik/partial/hx_sortie_de_caisse.html` | Champs cachés `tag_id_cm` et `type_app` dans `#form-sortie-caisse`. |
| `tests/pytest/test_menu_ventes.py` | Classe `TestParamsVentesPropages` (3 tests). |

### Migration
- **Migration necessaire / Migration required:** Non

## Tests a realiser / How to test

### Automatiques
```bash
poetry run pytest tests/pytest/test_menu_ventes.py tests/pytest/test_caisse_*.py tests/pytest/test_corrections_fond_sortie.py -q
```

### Test 1 : Fond de caisse (le scénario du bug)
1. POS → menu **Ventes**. L'URL contient `uuid_pv`, `tag_id_cm`, `type_app`.
2. Cliquer **Fond de caisse**, puis **Retour**.
3. Cliquer l'onglet **Par moyen**.
4. Attendu : l'URL garde `uuid_pv`, `tag_id_cm` et `type_app`.

### Test 2 : Sortie de caisse
1. Ventes → **Sortie de caisse** → saisir une coupure → valider.
2. Sur l'écran de succès, cliquer **Retour**, puis un onglet.
3. Attendu : l'URL garde les 3 paramètres. Le header affiche le bon PV.

### Test 3 : Retour au POS
1. Depuis Ventes, après les tests 1 et 2, cliquer « Retourner au point de ventes ».
2. Attendu : on revient sur le PV d'origine, avec la même carte primaire.
