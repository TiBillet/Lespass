# Bénévolat, chantier 2 : page publique du planning, s'inscrire, se retirer / Volunteering, step 2: public planning page, sign up, withdraw

**Date :** 2026-10-16
**Migration :** Non (la migration du chantier 1 a été recréée en `booking/0003_benevolat.py` après le merge de `main`, qui apportait `0002_booking_custom_form`)

## Resume / Summary
**Quoi / What :** la page publique `/booking/benevolat/<slug>/` d'un planning : compteur (places couvertes, renforts, créneaux encore vides) avec sa jauge, grille jours × tâches sur ordinateur, liste par jour avec barre de jours sur téléphone, en-têtes de jours colorés du rouge au vert selon le remplissage. « Je viens », « Je viens aussi » (renfort), « Me retirer », « Je ne peux plus venir ». Une fenêtre demande le prénom et le nom s'ils manquent au compte. Mail de confirmation, et mail à l'équipe quand quelqu'un se retire après le délai.
/ The planning public page, sign-up, withdrawal, name dialog, confirmation email, team email on late withdrawal.

**Pourquoi / Why :** chantier 2 de `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` (§5.2 à §5.4).
/ Step 2 of the volunteering spec.

Choix techniques notables :
- chaque action remplace **toute la zone du planning** (compteur, grille, jours mobiles), pas la case seule : chaque besoin est affiché deux fois (desktop et mobile), et le site charge htmx 1.9.12, qui gère mal un `<th>` en hors bande. La spec est mise à jour ;
- la fenêtre du nom est un `<dialog>` natif, atteint par `HX-Retarget` ; `showModal()` place le curseur dans le premier champ ;
- les mails partent après le commit (`transaction.on_commit`) ; un double clic ne crée qu'une inscription et un seul mail ;
- styles rangés sous `.benevolat` et préfixés `bv-` : la page s'affiche dans les trois skins, qui ont chacun leurs `.btn` et `.badge`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/benevolat.py` | Nouveau : taux de remplissage, prénom public, plage horaire, droit d'accès (adhésions), construction de la grille et du compteur |
| `booking/views_benevolat.py` | Nouveau : `BenevolatViewSet` (`retrieve`, `inscrire`, `retirer`), serializer de la fenêtre du nom |
| `booking/urls.py` | Trois routes du bénévolat, avant `router.urls` (slug `book` protégé) |
| `booking/tasks.py` | `envoyer_confirmation_benevole`, `prevenir_l_equipe_d_un_desistement` |
| `booking/models.py` | `nombre_inscrits()` lit le préchargement (`len(all())`) au lieu d'une requête par besoin |
| `booking/templates/booking/benevolat/` | `planning.html`, `partials/{zone,compteur,grille,jours_mobile,besoin,fenetre_nom}.html`, `emails/{confirmation,desistement_equipe}.html` |
| `booking/static/booking/css/benevolat.css` | Nouveau (`collectstatic` lancé en dev) |
| `pytest.ini` | Famille E2E `benevolat` |
| `tests/pytest/test_benevolat_inscription.py` | 27 tests, vérifiés par mutation (15 mutations) |
| `tests/e2e/test_benevolat_flow.py` | 4 tests navigateur (sans rechargement, fenêtre, 422, mobile 375 px), vérifiés par mutation |
| `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` | Mécanisme htmx (zone + `HX-Retarget`), statut |

i18n : nouvelles chaînes traduisibles (msgid en français), workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

Un planning de démonstration existe sur `lespass` : `https://lespass.tibillet.localhost/booking/benevolat/bar-demo/`.

### Test 1 — visiteur sans compte
1. Navigation privée → la page du planning.
2. Attendu : les prénoms sont visibles, jamais d'email ni de nom de famille. Chaque besoin propose « Me connecter pour venir » ; un besoin couvert montre aussi le badge « Couvert ».

### Test 2 — s'inscrire et se retirer
1. Se connecter, ouvrir la page, cliquer « Je viens ».
2. Si le compte n'a pas de prénom ou de nom : la fenêtre « Comment on t'appelle ? » s'ouvre. Envoyer vide → messages d'erreur. Remplir → la fenêtre se ferme.
3. Attendu : la case montre « Toi » et « Tu y es », l'en-tête du jour change de couleur et de texte, le compteur bouge, un toast s'affiche, la page ne se recharge pas. Un mail de confirmation arrive.
4. « Me retirer » → la case redevient libre.

### Test 3 — retrait après le délai
1. Dans l'admin, mettre le délai du planning à 500 heures.
2. Sur la page : la case affiche « Je ne peux plus venir ». Cliquer.
3. Attendu : le retrait est fait, et un mail part à l'adresse du lieu (`Configuration.email`).

### Test 4 — planning réservé
1. Ajouter une adhésion requise au planning.
2. Attendu : un compte sans cette adhésion voit « Réservé aux adhérent·es », sans bouton.

### Test 5 — téléphone
1. DevTools en mode mobile (375 px).
2. Attendu : la barre de jours en haut, la liste par jour, aucun défilement horizontal de la page.

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_benevolat_inscription.py booking/tests -q`
- `make e2e benevolat`
