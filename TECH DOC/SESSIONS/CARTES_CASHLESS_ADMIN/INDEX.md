# Cartes NFC — Admin web et flux de remboursement

Travail découpé en 3 phases indépendantes. Chaque phase est livrable et testable seule.

## Décisions transversales (validées en brainstorming 2026-04-13)

- **Scope admin** : consultation + actions ciblées (B). Création et suppression réservées au superuser.
- **Filtre tenant** : `Detail.origine == request.tenant` par défaut. Superuser voit le queryset complet.
- **Detail (lots de cartes)** : admin séparé, même règle de filtre.
- **Actions sensibles** : autorisées pour l'admin tenant si la carte appartient au tenant.
- **Périmètre du remboursement espèces** : TLF dont `asset.tenant_origin == request.tenant`, plus tous les FED.
  Un lieu ne rembourse que ses propres tokens locaux et la part fédérée Stripe.
- **VC / VV unifiés** : un seul flow « Rembourser » avec une checkbox optionnelle « Réinitialiser la carte (VV) ».
- **Dette pot central → tenant pour les FED remboursés** : nouvelle action `Transaction.BANK_TRANSFER`
  (réutilise la table Transaction, single source of truth). Calcul de la dette par requête.
- **Flow technique remboursement** : ViewSet dédié dans `Administration/views_cards.py`,
  patterns FALC `/djc` (`viewsets.ViewSet`, methodes explicites, serializers DRF, HTMX HX-Trigger).
- **Section sidebar** : sous « Fedow », conditionnelle à `Configuration.module_monnaie_locale`.
- **Code legacy mort `admin_root.py`** : commenter le reliquat actif et noter en en-tête que tout est passé sur `staff_admin_site`.

## Mécanisme de remboursement (issu du legacy `OLD_REPOS/Fedow` + `OLD_REPOS/LaBoutik`)

- Côté Fedow V1 (`CardRefundOrVoidValidator`, `serializers.py:174`) :
  - `local_tokens` : value > 0, `asset.wallet_origin == lieu.wallet`, catégories TLF + TNF
  - `fed_token` : value > 0, catégorie STRIPE_FED_FIAT (toutes valeurs, pas de filtre origine)
  - 1 `Transaction(action=REFUND, sender=wallet_carte, receiver=lieu.wallet)` par asset
- Côté LaBoutik V1 (`webview/views.py:1396 methode_VC`) : 2 ArticleVendu par remboursement
  - Vente positive : prix = solde FED, `moyen_paiement = STRIPE_FED` (encaissement en monnaie fédérée)
  - Vente négative : prix = -(TLF + FED), `moyen_paiement = ESPECE` (sortie cash totale)
- Action `void_card` (`Configuration.void_card`) : si coché, en plus du REFUND, la carte est nettoyée
  (`user = None`, `wallet_ephemere = None`, `primary_places.clear()`).
- Pot central : à la fin du mois, virement bancaire externe vers le compte du lieu pour les FED remboursés.
  Mécanisme bancaire externe au code, mais on doit **tracer la dette** côté Lespass (Phase 2).

## Phases

### Phase 1 — Admin web cartes + remboursement espèces
- Admin Unfold pour `CarteCashless` et `Detail`.
- Page dédiée `/admin/cartes/<uuid>/rembourser/` (ViewSet FALC).
- Action remboursement TLF + FED → Transaction REFUND + LigneArticle FED + LigneArticle CASH.
- Checkbox optionnelle « Réinitialiser » (VV).
- Cleanup `admin_root.py`.
- README `fedow_core/REFUND.md` qui documente la mécanique de bout en bout (TLF + FED + dette pot central).
- Spec : [`2026-04-13-phase1-admin-cartes-design.md`](2026-04-13-phase1-admin-cartes-design.md)
- Plan : à venir après validation du spec

### Phase 2 — Suivi de la dette pot central → tenant (FED remboursés)
- Nouvelle action `Transaction.BANK_TRANSFER` (modèle déjà extensible).
- Vue admin pour saisir un virement bancaire reçu (référence + montant + date).
- Calcul agrégé de la dette : `Sum(REFUND FED to tenant) - Sum(BANK_TRANSFER to tenant)`.
- Tableau de bord « Dette en attente de virement » côté tenant et côté pot central (superuser).
- Spec : à venir

### Phase 3 — Bouton POS Cashless « Rembourser carte / Vider carte »
- Ajout `Product.methode_caisse = VC` et `VV` (champ existe déjà).
- Configuration : article système « Vider Carte » sélectionnable dans l'admin (`LaboutikConfiguration.methode_vider_carte`, miroir du legacy).
- Vue dans `laboutik/views.py` qui réutilise le service de remboursement de la Phase 1.
- Flow POS : caissier scan carte → écran récap tokens → bouton confirmer (avec checkbox VV).
- Spec : à venir
