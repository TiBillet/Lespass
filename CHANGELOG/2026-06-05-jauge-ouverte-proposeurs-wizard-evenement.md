# Jauge ouverte aux proposeurs dans le wizard d'évènement / Gauge available to proposers in the event wizard

**Date :** 2026-06-05
**Migration :** Non

**Quoi / What :** dans le wizard de proposition d'évènement (agenda participatif), le champ
**« Jauge max »** était réservé au staff. Il est désormais proposé à **tout le monde** (anonyme,
membre connecté, staff). Une proposition non-staff qui renseigne une jauge la voit **appliquée à
l'identique du staff** : `jauge_max` + `show_gauge=True` + produit **FREERES** (billetterie de
réservation gratuite). L'évènement **reste une proposition modérée** (`is_proposal=True`) jusqu'à
validation admin. Sans jauge saisie : défaut du modèle (`50`) intact, `show_gauge=False`, aucune
billetterie greffée. La logique des **tags** (staff = création libre ; public = sélection parmi
l'existant) est **inchangée**.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/reunion/views/event/wizard/_events_inner.html` | Champ jauge + badge jauge affichés pour tous ; layout tags en `col-md-6` ; logique tags inchangée (`show_admin_fields`) |
| `BaseBillet/views.py` | `_creer_event_depuis_brouillon` : jauge appliquée pour tous (plus de `if est_staff else None`) |
| `BaseBillet/validators.py` | Docstring `WizardEventSerializer` mis à jour (jauge commune à tous) |
| `tests/pytest/test_event_wizard_unifie.py` | +1 test de non-régression (jauge non-staff appliquée + cas sans jauge) |

### i18n
- Aucune nouvelle chaîne (`« Jauge max (optionnel) »` / `« Jauge »` existaient déjà). Pas de `makemessages`.

---
