# Bénévolat, chantier 3 : « Mes créneaux », bloc d'accueil « Coups de main », lettre d'information / Volunteering, step 3: "My shifts", home block, newsletter

**Date :** 2026-10-16
**Migration :** Oui — `pages/0003_bloc_liste_coups_de_main.py` (nouveau choix de `Bloc.source`, libellés ; aucun SQL. `pages` est en SHARED_APPS et TENANT_APPS)

## Resume / Summary
**Quoi / What :**
- **« Mes créneaux bénévoles »** (`/my_account/my_volunteering/`) : mes inscriptions à venir, avec « Me retirer » ou « Je ne peux plus venir ». Raccourci dans « Mon compte » (V2 et classic), quand le module réservations est actif. Le mail de confirmation y renvoie.
- **Bloc d'accueil** : nouvelle source « Les prochains coups de main (bénévolat) » du bloc CMS « Liste automatique ». Une carte par planning publié qui a un besoin à venir : nom, période, places libres, 5 prochains jours colorés.
- **Lettre d'information** : bloc « Pas dispo cette fois ? » sous la grille, si le Ghost du lieu est configuré. `send_to_ghost_email` reçoit l'étiquette « Bénévolat », ajoutée aussi aux membres Ghost qui existent déjà.
/ "My shifts" page, "Coups de main" home block source, newsletter block with a Ghost label.

**Corrections issues d'une relecture Opus des chantiers 1 et 2 / Fixes from a review of steps 1-2 :**
- l'équipe n'est prévenue d'un retrait tardif que si l'inscription datait d'avant le délai (plus de faux désistement, plus de boucle de mails) ;
- une adhésion annulée n'ouvre plus un planning réservé ;
- prénom et nom : retour à la ligne refusé (il cassait le sujet du mail à l'équipe) ;
- début = fin refusé dans l'admin (créneau de 24 h par erreur) ;
- un refus envoyé depuis la fenêtre du nom la ferme ; un clic avec une session expirée affiche un toast ;
- admin : plus de requête par ligne de besoin (préchargement et cache des choix de tâche) ;
- accessibilité : le focus clavier reste sur le bouton de la case après un clic (id stable, sans `data-loading-disable`) ; noms accessibles des boutons de retrait et de connexion ; `data-testid` manquants ;
- l'écouteur 422 de la page ne s'applique qu'aux requêtes du planning ; `lang` et pluriels des mails.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `MyAccount.my_volunteering` |
| `BaseBillet/tasks.py` | `send_to_ghost_email(..., etiquettes_en_plus=None)` : étiquettes en plus, `PUT` pour un membre existant à qui il en manque |
| `booking/benevolat.py` | `resumes_des_plannings_a_venir`, `mes_creneaux_a_venir`, adhésions annulées exclues |
| `booking/views_benevolat.py` | `lettre`, retrait depuis « Mes créneaux », corrections de la relecture |
| `booking/urls.py` | Route `benevolat/<slug>/lettre/` |
| `booking/models.py` | `date_est_fermee` lit le préchargement ; `clean()` refuse début = fin |
| `booking/tasks.py` | Lien « Mes créneaux » dans le mail de confirmation |
| `booking/templates/booking/benevolat/` | `partials/{lettre,mes_creneaux,cartes_accueil}.html` ; corrections de `besoin.html`, `planning.html`, des mails |
| `booking/static/booking/css/benevolat.css` | Lettre, cartes d'accueil (`collectstatic` lancé en dev) |
| `pages/models.py`, `pages/migrations/0003_…` | Source `COUPS_DE_MAIN`, libellés et aides |
| `pages/templatetags/pages_tags.py` | Balise `plannings_benevoles_a_venir` (liste vide sur `public`) |
| `pages/templates/pages/{V2,classic}/partials/bloc_liste.html` | Branche `COUPS_DE_MAIN` |
| `pages/templates/pages/{V2,classic}/vues/compte/benevolat.html`, `…/index.html` | Page « Mes créneaux » et raccourci |
| `Administration/admin/benevolat.py` | Préchargement de l'inline, cache des choix de tâche |
| `tests/pytest/test_benevolat_chantier3.py` | 19 tests (compte, bloc, lettre, Ghost simulé) |
| `tests/pytest/test_benevolat_inscription.py`, `booking/tests/test_benevolat_models.py`, `tests/e2e/test_benevolat_flow.py` | Tests des corrections (CSRF, 404, 403, adhésion annulée, saisie, nombre de requêtes, focus) |

Tous les nouveaux tests ont été vus échouer sur une mutation volontaire.
i18n : nouvelles chaînes traduisibles (msgid en français), workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — Mes créneaux
1. S'inscrire sur `https://lespass.tibillet.localhost/booking/benevolat/bar-demo/`.
2. « Mon compte » → « Mes créneaux bénévoles ».
3. Attendu : le créneau est listé ; « Me retirer » fait disparaître la ligne, avec un toast.

### Test 2 — bloc d'accueil
1. Admin → Pages → une page → ajouter un bloc « Liste automatique », source « Les prochains coups de main (bénévolat) ».
2. Attendu : une carte par planning publié avec des besoins à venir, ses 5 prochains jours colorés, un lien vers le planning. En skin V2 et en skin classic.

### Test 3 — lettre d'information
1. Lieu avec Ghost configuré (adresse et clé).
2. Page du planning → bloc « Pas dispo cette fois ? » ; connecté·e, l'email est pré-rempli.
3. Envoyer un email invalide → message d'erreur. Un email valide → « C'est noté : … recevra la lettre d'information. »
4. Dans Ghost : le membre porte l'étiquette « Bénévolat » (ajoutée aussi s'il existait déjà).

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_benevolat_chantier3.py tests/pytest/test_benevolat_inscription.py booking/tests -q`
- `make e2e benevolat`
