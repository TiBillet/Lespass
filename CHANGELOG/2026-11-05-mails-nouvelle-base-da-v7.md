# Tous les mails passent sur une base commune habillée avec la D.A. v7 / All emails move to one base dressed with the v7 brand kit

**Date :** 2026-11-05
**Migration :** Non

## Resume / Summary
**Quoi / What :** Les gabarits de mails envoyés par `CeleryMailerClass` étendent désormais `emails/base.html`, réécrite avec la D.A. v7 : fond sable à volutes, carte papier, ruban 5 couleurs, bouton pilule, polices système, compatibilité Outlook et mode sombre. Score « HTML Check » de Mailpit : 96 à 97,3 % pour chaque mail.
/ The 24 email templates now extend a rewritten `emails/base.html` (v7 brand kit, Outlook and dark-mode safe).

**Composants partagés / Shared components :** `emails/composants/` : `titre`, `bouton`, `message` (info, succès, alerte, erreur, avec icône PNG), `ligne` (récapitulatif), `espace`. Bénévolat : `booking/benevolat/emails/_creneau.html`.

**Contexte commun / Common context :** `contexte_commun_des_mails()` (BaseBillet/tasks.py), appelée par `CeleryMailerClass` avant chaque rendu : nom du lieu, **logo du lieu** (`Configuration.logo`, et non plus `Configuration.img` qui est l'image de fond), dossier des images, adresse du site, adresse de réponse. Le contexte de l'appelant passe par-dessus. Un gabarit est rendu même quand l'appelant ne donne aucun contexte (avant : le mail partait avec le seul texte brut). Dans le schéma public, c'est TiBillet qui parle (logo TiBillet, pas de Reply-To).
/ `CeleryMailerClass` adds the venue name, the venue LOGO (not the background image), image folder, site URL and reply address.

**Rappel des bénévoles groupé / Grouped volunteer reminder :** une personne inscrite à plusieurs créneaux le lendemain reçoit un seul mail qui les liste tous (journée entière d'abord, puis par heure). Chaque créneau garde son lien « Je ne peux plus venir ». Les inscriptions du mail sont toutes marquées `rappel_envoye_le`.
/ One reminder email per person listing all tomorrow's slots, each with its own withdrawal link.

**Mails de création d'espace / Onboarding emails :** le nom du lieu en création passe dans `nom_du_nouveau_lieu` (et plus `organisation`, qui est le nom de l'en-tête).

**Billets / Tickets :** l'heure de l'événement est affichée dans le fuseau du lieu ; le mail ne montre plus le logo TiBillet à la place de l'image d'un événement qui n'en a pas.

**Supprimés (inutilisés) / Removed (unused) :** `emails/legacy/welcome_email.html`, `ApiBillet/templates/mails/base.html`, `ApiBillet/templates/mails/pairing_terminal.html`.

**Ménage du code mort / Dead code cleanup :**
- Dans les tâches, les clés de contexte que plus aucun gabarit ne lit sont retirées : `image_url`, `image_url_place`, `objet`, `now`, `button_color` (et `config`, `reservation`, `contribution` là où elles ne servaient plus), avec les 13 calculs du logo qui les alimentaient (ils lisaient l'image de fond `Configuration.img`).
- `booking/tasks.py` : `_adresse_du_lieu_et_logo(config)` devient `_domaine_du_lieu()`.
- Supprimés : la tâche `send_payment_error_user` (jamais appelée) et son gabarit `emails/payment_error.html` ; le bloc `report_to_pdf` / `report_celery_mailer`, déjà neutralisé dans une chaîne, et son gabarit `mails/mail_rapport.html` (il visait `report/ticketz.html`, qui n'existe plus).
/ Unread context keys, logo computations, an uncalled task and a dead report block are removed.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/emails/base.html` | Réécrite (D.A. v7), blocs `texte_d_apercu`, `contenu`, `raison_du_mail` |
| `BaseBillet/templates/emails/composants/*.html` | Nouveaux composants |
| `BaseBillet/static/emails/icone-{succes,alerte,erreur}.png` | Nouvelles icônes des messages |
| `BaseBillet/tasks.py` | `contexte_commun_des_mails()`, branchée dans `CeleryMailerClass` ; contexte de `ticket_celery_mailer` enrichi |
| `booking/tasks.py` | `rappeler_les_benevoles_du_lendemain_du_lieu` : un mail par personne |
| `onboard/tasks.py` | Clé `nom_du_nouveau_lieu` dans le contexte HTML |
| 24 gabarits (BaseBillet, booking, crowds, onboard, AuthBillet, comptabilite, ApiBillet) | Migrés sur la base |
| `tests/pytest/test_benevolat_rappel.py` | Nouveau test du rappel groupé ; test des liens adapté |
| `tests/pytest/test_mail_reply_to.py` | Configuration simulée avec `logo=None` |

---

## Comment tester (a la main) / Manual test
1. Mailpit, rechercher `NOUVELLE BASE` : un exemple de chaque mail (26 envois).
2. S'inscrire à deux créneaux du lendemain avec le même compte, lancer `rappeler_les_benevoles_du_lendemain` : un seul mail, deux créneaux, deux liens de désistement.
3. Lieu avec un logo : il apparaît en haut du mail, à 48 px de haut. Lieu sans logo : le nom seul.

### Déploiement / Deployment
- `collectstatic` obligatoire (fond, icônes, logo TiBillet PNG).
- Redémarrer Celery (tâche de rappel modifiée).
- Workflow i18n : nouvelles chaînes françaises dans les gabarits.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_benevolat_rappel.py tests/pytest/test_mail_reply_to.py"`
