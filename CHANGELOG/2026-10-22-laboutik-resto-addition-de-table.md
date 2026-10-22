# LaBoutik : addition de table et écran de la table choisie / Table bill and chosen-table screen

**Date :** 2026-10-22
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- **Écran d'une table choisie** : l'écran restaurant reste affiché, avec ses zones du
  bas, et il n'y a plus de bascule vers l'écran de vente direct. Un bandeau remplace
  l'en-tête « Ticket ». Il montre le nom de la table, son statut écrit avec la couleur
  du statut, et un bouton « Changer » qui ramène à la grille. Dessous, « Déjà envoyé »
  se replie (`details` / `summary`, replié par défaut). En mobile, une pastille de table
  s'affiche dans la bande du ticket replié. Une table inconnue ramène à la grille.
- **Addition de table (une Vente en attente)** : le bouton du ticket devient
  « Ajouter à la table ». Il poste vers `POST /laboutik/commande/ajouter_a_la_table/`.
  Le 1er envoi ouvre une `Vente` EN_ATTENTE, sans article ni règlement. Chaque envoi
  crée une `CommandeSauvegarde` rattachée à cette vente (`commande.vente`), et la table
  passe Occupée. Les retours de consigne, tarifs en points, tarifs au poids ou à prix
  libre, recharges, adhésions et billets sont refusés, sans rien écrire.
- **Paiement de la table** : avec une table choisie, les touches du bas encaissent
  l'addition et le panier en cours, même si le panier est vide. Les flux espèces, CB,
  chèque, offert, mixte, NFC et complément NFC reprennent la vente de l'addition au lieu
  d'en ouvrir une. Après l'encaissement, les commandes passent PAID et la table Libre.
  Le bandeau est mis à jour hors bande. `payer_commande` refuse une commande qui fait
  partie d'une addition.
- **Zone bas-droite** : on n'affiche que les moyens acceptés par le point de vente
  (Mixte dès deux moyens combinables, Offrir seulement en mode gérant). « Ticket de
  caisse », les voyants Ventes / Note et VALIDER sont retirés.
- **Zone bas-gauche** : « Poser carte » est retiré. « Vérifier carte » devient
  « Check carte ».
- **Bas du ticket** : le total et les boutons restent visibles dans la grille du mode
  restaurant. Le contenu du ticket défile.

/ Chosen-table screen keeps the restaurant layout with a table banner and a collapsible
"already sent" block. The ticket button adds the cart to the table bill: one pending
`Vente` per table, one order per send. Payment keys settle the whole bill into that sale.
Bottom keys follow the POS accepted methods; obsolete keys removed.

**Pourquoi / Why :** Le mode restaurant n'enregistrait rien pour une table. `id_table`
était posté, mais aucune vue ne le lisait. La table choisie n'apparaissait que dans
l'en-tête, et les zones du bas disparaissaient.
/ Restaurant mode recorded nothing for a table; the chosen table was barely visible.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/services_table.py` | Nouveau : addition de table (vente en attente, envois, articles à payer, résumé, reprise de la vente, clôture, refus) |
| `laboutik/views.py` | `point_de_vente` (écran resto avec table, bandeau, `paiement_mixte_possible`) ; action `CommandeViewSet.ajouter_a_la_table` ; `_articles_du_panier_et_de_l_addition` dans `moyens_paiement`, `_executer_paiement`, `_executer_paiement_complementaire`, `identifier_client` ; reprise de la vente de l'addition dans `_ouvrir_la_vente_de_caisse`, NFC et complément ; clôture après `payer` / `payer_complementaire` ; garde dans `payer_commande` |
| `laboutik/templates/laboutik/partial/_addition_de_table.html` | Nouveau : bandeau + « Déjà envoyé » repliable |
| `laboutik/templates/laboutik/partial/_pastille_de_table.html` | Nouveau : pastille de la bande repliée |
| `laboutik/static/css/addition_table.css` | Nouveau : style du bandeau (variante B de la maquette) |
| `laboutik/templates/cotton/addition.html` | Bandeau à la place de l'en-tête, pastille mobile, champ `type_app` |
| `laboutik/templates/cotton/addition_footer.html` | « Ajouter à la table » (hx-post) quand une table est choisie |
| `laboutik/static/js/footer.js` | Pas de `displayPaymentTypes` sur le bouton « Ajouter à la table » |
| `laboutik/static/js/addition.js` | Une table qui doit de l'argent se paie avec un panier vide |
| `laboutik/templates/laboutik/partial/win_bottom_right.html`, `win_bottom_right.css` | Touches filtrées ; Ticket, voyants et VALIDER retirés |
| `laboutik/templates/laboutik/partial/win_bottom_left.html`, `win_bottom_left.css` | « Poser carte » retiré, « Check carte », 3 actions |
| `laboutik/templates/laboutik/views/restaurant_interface.html` | Écran aussi avec une table ; panneau appui long + indicateur WebSocket |
| `laboutik/static/css/restaurant_interface.css` | Bas du ticket toujours visible (min-height: 0) |
| `tests/pytest/test_resto_addition_table.py` | Nouveau : 13 tests |
| `tests/pytest/test_resto_touches_et_tables.py` | Écran de la table : gabarit restaurant |

---

## Comment tester (a la main) / Manual test

Prérequis : PV « Terrasse » (`service_direct = False`, `accepte_commandes = True`).

### Test 1 — envoyer à la table
1. Choisir une table libre → bandeau « Nom · Libre », zones du bas visibles, bouton
   « Ajouter à la table » grisé.
2. Ajouter 2 articles → « Ajouter à la table » → popup « Ajouté à la table X ».
3. Retour → panier vidé, bandeau « Occupée », « Déjà envoyé · 2 articles · X € ».
4. Toucher « Déjà envoyé » → les lignes apparaissent, sans bouton moins.
5. Admin → Ventes : une vente « En attente », sans numéro.

### Test 2 — payer la table
1. Panier vide, touche **Espèces** → les moyens de paiement montrent le total de
   l'addition → valider.
2. Vente réglée et numérotée. Le bandeau repasse « Libre », « Déjà envoyé » disparaît.
3. Recommencer avec un article dans le panier : il est encaissé avec l'addition.

### Test 3 — cas limites
- Retour de consigne, tarif au poids : « Ajouter à la table » refuse, rien en base.
- PV qui refuse le chèque : pas de touche Chèque. Un seul moyen : pas de Mixte. Carte
  sans mode gérant : pas d'Offrir.
- Sans table (« Continuer sans table ») : VALIDER fait un paiement direct, comme avant.
- `id_table` inconnu dans l'URL : la grille des tables s'affiche.
- 390 px : pastille de table dans la bande du ticket, actions bas-gauche sur une rangée.

### Verifs DB / Playwright
- `poetry run pytest tests/pytest/test_resto_addition_table.py tests/pytest/test_resto_touches_et_tables.py`
- Sélecteurs : `resto-addition-table`, `resto-addition-table-envoye`,
  `resto-addition-table-changer`, `resto-addition-table-pastille`,
  `addition-ajouter-a-la-table`, `resto-action-check-carte`.
- Aucun E2E encore : parcours « envoyer → payer » à écrire.
