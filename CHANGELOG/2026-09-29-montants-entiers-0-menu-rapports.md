# Les deux rapports rangés dans « Ventes & comptabilité » / Both reports in "Sales & accounting"

**Date :** 2026-09-29
**Migration :** Non

## Resume / Summary

**Quoi / What :** le menu « Ventes & comptabilité » de l'admin montre désormais les deux
rapports, l'un sous l'autre : « Rapport ventes en ligne » (clôtures `comptabilite`,
anciennement « Rapports ») puis « Rapport ventes caisse » (clôtures `laboutik`,
anciennement « Closures » dans la section de la caisse). L'entrée caisse n'apparaît que
si le module caisse est actif, avec la même permission qu'avant. Elle quitte la section
de la caisse : elle n'est pas dupliquée. /
The admin "Sales & accounting" menu now shows both reports, one under the other: online
sales report, then POS sales report (only when the POS module is on). The POS entry
leaves the POS section.

**Pourquoi / Why :** un usager ne trouvait pas ses ventes de caisse dans « Rapports » :
la clôture caisse était rangée ailleurs. En attendant la clôture unique (fiche F), on
range les deux ensemble, sans modifier les rapports. /
Users could not find their POS sales under "Rapports". Until the single closure
(sheet F), both are shelved together; the reports themselves are unchanged.

Chantier : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-0-menu-rapports.md` (décision D25).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | section « Sales & accounting » : « Rapport ventes en ligne » (icône `lock`) puis « Rapport ventes caisse » (icône `point_of_sale`, sous `if configuration.module_caisse`), puis « Entries » inchangé ; entrée « Closures » retirée de la section caisse ; clés `"laboutik.cloturecaisse"` de `DESCRIPTION_DES_PAGES` et `CATEGORIE_DES_PAGES` déplacées sous `# --- Ventes & comptabilite ---`, textes inchangés |
| `tests/pytest/test_menu_rapports.py` | nouveau : `test_menu_ventes_comptabilite_range_les_deux_rapports` |

### Tests vus échouer puis mutations / Tests seen failing, then mutations

Avant correctif (rouge prouvé par l'orchestrateur) :
```
E       AssertionError: La section Ventes & comptabilité doit lister le rapport en ligne puis le rapport caisse. Liens trouvés : ['/admin/comptabilite/cloturecaisse/', '/admin/BaseBillet/lignearticle/']
FAILED tests/pytest/test_menu_rapports.py::test_menu_ventes_comptabilite_range_les_deux_rapports
======================== 1 failed, 2 warnings in 0.59s =========================
```

Après correctif : `1 passed`. Voisins (`test_admin_tableau_de_bord.py`,
`test_admin_page_de_module.py`, `test_admin_fil_ariane_et_rail.py`,
`test_module_newsletter_activation.py`) : `74 passed`.

#### Mutations

Jouées par l'orchestrateur.

| Mutation du code de production (`Administration/admin/dashboard.py`) | Test qui tombe |
|---|---|
| inverser l'ordre : `items_ventes_et_comptabilite.append(` → `.insert(0,` | `test_menu_ventes_comptabilite_range_les_deux_rapports` (« Liens trouvés : ['/admin/laboutik/cloturecaisse/', '/admin/comptabilite/cloturecaisse/', …] ») |
| remettre l'entrée « Closures » dans la section caisse | idem (« Le rapport caisse est encore rangé ailleurs : ['Caisse & Restaurant'] ») |
| retirer la condition : `if configuration.module_caisse:` → `if True:` | idem (« Module caisse inactif : … Trouvé dans : ['Ventes et comptabilité'] ») |

Empreinte `sha256` du fichier identique avant et après les trois mutations.

### Traductions / Translations

Deux nouvelles chaînes `_()` (source FR), à passer dans `makemessages` / traduire en EN :
- « Rapport ventes en ligne »
- « Rapport ventes caisse »

L'ancienne chaîne « Closures » n'est plus utilisée par ce menu ; « Rapports » non plus.

---

## Comment tester (a la main) / Manual test

1. Ouvrir `https://lespass.tibillet.localhost/admin/` avec un compte admin
   (`admin@admin.com`).
2. Dans le rail, déplier « Ventes et comptabilité » (libellé FR de `Sales & accounting`) : « Rapport ventes en ligne »,
   puis « Rapport ventes caisse », puis « Entries ».
3. Cliquer sur chacun : les listes de clôtures en ligne et de clôtures caisse s'ouvrent.
4. Ouvrir la page du module Caisse (onglet « Analyser ») : « Closures » n'y figure plus.
   Sur la liste des clôtures caisse, le fil d'Ariane ne dit plus « Caisse & Restaurant »
   (même comportement que « Rapport ventes en ligne » et « Entries », section autonome).
5. Éteindre le module caisse dans le tableau de bord : « Rapport ventes caisse »
   disparaît du menu. Le rallumer.
