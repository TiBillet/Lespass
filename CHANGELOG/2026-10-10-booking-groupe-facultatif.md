# Groupe de ressource facultatif, démo : accueil V2 et module réservation / Optional resource group, demo: V2 home and booking module

**Date :** 2026-10-10
**Migration :** Oui — suppression de `booking 0002_alter_resource_group` et `booking 0003_default_group`. `booking` repart de `0001_initial` seule. Pré-prod, et toute base de dev qui a joué 0002/0003 : flush (`flush.sh` / `demo_data_v2`). Sans flush, ces bases gardent `group_id` NOT NULL : créer une ressource sans groupe y lève une `IntegrityError`.

## Resume / Summary
**Quoi / What :**
- `Resource.group` redevient facultatif (`null=True, blank=True`). Les migrations `booking 0002` (groupe obligatoire) et `0003` (semis des groupes « Ressource » et « Espace ») sont supprimées. L'outil `supprimer_lieux_inactifs` ne tolère plus de groupes semés : un groupe garde le lieu, comme toute table non vide.
- Démo (flush) : la landing de `lespass` (`charger_site_lespass`) est créée en brouillon, la racine « / » sert l'accueil du skin V2. Le module réservation de ressources (`module_booking`) est activé dans tous les lieux de démo.

/ `Resource.group` is optional again; booking 0002/0003 are removed; the inactive-venue cleanup no longer tolerates seeded groups. Demo: lespass's landing page is a draft ("/" serves the V2 home), and the booking module is on in every demo venue.

**Pourquoi / Why :** `migrate_schemas` plantait en pré-prod (`column "group_id" of relation "booking_resource" contains null values`) : 0002 passait la colonne en NOT NULL avant que 0003 crée les groupes, sans jamais rattacher les ressources existantes. Le groupe ne sert qu'au rangement de l'affichage, et le front gère déjà les ressources sans groupe. `booking` n'est pas encore en production. La landing publiée de `lespass` doublonnait l'accueil V2.
/ The migration crashed on pre-prod. The group is display-only and `booking` is not in production yet. The published lespass landing duplicated the V2 home.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py` | `group` : `null=True, blank=True` |
| `booking/migrations/0002_alter_resource_group.py` | Supprimé |
| `booking/migrations/0003_default_group.py` | Supprimé |
| `Administration/nettoyage_des_lieux.py` | Retrait de la tolérance des 2 groupes semés |
| `tests/pytest/test_supprimer_lieux_inactifs.py` | Le test des groupes semés devient « un groupe garde le lieu, quel que soit son nom » |
| `booking/tests/conftest.py`, `test_booking_engine.py`, `test_timezone_slots.py`, `tests/pytest/fabriques_panier.py` | Les ressources de test n'ont plus de groupe |
| `pages/management/commands/charger_site_lespass.py` | Landing de `lespass` en brouillon (`publie=False`) |
| `Administration/management/commands/demo_data_v2.py` | `module_booking = True` ; la vérification des sites accepte un accueil non publié |
| `booking/management/commands/create_booking_fixtures.py` | Docstring mise à jour |
| `pages/templates/pages/{V2,classic,faire_festival}/shell.html` | `hx-vals` « skin_preview » posé seulement pendant un aperçu de skin (sinon chaque requête htmx ajoutait `?skin_preview=None` à l'URL) |
| `pages/templates/cotton/V2/ressource_card.html` | « Réserver » charge la page de la ressource (`hx-get` pointait vers `/memberships//`) et pousse son URL |
| `BaseBillet/views.py` | Libellé par défaut du menu adhésion : « Adhésion » (au lieu de « Adhésions & services ») ; `membership_menu_name` le remplace s'il est rempli |
| `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md`, `CHANTIER-05-briefs/PROMPT-ORCHESTRATEUR.md`, `CHANTIER-05-SUIVI.md` | Migrations de la branche : `booking` = `0001` seule |

---

## Comment tester (a la main) / Manual test
### Test 1 — migrations
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations booking --check --dry-run` → « No changes detected ».
2. Sur une base vide (flush) : `migrate_schemas` passe sans erreur.

### Test 2 — ressource sans groupe
1. Admin → Ressources → créer une ressource sans groupe → enregistrement accepté.
2. Page publique des ressources → la ressource apparaît en tête, hors de tout groupe.

### Test 3 — démo après flush
1. `https://lespass.tibillet.localhost/` → accueil du skin V2 (pas la landing du moteur de pages).
2. Admin → Pages → « Accueil » est en brouillon ; un admin du lieu la prévisualise sur `/accueil/`.
3. Chaque lieu de démo : l'entrée « Ressources » est dans la navbar, et le module est actif sur `/admin/module/ressources/`.
4. Sortie du flush : `Sites web de demonstration : ✓ lespass …`.
5. Un lieu sans « Nom de la page adhésion » en config (ex. `le-coeur-en-or`) : la navbar affiche « Adhésion ».
6. Navbar → « Ressources » : l'URL est `/booking/`, sans `?skin_preview=None`. « Réserver » sur une carte → page de la ressource, URL `/booking/<id>/resource/`.
7. Aperçu de skin depuis l'admin (`/?skin_preview=V2`) : la navigation htmx garde le paramètre et le bandeau d'aperçu.
