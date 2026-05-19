# Wizards de création et proposition d'évènement

**Chantier :** EVENT_WIZARD (cf. `TECH_DOC/SESSIONS/EVENT_WIZARD/`) + OTP (cf. `TECH_DOC/SESSIONS/OTP/`)

## Ce qui a été fait

Refonte de la création d'évènement sur `event/list` en wizard 2 étapes
(admin) + ajout d'un wizard public anonyme avec OTP email pour
permettre à tout visiteur de proposer un évènement soumis à modération.

Service OTP DRY (`AuthBillet/otp_service.py` + `otp_session.py`) réutilisable
pour de futurs flows (login OTP, SSO, migration onboard).

### Modifications principales

| Fichier | Changement |
|---|---|
| `AuthBillet/otp_service.py` | NOUVEAU — service stateless |
| `AuthBillet/otp_session.py` | NOUVEAU — helper session HTTP |
| `BaseBillet/models.py` | +Event.is_proposal |
| `BaseBillet/views.py` | +EventWizardAdmin, +EventWizardPublic |
| `BaseBillet/validators.py` | +4 serializers wizard |
| `BaseBillet/templates/reunion/views/event/wizard/` | NOUVEAU (9 templates) |
| `Administration/admin_tenant.py` | +badge + filtre + action bulk |

## Tests à réaliser

### Test 1 : Wizard admin — adresse existante

1. Se connecter en admin (`admin@admin.com`).
2. Aller sur `/event/`.
3. Cliquer "Ajouter un évènement".
4. Garder "Utiliser une adresse existante", sélectionner l'adresse par défaut.
5. Cliquer "Continuer".
6. Remplir nom, date, description.
7. Cliquer "Créer l'évènement".
   - **Attendu** : redirection vers la page detail, toast succès, event apparait sur l'agenda.

### Test 2 : Wizard admin — nouveau lieu via carte

1. Sur step 1, basculer sur "Créer un nouveau lieu".
2. Saisir un nom de lieu (ex: "Salle des fêtes").
3. Utiliser la barre de recherche Leaflet pour trouver une adresse.
4. Déplacer le marqueur pour ajuster.
5. Vérifier que les 4 champs (rue, code postal, ville, pays) sont remplis automatiquement.
6. Cliquer "Continuer".
   - **Attendu** : PostalAddress créée en base avec `latitude` et `longitude` non null. Step 2 affiche le lieu en bandeau.

### Test 3 : Wizard public — flow complet

1. Se déconnecter (visiteur anonyme).
2. Sur `/event/`, cliquer "Proposer un évènement".
3. Saisir un email valide deux fois, soumettre.
4. Vérifier réception du mail (boite test).
5. Saisir le code à 6 chiffres, soumettre.
6. Choisir un lieu existant, soumettre.
7. Remplir nom + date + description.
8. Soumettre.
   - **Attendu** : page "Merci !", event créé avec `is_proposal=True, published=False`, n'apparait PAS sur `/event/`.

### Test 4 : Modération

1. Reconnexion admin.
2. Aller dans l'admin Django, vérifier le badge "+ 1" sur "Events" dans la sidebar.
3. Cliquer "Events", filtrer par "Proposals pending".
4. Cocher la proposition, lancer l'action "Approve and publish selected proposals".
   - **Attendu** : badge disparait, event devient visible sur `/event/`.

### Test 5 : Anti-spam

1. En anonyme, soumettre 3 demandes d'email consécutives en moins d'une heure.
   - **Attendu** : la 4e renvoie 429 (Throttle DRF).
2. Tenter de poster directement sur `/event/propose/event/` sans avoir fait l'OTP.
   - **Attendu** : redirection vers `/event/propose/email/`.

### Test 6 : Honeypot

1. Avec curl : `POST /event/propose/email/` avec `website=spam.example`.
   - **Attendu** : 422, pas d'email envoyé, aucune session OTP créée.

## Compatibilité

- Onboard inchangé : continue d'utiliser sa logique OTP custom.
- Les events existants restent `is_proposal=False` (défaut migration).
- L'ancien offcanvas a été retiré : tout test E2E le ciblant doit être adapté.

## Commandes de vérification en base

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from BaseBillet.models import Event
with schema_context('lespass'):
    print('Propositions en attente :', Event.objects.filter(is_proposal=True, published=False).count())
    print('Propositions approuvees :', Event.objects.filter(is_proposal=True, published=True).count())
"
```
