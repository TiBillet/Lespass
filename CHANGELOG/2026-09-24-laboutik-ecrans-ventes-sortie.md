# LaBoutik : écrans Ventes et Sortie de caisse aux couleurs de la nouvelle maquette / LaBoutik: Sales and Cash withdrawal screens follow the new mockup

**Date :** 2026-09-24
**Migration :** Non

## Resume / Summary

**Quoi / What :** les écrans **Ventes** (Ticket X) et **Sortie de caisse** reprennent la maquette
`TEMP-tibillet-laboutik-main/caisse` (`#viewVentes`, `#viewSortie`), en format tablette SUNMI D3 Mini
(1280 × 800) et terminal de poche SUNMI V2s (≤ 599 px). Le bouton retour du header est corrigé.
/ The Sales (Ticket X) and Cash withdrawal screens now follow the mockup, for both terminal formats.
The header back button is fixed.

**Pourquoi / Why :** c'étaient les deux derniers écrans de la maquette pas encore intégrés.
Ils gardaient les anciens onglets et environ 120 couleurs en dur.
/ They were the last two mockup screens not yet integrated.

### Écran Ventes / Sales screen
- **Chiffres du haut :** Total (nombre de ventes, date d'ouverture, TVA), Fond de caisse (entrées, sorties, solde) avec le bouton **Modifier**, et trois actions : Sortie de caisse, Imprimer Ticket X, Clôturer.
- **Mini-tableaux :** par moyen de paiement (avec le détail cashless), par point de vente, et TVA par taux.
- **Historiques :** trois boutons exclusifs. Un seul est ouvert à la fois, et re-cliquer le ferme.
  - Historique de vente (par article)
  - Historique de commande (filtres, scroll infini, clic sur une ligne → détail, réimpression, correction du moyen)
  - Synthèse par moyen
- **Chargement des historiques :** ils arrivent en HTMX dans `#detail-contenu`. Le template voit cette cible et ne renvoie que le tableau.
- **Fond de caisse :** c'est maintenant une popup `.card-modal` avec le pavé `c-numpad`. Après validation, l'écran se recharge et les chiffres sont à jour.
- **Clôture :** popup `.card-modal` qui reprend le texte de la maquette.
- **Supprimé :** les onglets « Toutes caisses / Par PV / Par moyen / Détail articles / Liste ventes ». Leur contenu est dans les mini-tableaux ou les historiques.

### Écran Sortie de caisse / Cash withdrawal screen
- Fond / Espèces / Solde, puis deux colonnes **Billets** et **Pièces** avec − / +.
- Carte du bas : total, Enregistrer, Imprimer et Ajouter une note.
  - **Imprimer** et **Ajouter une note** sont **désactivés**. Le clavier AZERTY de la note viendra plus tard, et l'impression d'une sortie n'est pas branchée côté serveur.
  - Le champ note n'est donc plus envoyé. Il est optionnel côté serveur.
- **Pas de « montant libre » ni « vider la caisse »** : le serveur n'accepte que des coupures.
- La validation JS (montant > solde, montant > espèces) est conservée.

### Header (bouton retour) / Header (back button)
- **Libellé :** « Caisse », comme dans la maquette.
- **Lien :** `url_retour_pv`, avec les 3 paramètres. Sans PV, on revient au premier PV de la carte primaire.
- **Titre centré :** « Ventes » ou « Sortie de caisse ». La nav est masquée sur ces écrans.
- **Depuis la Sortie de caisse, le retour ramène à Ventes.**
  - La zone est remplacée en `hx-swap-oob` par `_hdr_retour_zone.html`.
  - Ce remplacement n'a lieu que si la cible HTMX est `#ventes-zone`.
- **Corrigé :**
  - reste de la boucle des PV (`pv_item`, `data-testid="menu-pv-courant"`) ;
  - `onclick` qui ouvrait le burger ;
  - chevron hors du lien ;
  - variable `pv_actuelle` absente de certains contextes. Elle est supprimée : `url_retour_pv` la remplace.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/header.html` | Mode `retour_pv` : inclut `_hdr_retour_zone.html`, plus de burger ni de nav. |
| `laboutik/templates/laboutik/partial/_hdr_retour_zone.html` | **Nouveau.** Bouton retour (Caisse ou Ventes) et titre centré. Réutilisé en OOB. |
| `laboutik/templates/laboutik/partial/hx_recap_en_cours.html` | Réécrit : KPI, mini-tableaux, historiques, popup de clôture, JS `basculerHistorique()`. |
| `laboutik/templates/laboutik/partial/_ventes_historique_recap.html` | **Nouveau.** Tableaux « par article » et « synthèse par moyen ». |
| `laboutik/templates/laboutik/partial/hx_liste_ventes.html` | Historique de commande : filtres vers `#detail-contenu`, sans onglets. |
| `laboutik/templates/laboutik/partial/_ligne_vente.html` | **Nouveau.** Une ligne de commande, partagée par la page 1 et le scroll infini. |
| `laboutik/templates/laboutik/partial/hx_detail_vente.html` | Classes du nouveau tableau (`num`, `total-row`). |
| `laboutik/templates/laboutik/partial/hx_fond_de_caisse.html` | Popup avec pavé numérique. |
| `laboutik/templates/laboutik/partial/hx_sortie_de_caisse.html` | Réécrit : stats, billets / pièces, carte du bas, header OOB. |
| `laboutik/templates/laboutik/partial/_sortie_coupure_input.html` | Ligne `.denom-row` avec − / nombre / +. Mêmes `name` et `data-testid`. |
| `laboutik/templates/laboutik/partial/hx_sortie_succes.html` | Styles inline remplacés par des classes. |
| `laboutik/templates/laboutik/partial/hx_alerte_ventes_zone.html` | Nouveau conteneur `.ventes-body`. |
| `laboutik/templates/laboutik/views/ventes.html` | Commentaire de flux mis à jour. |
| `laboutik/static/css/ventes.css` | Réécrit depuis la maquette. Tokens uniquement ; V2s en `@media (max-width: 599px)`. |
| `laboutik/static/css/sortie_de_caisse.css` | Réécrit depuis la maquette. Tokens uniquement. |
| `laboutik/static/css/header.css` | `.hdr-retour-zone`, `.hdr-title`, `.hdr-spacer`, tailles V2s. |
| `laboutik/views.py` | `recap_en_cours` calcule toujours les KPI et `ventilation_par_pv`, sauf pour un fragment d'historique. Suppression de `pv_actuelle`. |

### Migration
- **Migration necessaire / Migration required :** Non

### Traductions / Translations
Nouvelles chaînes (`makemessages` non lancé) :
- « Caisse », « Modifier », « Historique de vente », « Historique de commande », « Synthèse par moyen »
- « Historique de vente par article », « Synthèse par moyen de paiement », « Par moyen de paiement »
- « Nouveau fond de caisse », « Fond de caisse mis à jour », « Billets », « Pièces », « Ajouter une note »
- « Imprimer (bientôt disponible) », « Retirer un … », « Ajouter un … », « Retour aux ventes »
- « Sortie de caisse enregistrée », « Aucune commande pour ces filtres », « Catégorie / Article », « Qté »

## Tests a realiser / Tests to run

Automatiques / Automated :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_menu_ventes.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_cloture_*.py tests/pytest/test_pos_*.py tests/pytest/test_caisse_*.py tests/pytest/test_laboutik_*.py -q
```

Manuels, à faire en 1280 × 800 puis en 360 × 720, à côté de la maquette :

### Test 1 : navigation et header
1. Dans la caisse, cliquer sur **Ventes**. Le titre centré doit être « Ventes », le retour doit afficher « ‹ Caisse », et la nav doit être absente.
2. Ouvrir **Sortie de caisse**. Le titre doit passer à « Sortie de caisse » et le retour à « ‹ Ventes ».
3. Cliquer sur « ‹ Ventes ». On revient à l'écran Ventes, et le header affiche de nouveau « Caisse ».
4. Cliquer sur « ‹ Caisse ». On revient à la caisse du bon PV, avec `tag_id_cm` et `type_app` dans l'URL.

### Test 2 : écran Ventes
1. Vérifier les KPI : total, nombre de ventes, TVA, fond, solde.
2. **Modifier le fond :** saisir au pavé, puis valider. La popup se ferme et le fond est mis à jour. La croix et le fond sombre ferment la popup sans rien enregistrer.
3. **Historiques :** ouvrir, fermer, puis basculer entre les trois.
   - Dans l'historique de commande, vérifier les filtres, le scroll infini et le clic sur une ligne (détail, réimprimer, corriger).
4. **Clôturer :** la popup s'ouvre, Annuler la ferme. Ne pas confirmer sur une base utile.
5. **Imprimer Ticket X :** le retour s'affiche sous les KPI.
6. Recharger la page (F5) avec `?vue=detail_articles`. L'historique doit être déjà ouvert.

### Test 3 : Sortie de caisse
1. Utiliser − / +, puis saisir un nombre au clavier. Le total doit suivre.
2. Saisir un montant supérieur aux espèces : un avertissement s'affiche, avec « Confirmer quand même ».
3. Saisir un montant supérieur au solde : une erreur bloquante s'affiche.
4. Enregistrer : l'écran de succès s'affiche, et « Retour aux ventes » ramène à l'écran Ventes.
5. Envoyer sans aucune coupure : une alerte s'affiche avec un bouton Retour.
