# Bénévolat : un module à part dans le tableau de bord / Volunteering: its own admin module

**Date :** 2026-10-16
**Migration :** Oui — `BaseBillet/0231_configuration_module_benevolat.py` (`Configuration.module_benevolat`, défaut `False`)

## Resume / Summary
**Quoi / What :** le bénévolat a sa carte « Bénévolat » dans le tableau de bord (groupe « Espace en ligne »), qu'on active comme les autres modules. Allumé, il a son bloc dans la barre latérale : Plannings bénévoles, Tâches bénévoles, Inscriptions bénévoles (ces entrées quittent « Réservation de ressources »). Le raccourci « Mes créneaux bénévoles » de « Mon compte » dépend aussi de ce module.
/ A "Bénévolat" module card; its sidebar block; the "My shifts" shortcut depends on it.

**Pourquoi / Why :** le mainteneur ne trouvait pas les pages du bénévolat dans le menu, et veut les tester comme un module. Décision P7 de la spec revue. Comme `/booking/`, les pages publiques ne vérifient pas le module.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py`, `BaseBillet/migrations/0231_…` | `Configuration.module_benevolat` |
| `Administration/admin/dashboard.py` | Carte `MODULE_FIELDS["module_benevolat"]`, bloc de la barre latérale |
| `pages/templates/pages/{V2,classic}/vues/compte/index.html` | Raccourci « Mes créneaux » sous `module_benevolat` |
| `tests/pytest/test_benevolat_module.py` | 6 tests (défaut, carte, bloc allumé / éteint, menu du site, page liste), vérifiés par mutation |
| `BaseBillet/views.py` | Entrée « Bénévolat » du menu du site (`main_nav`), module allumé seulement (ajout du 2026-10-17) |
| `booking/views_benevolat.py`, `booking/urls.py`, `booking/templates/booking/benevolat/liste.html` | Page `/booking/benevolat/` : les plannings à venir, en cartes (ajout du 2026-10-17) |
| `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` | P7 revue |

## Comment tester (a la main) / Manual test
1. Admin → Tableau de bord → « Découvrir plus de modules » → carte « Bénévolat » → l'activer.
2. Attendu : un bloc « Bénévolat » dans la barre latérale, avec les trois pages ; « Mon compte » montre « Mes créneaux bénévoles ».
3. Sur le site public, le menu montre « Bénévolat » → la liste des plannings à venir.
4. Le désactiver : le bloc, le raccourci et l'entrée du menu disparaissent.
