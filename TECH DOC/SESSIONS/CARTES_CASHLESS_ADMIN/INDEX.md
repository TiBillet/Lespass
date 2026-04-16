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
- Nouvelle action `Transaction.BANK_TRANSFER = 'BTR'` (table Transaction étendue).
- Saisie superuser : page dédiée `/admin/bank-transfers/` dans la section « Root Configuration ».
- Validation hard : `montant <= dette_actuelle` (rejet sur-versement, pas de cancellation).
- Mécanique : sender=`asset.wallet_origin`, receiver=`tenant.wallet`, **no token mutation** (étendre
  `actions_sans_credit/sans_debit` dans `TransactionService.creer()`).
- LigneArticle d'encaissement positif (`payment_method=TRANSFER`) pour rapports comptables.
- Nouveau code `Product.VIREMENT_RECU = "VR"` + helper `get_or_create_product_virement_recu()`.
- Affichage double : dashboard superuser (table tous tenants × assets) + widget tenant (solde +
  dernier virement) + 2 historiques (global et tenant).
- Spec : [`2026-04-13-phase2-bank-transfer-design.md`](2026-04-13-phase2-bank-transfer-design.md)
- Plan : à venir après validation du spec

### Refactor wallet-only (design à valider)
- Suppression du champ `CarteCashless.user` et `wallet_ephemere`, remplacés par `wallet` FK unique.
- Élimine la dualité `user.wallet | wallet_ephemere` et fusionne les 3 helpers dupliqués (`_wallet_de_la_carte`, `_obtenir_ou_creer_wallet`, `obtenir_contexte_cashless`).
- Effort révisé à 6-10h (au lieu de 16-24h) car V2 pas encore en production — pas de data migration zero-downtime nécessaire.
- Design : [`2026-04-14-refactor-carte-wallet-only-design.md`](2026-04-14-refactor-carte-wallet-only-design.md)

### Phase 3 — Bouton POS Cashless « Vider Carte »
- Tile POS auto-générée via Product `methode_caisse=VC` (créé par Phase 1) dans le M2M du PV.
- Flow dédié qui court-circuite le panier : clic tile → overlay scan NFC → récap tokens
  (total + détail TLF/FED) → checkbox VV → exécution via `WalletService.rembourser_en_especes()`
  (Phase 1) → écran succès + bouton impression reçu optionnel.
- Protection self-refund, contrôle d'accès via M2M `pv.cartes_primaires`.
- Patch additif léger : paramètre `primary_card=None` sur `WalletService.rembourser_en_especes()`
  pour tracer le·a caissier·e dans les Transactions REFUND.
- Formatter impression dédié (`formatter_recu_vider_carte`).
- Spec : [`2026-04-13-phase3-pos-vider-carte-design.md`](2026-04-13-phase3-pos-vider-carte-design.md)
- Plan : à venir après validation du spec
