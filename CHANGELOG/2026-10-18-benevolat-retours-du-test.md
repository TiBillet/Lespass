# Bénévolat : retours du premier test / Volunteering: first test feedback

**Date :** 2026-10-18
**Migration :** Oui — `booking/0005_planning_actif_sans_dates.py` (`docker exec lespass_django poetry run python manage.py migrate_schemas`). Supprime `date_de_debut` et `date_de_fin` des plannings ; le reste ne touche que les libellés et la valeur par défaut.

## Resume / Summary
**Quoi / What :**
- un planning « Chaque semaine » n'a plus de premier ni de dernier jour : il crée ses créneaux **à partir d'aujourd'hui** ;
- la case « Publié » devient **« Actif »** et pilote deux choses : la page publique ET la création automatique. Inactif : invisible et plus aucun créneau créé. Réactivé : la création reprend le jour même ;
- les pauses (vacances, fermeture d'été) passent par le **calendrier des fermetures**, qui existe déjà ;
- 4 semaines ouvertes à l'avance par défaut (au lieu de 8) ;
- fiche du planning : la case « Actif » est le dernier champ ; dans la semaine type, la colonne s'appelle « Jour de la semaine » et affiche le jour en entier (« Vendredi »), la colonne « Jour » des plannings ponctuels reste une date ;
- admin : entrée de menu « Tâches bénévoles » retirée (une tâche se crée avec le bouton à côté du champ « Tâche » des inlines) ; « Nombre de personnes souhaité » devient « Nbr postes » ; dans l'inline des besoins, la colonne « Inscrit·es » ne montre que les prénoms (ou les 6 premiers caractères de l'email), et la colonne « Fermeture » disparaît (elle reste sur la page « Besoins »).
/ Weekly plannings have no start/end date anymore; "Active" drives both the public page and the automatic creation; breaks use the closures calendar; 4-week default horizon; lighter admin.

**Pourquoi / Why :** retours du mainteneur après son test des chantiers 7 et 8 (décision D35 de `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md`) : les deux dates faisaient double emploi avec le calendrier des fermetures, et le menu était trop chargé.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py`, `booking/migrations/0005_planning_actif_sans_dates.py` | Dates supprimées, `published` libellé « Actif », horizon 4, « Nbr postes », aide du calendrier |
| `booking/benevolat.py` | Création à partir d'aujourd'hui, seulement si le planning est actif ; étapes « période modifiée » retirées |
| `booking/tasks.py` | La tâche de nuit ne traite que les plannings hebdomadaires actifs |
| `Administration/admin/benevolat.py` | Champs de dates retirés ; inline : prénoms, sans « Fermeture » |
| `Administration/admin/dashboard.py` | Entrée « Tâches bénévoles » retirée du menu (et donc de la page du module) |
| `booking/tests/…`, `tests/pytest/…` | Tests des dates retirés ; tests « inactif », prénoms, bouton d'ajout de tâche |
| `booking/management/commands/create_booking_fixtures.py` | Données de démo : planning hebdomadaire « Bar associatif » (mer.–sam. 17h–20h et 20h–22h, « Grand ménage » le mercredi 10h–13h, calendrier des fermetures) et planning ponctuel « Festival » (un jeudi dans 3 mois : installation, soirées vendredi et samedi en runs de 2h de 16h à 4h, désinstallation lundi et mardi), 6 bénévoles de démo et leurs inscriptions. Créés une seule fois (relancer ne change rien) |
| `Administration/management/commands/demo_data_v2.py` | Module « Bénévolat » allumé sur les lieux de démo |

**Traductions :** `locale/fr/LC_MESSAGES/django.po` traduisait `msgid "Actif"` par « Action » (aussi faux dans la caisse et Fedow) : le `msgstr` vaut maintenant « Actif ». Les nouveaux msgid (« Nbr postes », « Jour de la semaine », aides d'« Actif » et du calendrier…) ne sont encore dans aucun `.po` : `makemessages`, traduction EN, puis `compilemessages`, à lancer par le mainteneur.

**Relecture Fable (2026-10-18) appliquée :** à la réactivation par la fiche, toutes les lignes remplissent aussi les semaines déjà ouvertes (une ligne ajoutée pendant la pause n'avait jamais ses créneaux) ; conséquence assumée : un créneau supprimé à la main dans ces semaines revient. Trois tests ajoutés (réactivation, longue pause, ligne modifiée pendant la pause), gardes inutiles retirées des fixtures, spec et `api_v2/GUIDELINES.md` à jour.

---

## Comment tester (a la main) / Manual test

### Test 1 — planning hebdomadaire
1. Fiche d'un planning : type « Chaque semaine », case « Actif » cochée. Enregistrer.
2. Semaine type : ajouter une ligne. Pour une nouvelle tâche, cliquer le bouton à côté du champ « Tâche ». Enregistrer.
3. Les créneaux sont créés à partir d'aujourd'hui, sur 4 semaines.

### Test 2 — désactiver
1. Décocher « Actif », ajouter une ligne, enregistrer : aucun créneau créé, page publique introuvable.
2. Recocher « Actif », enregistrer : la ligne ajoutée pendant la pause a ses créneaux à partir d'aujourd'hui, sans doublon pour les autres lignes.

### Test 3 — pause
1. Calendrier des fermetures : fermer une semaine dans le mois qui vient, le rattacher au planning.
2. Les créneaux créés ensuite sautent cette semaine (ceux déjà créés restent : P9).

### Test 4 bis — données de démo
```bash
docker exec -w /DjangoFiles lespass_django poetry run python manage.py shell -c "
from django_tenants.utils import tenant_context
from django.core.management import call_command
from Customers.models import Client
with tenant_context(Client.objects.get(schema_name='lespass')):
    call_command('create_booking_fixtures')"
```
- `/booking/benevolat/bar-associatif/` et `/booking/benevolat/festival/` : créneaux couverts, à moitié, vides, un renfort.

### Test 4 — inline d'un planning ponctuel
- Colonne « Nbr postes » ; colonne « Inscrit·es » : « 2/2 : Camille, jturbe » ; pas de colonne « Fermeture ».
- Le menu « Bénévolat » ne montre plus « Tâches bénévoles ».
