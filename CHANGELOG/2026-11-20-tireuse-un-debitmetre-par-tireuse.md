# Tireuse : le débitmètre est rangé sur la tireuse / Tap: the flow meter lives on the tap

**Date :** 2026-11-20
**Migration :** Oui (`controlvanne` 0002 ajout et copie, 0003 suppression)

## Resume / Summary
**Quoi / What :**
- Le modèle du capteur et le facteur de calibration deviennent deux champs de la tireuse : `TireuseBec.flow_meter_model` et `TireuseBec.flow_calibration_factor` (6,5 par défaut). Ils se règlent sur la fiche de la tireuse.
- Le modèle `Debimetre`, son admin et son entrée de menu sont supprimés.
- Toute tireuse a maintenant un facteur : `ping` et `authorize` le renvoient toujours. La calibration fonctionne sur toutes les tireuses : le cas « aucun débitmètre associé » disparaît.
- Le tuto (`controlvanne/README.md`) perd l'étape « créer un débitmètre ».

/ The sensor model and calibration factor are now two fields of the tap. The `Debimetre` model, admin and menu entry are gone. Every tap has a factor: `ping` and `authorize` always return it, and calibration works on every tap. The tutorial loses its "create a flow meter" step.

**Pourquoi / Why :**
- Chaque capteur a son propre écart, et la calibration est propre à chacun. Un débitmètre partagé par plusieurs tireuses faussait la calibration des autres. Rangé sur la tireuse, le facteur ne peut plus être partagé.

/ Each sensor has its own error. A flow meter shared by several taps skewed the others' calibration. Stored on the tap, the factor can no longer be shared.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/models.py` | `flow_meter_model` et `flow_calibration_factor` sur `TireuseBec`. Classe `Debimetre` et champ `debimetre` supprimés. |
| `controlvanne/migrations/0002_debitmetre_sur_la_tireuse.py` | Ajoute les deux champs, copie le nom et le facteur de l'ancien débitmètre de chaque tireuse. |
| `controlvanne/migrations/0003_supprime_le_modele_debimetre.py` | Supprime le champ `debimetre` et le modèle `Debimetre`. |
| `controlvanne/viewsets.py` | `ping` et `authorize` : `"calibration_factor": tireuse.flow_calibration_factor`. |
| `controlvanne/calibration_views.py`, `templates/calibration/page.html` | Facteur lu et écrit sur la tireuse. Cas « aucun débitmètre » supprimé. |
| `controlvanne/admin.py` | `DebitmetreAdmin` supprimé. Les deux champs sur la fiche de la tireuse. |
| `Administration/admin/dashboard.py` | Entrée de menu « Débitmètres » supprimée. |
| `controlvanne/README.md` | Liste des modèles et tuto. |
| `tests/pytest/test_controlvanne_api.py`, `test_controlvanne_billing.py`, `test_controlvanne_ecran_calibration.py` | Fixtures : facteur sur la tireuse. Test d'unicité du débitmètre retiré (sans objet). |

### Migration
- Deux migrations séparées : en Postgres, modifier des lignes puis la structure de la même table dans une seule transaction peut échouer (« pending trigger events »).
- Un débitmètre partagé donne ses valeurs à chacune de ses tireuses. Une tireuse sans débitmètre reçoit un modèle vide et le facteur 6,5.
- Le Pi ne change pas : la clé `calibration_factor` de `ping` et d'`authorize` garde son nom.
- Vérifiée en dev sur 28 schémas : débitmètre partagé à 7,1 copié sur ses deux tireuses, tireuses sans débitmètre à 6,5.

### Traductions / Translations
Plusieurs chaînes disparaissent (menu « Flow meters », message « Aucun débitmètre associé… »). Les nouveaux champs reprennent des chaînes déjà traduites. `makemessages` reste à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test
1. Admin → Tireuses → ouvrir une tireuse : les champs « Débitmètre » (modèle) et « Facteur de calibration » sont sur la fiche.
2. Le menu « Débitmètres » n'existe plus.
3. Bouton « Calibrer le débitmètre » : la page affiche le modèle et le facteur actuel. Une série appliquée change le facteur sur la fiche de la tireuse.
4. Badger une carte : la réponse d'`authorize` contient `calibration_factor` avec le facteur de la tireuse.
