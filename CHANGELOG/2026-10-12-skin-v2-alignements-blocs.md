# Skin V2 : alignements des blocs de page / V2 skin: page block alignment fixes

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Corrections CSS du skin V2 sur les pages construites par blocs : sommaire aligné à gauche, sous-cartes avec un vrai padding, boutons de même taille et même hauteur, puces rendues aux listes des blocs texte, citation en romain avec son guillemet dans le cadre, pastilles de la frise centrées sur la ligne, boutons du pied de page moins massifs et sur une ligne en mobile.
/ V2 skin CSS fixes on block-built pages: ToC packed left, sub-cards padded, block buttons share size and height, bullets restored in text blocks, upright quote with its mark inside the frame, timeline dots centred on the line, lighter footer buttons that stay on one line on mobile.

**Pourquoi / Why :** Relecture visuelle du site de l'Université Populaire de Villeurbanne (premier site complet monté avec le constructeur V2) : boutons désalignés, textes collés aux bords des cartes, entrées du sommaire poussées à droite.
/ Visual review of the first full site built with the V2 page builder surfaced misaligned buttons, text touching card edges and right-pushed ToC entries.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/partials/bloc_liste.html` | **Passe 3** : la source EVENEMENTS rend le composant de l'accueil (`cotton/V2/agenda_a_venir.html` + `event_card.html`) : en-tête « Titre · N événements à venir » + « Tout l'agenda → », cartes et prix identiques à la section « Ce qui arrive » |
| `pages/templatetags/pages_tags.py` | **Passe 3** : tag `agenda_a_venir_du_bloc` — même source que l'accueil (`EventMVT.federated_events_filter()` : évènements du lieu ET des lieux fédérés), triés par date, avec prix et nombre total à venir |
| `BaseBillet/views.py` | **Passe 3** : calcul du libellé de prix des cartes extrait de `index()` dans `poser_prix_min_sur_evenements()`, partagé avec le bloc |
| `pages/templates/cotton/V2/agenda_a_venir.html` | **Passe 3** : paramètres optionnels `total`, `nombre_max`, `testid` (l'accueil garde son rendu : 3 cartes, compteur = liste reçue) |
| `pages/templates/cotton/V2/event_card.html` | **Passe 3** : domaine courant = `request.get_host` — sur une page CMS ou avec un paramètre d'URL, les évènements du lieu s'affichaient « via <domaine> » comme des évènements fédérés |
| `pages/static/V2/css/V2.css` (`.event-card__meta`) | **Passe 3** : `margin-top: auto` — « En savoir plus » et le prix à la même hauteur sur toutes les cartes d'une rangée |
| `pages/static/V2/css/V2.css` | **Passe 2 (équilibre optique)** : titre de page, fil d'Ariane et signature sur l'axe gauche du contenu (ils se centraient en se rétrécissant) ; bannière : carte en retrait dans l'image, titre à la taille d'un titre de page ; cartes d'évènement en 16/9 (plus de bandes grises) ; appel à l'action et newsletter encadrés comme des cartes (padding égal, fond papier au lieu du bleuté) ; sous-cartes en semi-gras ; frise limitée à 72 caractères |
| `pages/templates/pages/V2/partials/bloc_integration_newsletter.html` | Titre et sous-titre rendus par le gabarit (typographie du site) ; Ghost en variante minimale (champ + bouton, plus de cadre noir en Arial) ; bouton à la couleur des boutons du site |
| `pages/static/V2/css/V2.css` | **Passe 1** : Sommaire (`flex-start`, numéro à largeur fixe, sous-entrées alignées) ; sous-cartes (padding 4 côtés) ; boutons de bloc (taille + interligne communs aux deux variantes) ; listes `.tb-markdown` (puces) ; citation (romain, guillemet dans le cadre) ; frise (pastille centrée) ; `.btn--grad` (20 px max, 56 px de haut, sans soulignement) |

---

## Comment tester (a la main) / Manual test

Tenant local en skin V2 avec du contenu riche : `le-coeur-en-or` (site UPop recopié par l'API).

### Test 1 — sommaire
1. Ouvrir `https://le-coeur-en-or.tibillet.localhost/la-vie-de-l-upop/`.
2. Le sommaire à gauche : « 01 », « 02 » alignés en colonne, chaque libellé collé à son numéro. « Pourquoi une association ? » (sous-entrée) commence sous le libellé de l'entrée 01.

### Test 2 — boutons
1. Même page, bloc « Rejoindre l'UPop » : « Adhérer » et « Voir l'agenda » ont la même hauteur (44 px) et la même ligne de base.
2. Pied de page : « Créer un espace » / « Contribuer au projet » non soulignés, sur une ligne à 375 px.

### Test 3 — cartes, listes, citation, frise
1. `/qui-sommes-nous/` : les sous-cartes ont de l'air sur les quatre côtés ; les pastilles de « Notre histoire » sont centrées sur la ligne verticale.
2. `/upop-bar/` : les listes du texte ont des puces (disque, puis cercle pour le niveau 2).
3. `/la-vie-de-l-upop/` : la citation est droite (pas en italique), le guillemet bleu est dans le cadre gris.

### Test 4 — équilibre (passe 2)
1. `/qui-sommes-nous/`, `/vortex/` : le grand titre démarre au même bord gauche que les blocs (avant : centré).
2. Une sous-page (`/vortex-2025-09-15/`) : fil d'Ariane et titre alignés à gauche, l'un sous l'autre.
3. Accueil : la carte de la bannière est en retrait dans la photo, titre en grand ; cartes d'évènement sans bandes grises ; « Recevoir les nouvelles » et « Nous suivre » sont deux cartes papier séparées de 32 px, titre en Unbounded, formulaire Ghost réduit à champ + bouton bleu.

### Test 5 — bloc « Prochains rendez-vous » (passe 3)
1. Comparer `https://le-coeur-en-or.tibillet.localhost/` (bloc LISTE / EVENEMENTS) avec la section « Ce qui arrive » de `https://lespass.tibillet.localhost/` : même en-tête (titre · N événements à venir, « Tout l'agenda → »), mêmes cartes (pastille de date, lieu, tags, « par … », prix).
2. Les cartes d'une rangée ont « En savoir plus » à la même hauteur, avec ou sans tags.
3. Ajouter `?x=1` à l'adresse : les cartes disent toujours « par <lieu> », pas « via <domaine> ».
4. Lieu avec des lieux fédérés (`le-coeur-en-or` fédère `lespass` et `la-maison-des-communs`) : leurs évènements apparaissent dans le bloc, marqués « via <domaine> », et le compteur les inclut (27 en local le 2026-10-12).

### Test 6 — mobile
1. Dans l'inspecteur, largeur 375 px : aucun défilement horizontal, aucun bouton coupé.

### Verifs automatiques
- `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_marque.py -q` (aucune couleur en dur dans le CSS).
