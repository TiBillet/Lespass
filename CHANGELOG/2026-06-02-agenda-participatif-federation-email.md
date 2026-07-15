# Agenda participatif → Fédération + récolte e-mail du proposeur anonyme

**Date :** 2026-06-02
**Migration :** Oui

## Ce qui a été fait

### 1. Déplacement des réglages (Lot A)
Les 3 réglages de l'agenda participatif quittent `Configuration` (et le dashboard des modules)
pour vivre sur **`FederationConfiguration`** (admin « Options de fédération ») :
- `module_agenda_participatif` (activation)
- `proposition_anonyme_autorisee`
- `tag_auto_proposition`

La **carte « Agenda participatif » du dashboard est supprimée**. La carte fédération est
renommée **« Fédération et agenda participatif »** avec une description FALC.

### 2. Récolte e-mail du proposeur anonyme (Lot B)
À l'**étape 1** du wizard (`/event/wizard/place/`), un visiteur **non connecté** doit saisir un
**e-mail obligatoire**. À la finalisation : `get_or_create_user(email, send_mail=False)` crée (ou
récupère) un compte **non validé** (`email_valid=False`, inactif) **sans envoyer l'OTP**.
L'évènement est lié à ce compte (`created_by`) et reste une **proposition modérée**.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | 3 champs déplacés vers `FederationConfiguration` |
| `BaseBillet/migrations/0217_*` | AddField ×3 → recopie par tenant → RemoveField ×3 |
| `Administration/admin_tenant.py` | fieldset « Agenda participatif » → `FederationConfigurationAdmin` |
| `Administration/admin/dashboard.py` | carte agenda supprimée ; carte fédération renommée + texte FALC |
| `BaseBillet/views.py` | usages → `FederationConfiguration` ; récolte e-mail (étape 1 + finalisation) |
| `BaseBillet/validators.py` | `WizardPlaceSelectSerializer` : champ `email_proposeur` |
| `.../event/wizard/_form_lieu.html` | champ e-mail conditionnel (anonyme) |
| `.../event/list.html` | bouton « Proposer » → `federation_config.*` |

## Tests à réaliser

### Prérequis : appliquer la migration
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

### Test 1 : dashboard
1. Aller dans l'admin → dashboard d'accueil.
2. **Vérifier** : plus de carte « Agenda participatif ». La carte fédération s'appelle
   **« Fédération et agenda participatif »** avec le texte FALC (mention de l'agenda participatif).

### Test 2 : admin « Options de fédération »
1. Aller dans `admin/BaseBillet/federationconfiguration/`.
2. **Vérifier** : un fieldset **« Agenda participatif »** avec 3 champs (Activer l'agenda
   participatif / Autoriser les propositions anonymes / Tag automatique).
3. Cocher « Activer l'agenda participatif » + « Autoriser les propositions anonymes ». Enregistrer.

### Test 3 : proposition par un visiteur anonyme
1. **Déconnecté**, aller sur `/event/`.
2. **Vérifier** : le bouton « Proposer un évènement » apparaît (car module ON + anonyme autorisé).
3. Cliquer → étape 1 : **un champ e-mail obligatoire** est affiché.
4. Valider **sans e-mail** → message d'erreur, on reste sur l'étape 1.
5. Saisir un e-mail + choisir un lieu → continuer → ajouter un évènement → envoyer.
6. **Vérifier** : page de remerciement. L'évènement n'est **pas** publié (proposition).

### Test 4 : modération admin
1. Admin → Évènements (filtre propositions en attente).
2. **Vérifier** : l'évènement proposé est présent, non publié, avec `created_by` = le compte créé
   depuis l'e-mail saisi.

### Test 5 : anonyme non autorisé / module OFF
1. Décocher « Autoriser les propositions anonymes » (module ON).
2. Déconnecté, accès direct à `/event/wizard/place/` → **redirigé vers la connexion**.
3. Décocher « Activer l'agenda participatif » → accès direct → **404**.

### Test 6 : visiteur connecté (non staff)
1. Connecté (compte sans droit de création), module ON.
2. **Vérifier** : bouton « Proposer », **pas** de champ e-mail (l'utilisateur a déjà un compte) ;
   l'évènement est lié à son compte, en proposition modérée.

## Vérifications en base
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell
```
```python
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import FederationConfiguration, Configuration

lespass = Client.objects.get(schema_name="lespass")
with tenant_context(lespass):
    fc = FederationConfiguration.get_solo()
    print("module:", fc.module_agenda_participatif)
    print("anonyme:", fc.proposition_anonyme_autorisee)
    print("tag auto:", fc.tag_auto_proposition_id)
    # Les champs ne doivent PLUS exister sur Configuration :
    print(hasattr(Configuration.get_solo(), "module_agenda_participatif"))  # False
```

## Compatibilité
- La migration `0217` recopie la valeur existante par tenant : un tenant qui avait activé
  l'agenda participatif (ancien champ `Configuration`) le garde activé sur `FederationConfiguration`.
- Aucun changement de logique de droits : staff publie directement, connecté/anonyme = proposition
  modérée. Le seul ajout est l'e-mail obligatoire pour l'anonyme.
- Tests automatisés : `tests/pytest/test_event_wizard_unifie.py` (8 tests, dont 2 nouveaux pour la
  récolte e-mail). Tous verts.

## i18n
Nouveaux textes `_()` à extraire (texte source FR) : label/aide du champ e-mail, messages d'erreur,
libellé + description de la carte dashboard. Lancer `makemessages` puis `compilemessages`.
