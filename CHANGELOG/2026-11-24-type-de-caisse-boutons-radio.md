# Type de caisse : boutons radio avec description / POS type: radio buttons with description

**Date :** 2026-11-24
**Migration :** Non

## Resume / Summary
**Quoi / What :** dans l'admin d'un point de vente, le champ « Type de caisse » devient une liste de boutons radio. Chaque choix a sa description juste en dessous. Seuls Direct, Cashless et Billetterie sont proposés. Un point de vente existant en « Adhésions » ou « Avancé » garde son type.
/ In the point of sale admin, "POS type" becomes a radio list with a description under each choice. Only Direct, Cashless and Ticketing are offered. An existing POS keeps a non-offered type.

**Pourquoi / Why :** l'aide regroupait toutes les descriptions sous le select, avec du jargon (« M2M »). Elle annonçait aussi un chargement automatique des adhésions qui n'existe pas : « Adhésions » se comporte comme « Direct ». « Avancé » n'est pas codé, et le point de vente d'une tireuse est créé tout seul avec la tireuse. Issue LaBoutik #114.
/ The help text listed every description under the select, with jargon, and promised a membership auto-loading that does not exist. "Advanced" is not coded; a tap's POS is auto-created. LaBoutik issue #114.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/laboutik.py` | `RadioAvecDescriptionWidget`, `DESCRIPTIONS_DES_TYPES_DE_POINT_DE_VENTE`, champ `comportement` dans `PointDeVenteForm` |
| `Administration/templates/admin/widgets/radio_option_avec_description.html` | Nouveau : un choix radio avec sa description (`aria-describedby`, `data-testid="radio-choix-<valeur>"`) |
| `tests/pytest/test_admin_point_de_vente_type.py` | Nouveau : 4 tests |

---

## Comment tester (a la main) / Manual test

### Test 1 — création
1. Admin > Caisse > Points de vente > Ajouter.
2. « Type de caisse » affiche 3 boutons radio : Direct, Cashless, Billetterie.
3. Chaque choix a sa description en dessous. « Direct » est coché par défaut.
4. Enregistrer avec « Cashless » : le point de vente est bien en Cashless dans la liste.

### Test 2 — point de vente existant avec un type retiré
1. En shell, passer un point de vente en `comportement="A"` (Adhésions).
2. L'ouvrir dans l'admin : un 4ᵉ choix « Memberships » est présent et coché, sans description.
3. Enregistrer sans rien changer : le type reste `A`.

### Test 3 — tireuses
1. Les points de vente de type tireuse restent absents de la liste admin des points de vente et du choix des points de vente d'une carte primaire.

### Tests automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_admin_point_de_vente_type.py -q`
