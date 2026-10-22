# LaBoutik : addition de table et écran de la table choisie / Table bill and chosen-table screen

**Date :** 2026-10-22
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- **Écran d'une table choisie** : l'écran restaurant reste affiché, avec ses zones du
  bas, et il n'y a plus de bascule vers l'écran de vente direct. Un bandeau remplace
  l'en-tête « Ticket ». Il montre le nom de la table, son statut écrit avec la couleur
  du statut, et un bouton « Changer » qui ramène à la grille. Dessous, « Sur l'addition »
  se replie (`details` / `summary`, replié par défaut). Chaque ligne indique si elle
  est partie en préparation (coche) ou si elle est « à envoyer » (horloge, et une
  pastille « N à envoyer » dans le résumé). En mobile, une pastille de table
  s'affiche dans la bande du ticket replié. Une table inconnue ramène à la grille.
- **Addition de table (une Vente en attente)** : la touche « Ajouter à la table »
  poste vers `POST /laboutik/commande/ajouter_a_la_table/`.
  Le 1er envoi ouvre une `Vente` EN_ATTENTE, sans article ni règlement. Chaque envoi
  crée une `CommandeSauvegarde` rattachée à cette vente (`commande.vente`), et la table
  passe Occupée. Les retours de consigne, tarifs en points, tarifs au poids ou à prix
  libre, recharges, adhésions et billets sont refusés, sans rien écrire.
- **Paiement de la table** : avec une table choisie, les touches du bas encaissent
  l'addition et le panier en cours, même si le panier est vide. Les flux espèces, CB,
  chèque, offert, mixte, NFC et complément NFC reprennent la vente de l'addition au lieu
  d'en ouvrir une. Après l'encaissement, les commandes passent PAID et la table Libre.
  Le bandeau est mis à jour hors bande. `payer_commande` refuse une commande qui fait
  partie d'une addition. Après un paiement avec une table, le bouton OK de l'écran de
  succès (ou le fond) ramène à la grille des tables, pour choisir la suivante.
  Avec un panier vide, le champ `total` vide de `#addition-form` provoquait une 500 :
  le serveur ne le lit plus et prend le total calculé depuis les articles.
- **Carte TiBillet complétée par un autre moyen** (fonds insuffisants) : l'écran de
  succès affiche la répartition comme le paiement mixte, par exemple
  « paiement mixte (carte TiBillet 10.00 € · espèce 2.00 €) ». Les montants sont lus
  dans les règlements de la vente, et ceux de deux cartes sont additionnés.
- **Check carte** : la zone « Recharger » s'affiche toujours, dès que le point de
  vente est connu. La règle « la carte primaire doit avoir un PV cashless »
  (`_carte_primaire_a_un_point_de_vente_cashless`) est supprimée.
- **Envoi prépa** : `POST /laboutik/commande/envoyer_en_preparation/`. Si le panier
  n'est pas vide, il est d'abord ajouté à la table. Ensuite, les articles de la table
  qui ne sont pas encore partis passent EN_COURS. Après le commit, un ticket est
  imprimé par commande envoyée, découpé par imprimante de catégorie : c'est la tâche
  `imprimer_commande`, qui existait mais que rien n'appelait. Un 2e appui sans rien
  de nouveau répond « Rien à envoyer ».
- **Zone bas-droite** : les touches de paiement sont dans l'ordre des tuiles
  (Carte TiBillet, Espèces, CB, Chèque, Offrir, Mixte). On n'affiche que les moyens
  acceptés par le point de vente (Mixte dès deux moyens combinables, Offrir seulement
  en mode gérant). « Cashless » devient « Carte TiBillet ». Viennent ensuite Vider
  (confirmation en deux temps), et, avec une table, « Ajouter à la table » et
  « Envoi prépa ». « Ticket de caisse », les voyants Ventes / Note et VALIDER sont
  retirés.
- **Ticket en mode restaurant** : plus de boutons (Vider, Check carte, Valider). Le
  total reste affiché.
- **Zone bas-gauche** : « Poser carte » est retiré. « Vérifier carte » devient
  « Check carte ».
- **Bas du ticket** : le total reste visible dans la grille du mode restaurant. Le
  contenu du ticket défile.

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
| `laboutik/services_table.py` | Nouveau : addition de table (vente en attente, envois, articles à payer, résumé envoyé / à envoyer, envoi en préparation, reprise de la vente, clôture, refus) |
| `laboutik/views.py` | `point_de_vente` (écran resto avec table, bandeau, `paiement_mixte_possible`) ; actions `CommandeViewSet.ajouter_a_la_table` et `envoyer_en_preparation` (lecture du panier partagée) ; `mode_restaurant` ; `_articles_du_panier_et_de_l_addition` dans `moyens_paiement`, `_executer_paiement`, `_executer_paiement_complementaire`, `identifier_client` ; reprise de la vente de l'addition dans `_ouvrir_la_vente_de_caisse`, NFC et complément ; clôture après `payer` / `payer_complementaire` ; garde dans `payer_commande` |
| `laboutik/templates/laboutik/partial/_addition_de_table.html` | Nouveau : bandeau + « Sur l'addition » repliable (envoyé / à envoyer) |
| `laboutik/templates/laboutik/partial/_pastille_de_table.html` | Nouveau : pastille de la bande repliée |
| `laboutik/static/css/addition_table.css` | Nouveau : style du bandeau (variante B de la maquette) |
| `laboutik/templates/cotton/addition.html` | Bandeau à la place de l'en-tête, pastille mobile, champ `type_app` |
| `laboutik/templates/cotton/addition_footer.html` | Pas de boutons en mode restaurant (le total reste) |
| `laboutik/static/js/footer.js` | Sans `#addition-bt-valider` : rien à brancher ; pas de `displayPaymentTypes` sur « Ajouter à la table » |
| `laboutik/static/js/addition.js` | Une table qui doit de l'argent se paie avec un panier vide |
| `laboutik/templates/laboutik/partial/win_bottom_right.html`, `win_bottom_right.css` | Touches filtrées, ordre des tuiles, Carte TiBillet ; Vider, Ajouter à la table, Envoi prépa branchés ; Ticket, voyants et VALIDER retirés |
| `laboutik/templates/laboutik/partial/win_bottom_left.html`, `win_bottom_left.css` | « Poser carte » retiré, « Check carte », 3 actions |
| `laboutik/templates/laboutik/views/restaurant_interface.html` | Écran aussi avec une table ; panneau appui long + indicateur WebSocket |
| `laboutik/static/css/restaurant_interface.css` | Bas du ticket toujours visible (min-height: 0) |
| `tests/pytest/test_resto_addition_table.py` | Nouveau : 19 tests |
| `tests/pytest/test_resto_touches_et_tables.py` | Écran de la table : gabarit restaurant |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | `succesNouvelleVente()` : retour à la grille après le paiement d'une table |
| `laboutik/templates/laboutik/partial/hx_check_card.html`, `hx_card_recharge.html` | Documentation : la recharge s'affiche toujours |
| `tests/pytest/test_paiement_complementaire.py` | +1 test, +1 vérification : libellé de la répartition |
| `tests/pytest/test_retour_carte_recharge.py` | La recharge s'affiche sans PV cashless et sans carte primaire |

---

## Comment tester (a la main) / Manual test

Prérequis : PV « Terrasse » (`service_direct = False`, `accepte_commandes = True`).

### Test 1 — envoyer à la table
1. Choisir une table libre → bandeau « Nom · Libre », zones du bas visibles, bouton
   « Ajouter à la table » grisé.
2. Ajouter 2 articles → touche « Ajouter à la table » → popup « Ajouté à la table X ».
3. Retour → panier vidé, bandeau « Occupée », « Sur l'addition · 2 à envoyer · 2 articles · X € ».
4. Toucher « Sur l'addition » → les lignes apparaissent (horloge, « à envoyer »), sans bouton moins.
5. Admin → Ventes : une vente « En attente », sans numéro.
6. Touche « Envoi prépa » → popup « Envoyé en préparation ». Les lignes passent en coche,
   la pastille disparaît. Ticket imprimé sur l'imprimante de chaque catégorie qui en a une.
7. « Envoi prépa » à nouveau → « Rien à envoyer ».
8. Panier non vide + « Envoi prépa » → le panier est ajouté puis envoyé en une fois.

### Test 2 — payer la table
1. Panier vide, touche **Espèces** → les moyens de paiement montrent le total de
   l'addition → valider.
2. Vente réglée et numérotée. Le bandeau repasse « Libre », « Déjà envoyé » disparaît.
3. Recommencer avec un article dans le panier : il est encaissé avec l'addition.

### Test 2 bis — après le paiement, carte complétée, recharge
1. Payer une table → écran de succès → OK : la grille des tables s'affiche.
2. Sans table, payer un panier → OK : la caisse reste sur l'écran de vente, panier vidé.
3. Payer 15 € avec une carte qui n'a que 6 € → compléter en espèces : le succès affiche
   « paiement mixte (carte TiBillet 6.00 € · espèce 9.00 €) ».
4. Check carte depuis un PV, avec une carte primaire sans PV cashless : la zone
   « Recharger » est là.

### Test 3 — cas limites
- Retour de consigne, tarif au poids : « Ajouter à la table » refuse, rien en base.
- PV qui refuse le chèque : pas de touche Chèque. Un seul moyen : pas de Mixte. Carte
  sans mode gérant : pas d'Offrir.
- Sans table (« Continuer sans table ») : VALIDER fait un paiement direct, comme avant.
- `id_table` inconnu dans l'URL : la grille des tables s'affiche.
- 390 px : pastille de table dans la bande du ticket, actions bas-gauche sur une rangée.

### Verifs DB / Playwright
- `poetry run pytest tests/pytest/test_resto_addition_table.py tests/pytest/test_resto_touches_et_tables.py`
- Sélecteurs : `resto-addition-table`, `resto-addition-table-envoye`, `resto-addition-table-a-envoyer`,
  `resto-touche-envoyer-prepa`, `addition-vider`,
  `resto-addition-table-changer`, `resto-addition-table-pastille`,
  `addition-ajouter-a-la-table`, `resto-action-check-carte`.
- Aucun E2E encore : parcours « envoyer → payer » à écrire.
