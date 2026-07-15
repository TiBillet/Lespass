# Wizards de création et proposition d'évènement

**Date :** 2026-05-19
**Migration :** Oui

**Chantier :** EVENT_WIZARD (cf. `TECH_DOC/SESSIONS/EVENT_WIZARD/`) + OTP (cf. `TECH_DOC/SESSIONS/OTP/`)

> ⚠️ **MISE À JOUR V2 (2026-05-21, CHANTIER-02)** : le flux a évolué. Le wizard
> public **n'utilise plus l'OTP** mais la **connexion classique**. Le choix de
> lieu se fait en **2 pages** (choix → carte). On peut proposer **plusieurs**
> évènements. **Utiliser les tests V2 ci-dessous** ; les tests MVP/OTP en bas de
> page sont **parqués** (l'OTP reviendra dans l'offcanvas de connexion).

## Ce qui a été fait

Refonte de la création d'évènement sur `event/list` en wizard multi-étapes
(admin + public). Choix de lieu en 2 pages, ajout de plusieurs évènements,
modération admin des propositions. Le service OTP DRY (`AuthBillet/otp_service.py`
+ `otp_session.py`) reste en place, parqué pour un futur offcanvas de connexion.

## Tests V2 (flux actuel — CHANTIER-02)

Pré-requis : être **connecté** (admin pour le wizard admin ; n'importe quel
compte pour le wizard public). Serveur byobu à jour (sinon `Event() got
unexpected keyword arguments: 'is_proposal'` = models.py périmé → relancer byobu).

### V2-1 : Wizard public — visiteur anonyme

1. Se déconnecter, aller sur `/event/`, cliquer « Proposer un évènement ».
   - **Attendu** : toast « Merci de vous connecter d'abord. » + l'offcanvas de
     connexion s'ouvre automatiquement (page `event-list?login=1`).

### V2-2 : Wizard public — connecté, lieu existant, multi-évènements

1. Connecté, aller sur `/event/propose/` → étape **Lieu** (page 1).
2. Toggle « Utiliser une adresse existante », filtrer dans la liste, sélectionner. « Continuer ».
3. Étape **Évènements** : remplir nom + date, « Ajouter à la liste » → l'évènement
   apparaît, le form se vide. Ajouter un 2ᵉ. Retirer le 1ᵉʳ avec ×.
   - **Attendu** : add/remove en HTMX sans rechargement ; erreurs de validation
     affichées sous le form (renvoi 200).
4. « Envoyer ma proposition ».
   - **Attendu** : page « Merci ! », N events créés `is_proposal=True, published=False, created_by=<moi>`, partageant le lieu choisi.

### V2-3 : Wizard public — nouveau lieu (carte page 2)

1. Page 1, toggle « Créer un nouveau lieu », saisir un nom. « Continuer ».
2. Page **Carte** : la recherche est pré-remplie avec le nom et **lancée
   automatiquement** ; les champs rue/CP/ville se remplissent. Ajuster le marqueur si besoin. « Continuer ».
   - **Attendu** : `PostalAddress` créée (lat/lng non null), puis étape Évènements.

### V2-4 : Wizard admin

1. Connecté admin, `/event/` → « Ajouter un évènement ». Mêmes 2 pages de lieu,
   puis étape Évènements avec en plus **jauge** + **tags**.
2. Ajouter 1+ évènement(s), finaliser.
   - **Attendu** : N events `published=True` ; 1 seul → redirection fiche, plusieurs → agenda.

### V2-5 : Plafond d'affichage (300+ adresses)

Sur un tenant avec >50 adresses : la liste n'en affiche que 50 + message « Tapez
pour filtrer ». La recherche trouve une adresse **au-delà** du plafond. L'item
sélectionné reste visible.

### V2-6 : Mobile

Sous 576px de large, le toggle « adresse existante / nouveau lieu » s'empile
**verticalement** (2 boutons pleine largeur).

### V2-7 : Modération

Identique au MVP (Test 4 ci-dessous) : badge sidebar, filtre « Proposals
pending », action bulk « Approve and publish ».

---

## Tests MVP (OTP) — ⚠️ flux PARQUÉ (conservé pour référence)

> Ces scénarios décrivent le flux OTP du MVP. **Plus actifs** depuis V2 (le
> wizard public exige une connexion classique). À ré-utiliser le jour où l'OTP
> est rebranché dans l'offcanvas de connexion.

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
