# Formulaire event unifié (front) + fix image + options config

**Date :** 2026-06-01
**Migration :** Oui

> Spec : `TECH_DOC/SESSIONS/EVENT_WIZARD/CHANTIER-03-formulaire-unifie.md` · Plan : `PLAN-03-…`.
> Périmètre **frontend** (admin Django non touché). Vérifié dans Chrome (staff) + 6 tests pytch.

## Ce qui a été fait

- **Wizard unifié** `EventWizard` (front) → **un seul bouton** sur `/event` (remplace
  « Ajouter » staff + « Proposer » public). Routes `event-wizard-*`.
- **Staff** → event publié, champs jauge + tags. **Public** → proposition modérée + tag auto ;
  tags limités aux **existants**.
- **Fix image (#1)** : `_attacher_image_brouillon` migre le fichier temp → `images/`.
- **Flux #4** : popup SweetAlert si saisie en cours non ajoutée (Ajouter d'abord / Envoyer sans
  / Annuler).
- **Config** : `proposition_anonyme_autorisee` + `tag_auto_proposition` (fieldset « Agenda
  participatif »).

## Tests automatisés (6 verts)

```bash
KEY=$(docker exec -e TEST=1 lespass_django poetry run python manage.py test_api_key | tail -1)
docker exec -e TEST=1 -e API_KEY="$KEY" lespass_django poetry run pytest tests/pytest/test_event_wizard_unifie.py -v
```

## Tests manuels (Chrome)

### Déjà vérifié (staff connecté)
1. `/event` → **un seul** bouton « Ajouter un événement ». ✅
2. Wizard : Lieu → Événements, champs **Jauge + Tags + Image** présents (staff). ✅
3. Flux #4 : saisir un nom sans « Ajouter à la liste » + « Créer » → popup SweetAlert. ✅
4. Images des events affichées dans `/event`. ✅

### À vérifier par toi (mode public — en navigation privée / déconnecté)
1. **Module OFF** (`module_agenda_participatif`=False) : aucun bouton « Proposer » sur `/event`
   pour un visiteur ; le staff voit toujours « Ajouter ».
2. **Module ON + anonyme OFF** : un visiteur **non connecté** → le bouton mène à la connexion.
3. **Module ON + `proposition_anonyme_autorisee` ON** : un anonyme peut proposer → wizard
   accessible, **pas** de champs jauge ; tags = autocomplete sur l'existant ; à l'envoi, event
   créé en **proposition** (non publié, `is_proposal=True`) avec le **tag auto** + visible dans
   l'admin pour modération.
4. **Upload image en proposition** : l'image doit apparaître dans `/event` une fois la
   proposition validée/publiée (bug #1).

## Nettoyage effectué

Code mort de l'ancien flux **supprimé** (commit de la session) :
- `views.py` : classes `EventWizardAdmin`, `EventWizardPublic` + helpers
  `_creer_event_admin_depuis_brouillon`, `_creer_event_public_depuis_brouillon` + leur import.
- `validators.py` : `WizardEventAdminSerializer`, `WizardEventPublicSerializer`,
  `EventProposalEmailSerializer`.
- templates obsolètes : `admin_step*.html`, `public_step0_*.html`, `public_step2_event.html`.
- tests obsolètes : `test_event_wizard_admin.py`, `test_event_wizard_public.py`.

Templates **conservés** (réutilisés par `EventWizard`) : `public_step1_place.html`,
`public_step_map.html`, `public_done.html`, `step2_event.html`, `_events_inner.html`,
`_form_lieu.html`, `_form_carte.html`, `_base.html`.

`manage.py check` OK · 34 tests pytch verts · audit conformité djc OK.
