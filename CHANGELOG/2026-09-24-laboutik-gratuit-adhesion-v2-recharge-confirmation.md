# LaBoutik : panier gratuit, parcours client en V2, confirmation des recharges / Free cart, V2 client flow, top-up confirmation

## A. Panier à 0 € : pas d'étape de paiement / 0 € cart: no payment step

**Quoi / What :** un billet gratuit (ou une adhésion à 0 €) faisait quand même choisir un moyen de paiement. Maintenant, après l'identification (scan ou email), la popup n'affiche qu'**un seul bouton VALIDER**. La vente est enregistrée avec le moyen « Offert » (`PaymentMethod.FREE`) : LigneArticle à 0 € et Ticket en `FREE`.
/ A free ticket or membership now shows a single VALIDATE button after identification, recorded as "Offered".

**Comment / How :**
- `identifier_client()` calcule `panier_est_gratuit` (total recalculé côté serveur, jamais lu du POST).
- La tuile `paiement-btn-gratuit` envoie `moyen_paiement=gift` directement vers `payer()`.
- `payer()` : nouvelle branche `gift`. **Garde serveur** : refus (400) si le total recalculé n'est pas 0. Sinon, même traitement qu'une CB (`_payer_par_carte_ou_cheque`). `MAPPING_CODES_PAIEMENT["gift"]` donne `FREE`.

## B. Parcours d'identification client en V2 (adhésion, billetterie, recharge panier) / V2 client identification flow

**Quoi / What :** l'écran de scan, le formulaire email et le récapitulatif du client utilisaient encore l'ancienne interface. Conséquences : CB et chèque affichaient 0 € dans la confirmation, et CASHLESS ouvrait une popup vide alors que la carte venait d'être scannée.

**Comment / How :**
- Scan : `hx_lire_nfc_client.html` utilise la popup V2 `c-V2.read-nfc`.
- Formulaire email/nom : même habillage `.card-modal` que les autres popups (champs et `data-testid` inchangés).
- **`hx_recapitulatif_client.html` est supprimé.** `identifier_client()` rend la popup de paiement normale (`hx_display_type_payment.html`) en mode `client_identifie` : nom, email, solde, détail des articles, puis **les mêmes tuiles qu'une vente normale**. Ces tuiles sont extraites dans l'include `partial/_tuiles_paiement.html`, et chacune reste un composant `c-V2.bt.paiement`.
  - L'identité du client (`email_adhesion`, `prenom_adhesion`, `nom_adhesion`, `tag_id`) est rangée dans `#addition-form` au chargement de la popup. Espèces, CB et chèque suivent donc exactement le parcours d'une vente normale (`confirmer` avec le total → `payer`). **Le « CB affiche 0 » est corrigé.**
  - Avec une carte déjà scannée, CASHLESS paie directement avec cette carte : pas de nouveau scan, pas de popup.
  - Les moyens de paiement sont recalculés par le serveur (`_determiner_moyens_paiement`).
- Fermer la popup de paiement (croix ou fond) remet l'URL de `#addition-form` sur `moyens_paiement` (`initUrlAddition()`). Avant, après un scan client, un nouveau VALIDER repartait vers `identifier_client`.
- Au passage : la tuile CHÈQUE de la vente normale envoie aussi le total à `confirmer`.

## C. « Adhésion SEPA » : tarifs en ligne exclus de la caisse / Online-only prices hidden at the POS

**Quoi / What :** il n'existe aucun moyen de paiement SEPA dans LaBoutik. Ce qui s'affichait, ce sont des **tarifs d'adhésion faits pour le parcours en ligne** : paiement récurrent (abonnement Stripe, prélèvement SEPA) ou validation manuelle. Ils sont maintenant exclus des tuiles (`_construire_donnees_articles`) **et** du panier (`_extraire_articles_du_panier` : un POST forcé est ignoré). Filtre : `recurring_payment=False, manual_validation=False`. Un produit qui n'a plus aucun tarif disparaît de la grille.

## D. Recharge depuis « Check carte » : confirmation en espèces / CB / chèque / Check-card top-up goes through confirmation

**Quoi / What :** sur l'écran « Recharger » du check carte, les tuiles ESPÈCE, CB et CHÈQUE payaient tout de suite. Elles ouvrent maintenant la même popup de confirmation que les autres paiements : pavé « Somme donnée / À rendre » pour les espèces, rappel du TPE pour la CB.

**Comment / How :** même mécanisme que le complément NFC (voir `2026-09-24-complement-nfc-confirmation.md`) :
- `hx_card_recharge.html` : les tuiles font `hx-get confirmer?method=…&total=…&recharge=1`. `#card-recharge-form` peut maintenant être soumis vers `payer()` (champ `moyen_paiement`, `hx-include` de `given_sum`). Le clic sur une tuile vide aussi un `given_sum` resté d'une vente précédente.
- `confirmer()` : `est_recharge`. `hx_confirm_payment.html` : si `est_recharge`, Valider soumet `#card-recharge-form`, et `#confirm` se ferme à la réponse.
- `payer()` (et la vue de commande qui lit aussi `given_sum`) : `given_sum` est arrondi (`int(round(float()))`). Le JS envoie `somme × 100`, qui peut être un nombre à virgule. Avant, `int()` plantait.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Filtre des tarifs en ligne (2 prefetch) ; `_rendre_popup_paiement_client_identifie()` ; `identifier_client()` rend la popup de paiement ; `payer()` : branche `gift` + garde ; `confirmer()` : `est_recharge` ; arrondi de `given_sum` (2 endroits) |
| `laboutik/templates/laboutik/partial/_tuiles_paiement.html` | **Nouveau** : tuiles de paiement (vente normale + client identifié, cashless direct, bouton gratuit) |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Mode `client_identifie` ; include des tuiles ; fermer → `initUrlAddition()` |
| `laboutik/templates/laboutik/partial/hx_recapitulatif_client.html` | **Supprimé** |
| `laboutik/templates/laboutik/partial/hx_lire_nfc_client.html` | Popup V2 `c-V2.read-nfc` |
| `laboutik/templates/laboutik/partial/hx_formulaire_identification_client.html` | Habillage V2 `.card-modal` |
| `laboutik/templates/laboutik/partial/hx_card_recharge.html` | Tuiles → `confirmer(recharge=1)` ; `#card-recharge-form` soumissible |
| `laboutik/templates/laboutik/partial/hx_confirm_payment.html` | Branche `est_recharge` |
| `laboutik/templates/cotton/V2/read_nfc.html` | Liste « Utilisé par » |
| `tests/pytest/test_billetterie_pos.py` | Classe `TestBilletGratuit` (4 tests) ; testid `paiement-btn-especes` |
| `tests/pytest/test_retour_carte_recharge.py` | 3 tests (tuiles → confirmation, `confirmer?recharge=1`, `given_sum` à virgule) |
| `tests/pytest/test_laboutik_tarifs_en_ligne_exclus.py` | **Nouveau** : 2 tests (tuile et panier sans tarif récurrent / validation manuelle) |
| `tests/PIEGES.md` | 9.38 réécrit (le récap client n'existe plus) |

### Tests à réaliser / How to test
1. **Adhésion payante** (PV Adhésions) : une adhésion à 10 € → VALIDER → « Scanner une carte TiBillet » → popup V2 « Approchez la carte » → scan → popup « Client identifié » avec le nom, le solde et le détail.
   - CB → la confirmation affiche **10,00 €** (plus 0).
   - CASHLESS → paiement direct avec la carte scannée, écran de succès (pas de popup vide).
   - La croix → retour à la caisse ; un nouveau VALIDER rouvre bien le choix d'identification.
2. **Adhésion par email** : « Saisir email / nom » → formulaire en popup V2 → VALIDER → même popup de paiement. CASHLESS demande alors un scan (pas de carte connue).
3. **Billet / adhésion à 0 €** : après l'identification, un seul bouton VALIDER (« Rien à encaisser »). Succès « Payé en cadeau : 0,00 € ». En admin : la LigneArticle et le billet sont en « Offert ».
4. **Tarifs SEPA / validation manuelle** : les produits « Adhesion SEPA lien… » (tarifs à validation manuelle) n'apparaissent plus dans la grille du PV Adhésions.
5. **Recharge check carte** : CHECK CARTE → scan → Monnaie locale → 5 € → ESPÈCE → popup pavé. Taper 10 → « À rendre 5,00 € » → Valider → succès avec « Monnaie à rendre ». Annuler ramène à l'écran Recharger. CB → rappel du TPE → Valider → succès.

Tests auto :
```
poetry run pytest tests/pytest/test_billetterie_pos.py tests/pytest/test_retour_carte_recharge.py tests/pytest/test_laboutik_tarifs_en_ligne_exclus.py tests/pytest/test_popups_paiement_v2.py -q
```

### Traductions
Nouvelles chaînes : « Rien à encaisser : validez pour enregistrer. », « Ce panier n'est pas gratuit. ». `makemessages` n'a **pas** été lancé.

### Migration
- **Migration necessaire / Migration required:** Non
