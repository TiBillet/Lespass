# Bénévolat : corrections de la relecture complète (Opus + Fable) / Volunteering: full review fixes

**Date :** 2026-10-16
**Migration :** Non

## Resume / Summary
**Quoi / What :** corrections issues de deux relectures du module bénévolat (code et sécurité par Opus ; spec, UX et vue d'ensemble par Fable), et d'une vérification mobile en 375 px.
/ Fixes from two reviews of the volunteering module and a 375 px mobile check.

### Sécurité / Security
- **XSS stockée dans les toasts (toute l'appli)** : l'écouteur des toasts (`appToast`, `panierToast`) passait le texte à SweetAlert en `title`, que SweetAlert interprète comme du HTML. Un prénom piégé (`<img onerror=…>`) s'exécutait chez l'admin qui inscrivait la personne. Passé en `titleText` (texte brut). Aucun toast du projet n'envoie de HTML volontairement.
- `lettre` (POST anonyme) vérifie maintenant le jeton CSRF, comme le désistement.
- La règle « admin du lieu » de l'inscription par l'équipe est celle de l'admin du projet (`TenantAdminPermissionWithRequest`) : superuser accepté, admin inactif refusé.
- Limite assumée et écrite dans la spec : « Créer et inscrire » avec l'email d'un compte d'un autre lieu montre à l'équipe le nom que porte ce compte.

### Correction / Fixes
- Deux retraits simultanés de la même inscription ne préviennent l'équipe qu'une fois (suppression comptée par la base).
- Un mail de rappel qui lève une erreur est journalisé sans bloquer les rappels suivants du lieu.
- Un besoin qui change de jour ou d'heures retrouve son rappel de la veille (`rappel_envoye_le` vidé).
- Email marqué en erreur : le compte n'est plus rattaché au lieu (transaction annulée).
- API : une date impossible (30 février) → 400 au lieu de 500 ; un nom de tâche sur deux lignes → 400 (il cassait le sujet des mails).
- Admin « Répéter » : période modèle de 31 jours au plus ; une adresse bricolée → 404.
- Page d'accueil : le bloc « Coups de main » ne charge plus les plannings terminés depuis longtemps.

### UX / UI
- Les deux gestes qui envoient un mail à quelqu'un d'autre demandent confirmation : « Inscrire » (équipe, avec nom et email) et « Je ne peux plus venir » après le délai. « L'équipe sera prévenue » est écrit en clair.
- Dans la fenêtre de l'équipe, la confirmation passe par la boîte native : celle de SweetAlert (skin V2) se dessinait sous le `<dialog>`, invisible et impossible à cliquer.
- Toast de l'équipe avec l'email (homonymes). Session expirée : le panneau de connexion s'ouvre.
- Mail « l'équipe t'a inscrit·e » : « ton prénom est affiché sur le planning public ». Sujet de confirmation daté.
- Page de désistement : un message clair si la page a expiré (au lieu d'une page blanche).
- Mobile : dates « Dimanche 18 octobre » (plus de majuscule à chaque mot), 5 jours sur une ligne dans la carte d'accueil, vrais boutons dans « Mes créneaux ».
- Desktop : dégradé sur le bord droit de la grille (indice de défilement), dates en toutes lettres.
- État vide sans légende, légende groupée, grille annoncée comme région, compteur sans `aria-live` recréé (le toast annonce), lien « Voir la page publique » dans l'admin.

### DA v7.1 / Visual identity v7.1
`booking/static/booking/css/benevolat.css` suit la DA TiBillet v7.1 (fichier `tibillet_v7_1.html` fourni par le mainteneur) : bouton principal bleu ciel `#86ceff` (texte encre), secondaire blanc bordé `#ded7cd`, liens encre gras soulignés de bleu `#006cb5`, champs de 44 px au contour 1,5 px `#988264` (recherche en pilule), badges et pastilles bordés de `#988264`, cartes papier `#faf8f5` bordées de brume `#ece7e1`, coins de 14 px, plus d'ombre. Les valeurs sont écrites dans le fichier : le `V2.css` du dépôt ne porte pas encore la v7.1.

### Laissé tel quel / Left as is
- Le bloc « Rappel » vouvoie : sa traduction vient du `.po`, partagée avec la page évènement.
- Pas de limite de fréquence sur la lettre ni sur les inscriptions (D13).

### Fichiers modifies / Modified files
`BaseBillet/templates/htmx/components/panier_scripts.html`, `booking/{models,benevolat,views_benevolat,tasks}.py`, `booking/templates/booking/benevolat/**`, `booking/static/booking/css/benevolat.css`, `Administration/admin/benevolat.py`, `api_v2/{serializers,views}_benevolat.py`, tests (`tests/pytest/test_benevolat_*.py`, `booking/tests/test_benevolat_repetition.py`, `tests/e2e/test_benevolat_flow.py`), spec.

Tests : 265 pytest et 6 E2E du bénévolat ; chaque correction vérifiée par mutation (13 mutations, toutes détectées).
i18n : nouvelles chaînes traduisibles (msgid en français), workflow i18n à lancer par le mainteneur.

## Comment tester (a la main) / Manual test
1. Mettre `<b>gras</b>` comme prénom d'un compte du lieu, l'inscrire par « Inscrire quelqu'un » : le toast affiche les balises en texte, rien n'est en gras.
2. « Inscrire » dans la fenêtre de l'équipe : une boîte de confirmation (navigateur) apparaît au-dessus de la fenêtre ; « Annuler » n'inscrit personne.
3. Sur un créneau proche (délai passé) : « Je ne peux plus venir » demande confirmation.
