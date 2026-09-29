# Paiement QR/NFC : un seul débit par QR code / QR/NFC payment: one debit per QR code

**Date :** 2026-09-28
**Migration :** Non
**Spec :** `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-04-F-chainage-hmac.md` §3 (session F-1), décision D23

## Resume / Summary

**Quoi / What :** avant de débiter chez Fedow, `valid_payment` et `process_with_nfc`
« réservent » la ligne en une requête atomique :
`filter(uuid, status=CREATED, payment_method=QRCODE_MA).update(status=UNPAID)`.
Si aucune ligne n'est réservée, le paiement est refusé (« déjà traité ») sans appel à Fedow.
Une erreur de Fedow pendant le débit passe la ligne en `FAILED` (plus jamais payable).
/ Both views atomically reserve the line (CREATED → UNPAID) before the Fedow debit; nothing
reserved = refused without calling Fedow. A Fedow error during the debit marks the line FAILED.

**Pourquoi / Why :** `valid_payment` chargeait la ligne sans filtre de statut, et Fedow n'a pas
de clé d'idempotence : chaque appel débite. Cas réels :
- deux écrans de validation ouverts sur le même QR code (deux onglets, deux adhérents qui ont
  scanné avant le paiement) : deux débits, et le 2e POST supprimait la vente du 1er (même uuid) ;
- paiement par carte : chaque clic sur « Lire la carte » ajoute un lecteur NFC
  (`generator.html`), donc un passage de carte peut envoyer deux requêtes simultanées. Le
  validateur lit bien `CREATED`, mais sans rien bloquer ;
- n'importe quelle `LigneArticle` du lieu (billet, adhésion) postée par son uuid était débitée,
  supprimée et recréée en vente QR.

Le double débit est silencieux (une seule vente reste en compta) : l'absence de signalement
en production ne prouve pas qu'il n'est jamais arrivé.

**Choix de simplicité (arbitré avec le mainteneur après une relecture critique) :** toute
erreur de Fedow au débit donne `FAILED`, sans distinguer un refus explicite (qui pourrait
remettre la ligne en `CREATED`) d'une erreur réseau. Le solde est vérifié avant le débit, un
refus est donc rare : l'encaisseur génère un nouveau QR code. Pas de `transaction.atomic`
autour de la recréation des lignes : c'est la fiche 05-C (chantier 05).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `valid_payment` : réservation, erreur Fedow → `FAILED` + message |
| `BaseBillet/views.py` | `process_with_nfc` : réservation (409 si déjà traité), erreur Fedow → `FAILED` + JSON 500 ; `raise f"..."` (TypeError, erreur 500 brute) remplacé par une réponse JSON `{"detail": ...}` que la fenêtre SweetAlert affiche déjà |
| `BaseBillet/views.py` | `process_qrcode` (GET) : garde `!= CREATED` au lieu de `== VALID`, placée AVANT l'écriture des métadonnées ; `save(update_fields=['metadata'])`. Un scan tardif ne réécrit plus la ligne d'une vente déjà validée, et un `save()` complet ne peut plus recréer une ligne supprimée par un paiement en cours |
| `tests/pytest/test_qrcodescanpay_flux_complet.py` | 8 tests (section 7 « Anti-rejeu ») |
| `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-04-F-chainage-hmac.md` | §3.2 : tableau aligné sur la version livrée |

### Tests

| Test | Vu échouer avant correctif |
|---|---|
| `test_un_qrcode_deja_paye_ne_debite_pas_une_seconde_fois` | oui (2 débits) |
| `test_une_ligne_qui_n_est_pas_un_qrcode_ne_peut_pas_etre_payee` | oui (débit d'une ligne Stripe) |
| `test_une_erreur_fedow_pendant_le_debit_bloque_le_qrcode` | oui (ligne restée `CREATED`) |
| `test_une_lecture_de_carte_concurrente_ne_debite_pas` | réécrit après relecture, vu échouer par M4 et MA (409 attendu) |
| `test_une_confirmation_concurrente_du_qrcode_ne_debite_pas` | ajouté après relecture, vu échouer par M1 et M9 |
| `test_une_erreur_fedow_pendant_un_paiement_par_carte_repond_proprement` | oui (`TypeError`) |
| `test_un_qrcode_en_cours_de_paiement_n_affiche_pas_l_ecran_de_validation` | oui (écran de validation affiché) |
| `test_une_erreur_apres_le_debit_par_carte_repond_proprement` | écrit après le correctif, vu échouer par la mutation M6 |

Les deux tests « concurrents » simulent une autre requête qui réserve la ligne pendant la
lecture du solde (entre le chargement de la ligne et la réservation) : seule une réservation
atomique en base, et non un test du statut lu en mémoire, arrête alors le débit.

### Mutations (10, toutes détectées, fichier restauré et sha256 vérifié)

| Mutation | Test tombé |
|---|---|
| M1 réservation retirée (QR) | `..._deja_paye_ne_debite_pas_une_seconde_fois`, `..._confirmation_concurrente_...` |
| M2 filtre `payment_method=QRCODE_MA` retiré | `..._n_est_pas_un_qrcode_ne_peut_pas_etre_payee` |
| M3 erreur Fedow → `CREATED` (QR) | `..._erreur_fedow_pendant_le_debit_bloque_le_qrcode` |
| M4 réservation retirée (NFC) | `..._lecture_de_carte_concurrente_ne_debite_pas` |
| M5 erreur Fedow → `CREATED` (NFC) | `..._erreur_fedow_pendant_un_paiement_par_carte_...` |
| M6 `raise f"..."` remis | `..._erreur_apres_le_debit_par_carte_...` |
| M7 garde GET remise à `== VALID` | `..._en_cours_de_paiement_n_affiche_pas_...` |
| M8 métadonnées écrites avant la garde GET | `..._en_cours_de_paiement_n_affiche_pas_...` |
| M9 réservation remplacée par le statut lu en mémoire (QR) | `..._confirmation_concurrente_...` |
| MA réservation remplacée par le statut lu en mémoire (NFC) | `..._lecture_de_carte_concurrente_...` |

Suites : `make test` 2089 passed puis 2090 passed après la relecture ; `make e2e` 116 passed.

### Relecture (agent Opus) et limites connues

- Tests renforcés (tests concurrents ci-dessus) ; spec §3.2 mise à jour.
- Une ligne peut rester `UNPAID` sans passer `FAILED` (worker tué pendant l'appel Fedow,
  exception après le débit et avant le `delete()`) : côté sûr, plus aucun débit possible ;
  vérification manuelle. Traitement fin en fiche 05-C.
- Débit fait puis échec de l'enregistrement (lecture de l'asset) : la réponse est propre, mais
  la vente n'est pas enregistrée (comportement antérieur ; fiche 05-C : réseau d'abord + transaction).

### i18n — nouvelle chaîne (makemessages à lancer par le mainteneur)

- « Le paiement n'a pas pu être confirmé. Demandez au lieu de vérifier votre portefeuille avant de réessayer. »

Chaînes réutilisées (déjà traduites) : « This payment has already been processed »,
« Error validating payment ».

---

## Comment tester (a la main) / Manual test

1. Admin (droit d'encaisser) : générer un QR code de paiement.
2. Scanner le QR code avec deux onglets connectés sous le même compte, avec un solde suffisant.
3. Valider dans le 1er onglet : paiement confirmé. Valider dans le 2e : « Ce paiement a déjà
   été réalisé », et un seul débit dans le portefeuille.
4. Rescanner le QR code : message « déjà réalisé » directement.
5. Couper Fedow (ou le rendre injoignable), générer un QR, valider : message « Le paiement
   n'a pas pu être confirmé… » ; la ligne est en échec dans l'admin, le QR n'est plus payable.
