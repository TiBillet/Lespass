# Mécanisme de remboursement de carte NFC

Document de référence pour le flow « Vider une carte / Remboursement en espèces »
implémenté par `WalletService.rembourser_en_especes()` (`fedow_core/services.py`).

## Vue d'ensemble

Quand une personne veut récupérer son solde en espèces (carte rendue, fin de festival,
remboursement à la demande), le lieu effectue un « refund » qui :

1. Lit les tokens éligibles du wallet de la carte.
2. Crée une `Transaction(action=REFUND)` par asset (transfert wallet_carte → wallet du lieu).
3. Crée des `LigneArticle` comptables qui apparaissent dans les rapports caisse/admin.
4. Optionnellement : réinitialise la carte (action VV — détache user, supprime wallet_ephemere,
   supprime la `CartePrimaire` associée).

## Tokens éligibles

| Catégorie | Éligible ? | Filtre |
|---|---|---|
| TLF — Token Local Fiduciaire | ✅ | `asset.tenant_origin == tenant courant` |
| FED — Fiduciaire Federée | ✅ | aucun filtre origine (1 seul Asset FED dans le système) |
| TNF — Token Local Cadeau | ❌ | non remboursable par nature |
| TIM — Monnaie Temps | ❌ | non monétaire |
| FID — Points de Fidélité | ❌ | non monétaire |

**Règle principale** : un lieu ne rembourse en espèces **que ses propres tokens locaux fiduciaires**
plus la part fédérée Stripe. Pour les TLF d'un autre lieu, le porteur doit aller dans ce lieu.

## Sortie comptable (LigneArticle)

Pour un remboursement de 10€ TLF + 5€ FED, le service crée :

| LigneArticle | `payment_method` | `amount` (centimes) | `sale_origin` | Sens comptable |
|---|---|---|---|---|
| 1 | `STRIPE_FED` | +500 | `ADMIN` | Encaissement de la part fédérée par le lieu |
| 2 | `CASH` | -1500 | `ADMIN` | Sortie de caisse totale |

Le `pricesold` de chaque ligne pointe vers le `Product` système « Remboursement carte »
(`methode_caisse=VC`) créé à la demande par `BaseBillet/services_refund.py`.

Les rapports comptables (caisse, admin tenant) peuvent identifier ces opérations en filtrant :
- `LigneArticle.pricesold.product.methode_caisse == 'VC'` ET `LigneArticle.sale_origin == 'AD'`
- Ou via `LigneArticle.payment_method == CASH AND amount < 0` couplé au product VC.

## Dette du pot central → tenant (FED)

La part FED remboursée à la personne **a été initialement encaissée par le pot central Stripe**
(quand la personne a fait sa recharge). Quand le lieu rend du FED en espèces, le pot central
**doit ce montant au lieu**. Le mécanisme actuel (V1) : virement bancaire du pot central vers
le compte du lieu, à la fin de chaque mois, pour la somme des FED remboursés.

**Phase 2 du chantier mono-repo (à venir)** : nouvelle action `Transaction.BANK_TRANSFER` qui
trace le virement reçu. Le solde de la dette se calcule par requête :

```python
# Dette pot central → tenant pour les FED remboursés
total_refund_fed = Transaction.objects.filter(
    action=Transaction.REFUND,
    asset__category=Asset.FED,
    receiver=tenant.wallet,
).aggregate(Sum('amount'))['amount__sum'] or 0

total_virements_recus = Transaction.objects.filter(
    action=Transaction.BANK_TRANSFER,  # à créer en Phase 2
    asset__category=Asset.FED,
    receiver=tenant.wallet,
).aggregate(Sum('amount'))['amount__sum'] or 0

dette_pot_central = total_refund_fed - total_virements_recus
```

## Action « VV » — Réinitialisation de la carte

Si l'admin coche la case « Réinitialiser la carte » :

```python
CartePrimaire.objects.filter(carte=carte).delete()  # carte ne peut plus être primaire
carte.user = None                                    # détache la personne
carte.wallet_ephemere = None                         # détache le wallet (reste en BDD pour audit)
carte.save(update_fields=["user", "wallet_ephemere"])
```

Cas typique : carte perdue, carte rendue par une personne qui ne reviendra pas, carte récupérée
en fin de festival pour réutilisation.

**Le wallet n'est jamais supprimé** : il reste en base pour conserver l'audit trail des
transactions historiques. Il est juste détaché de la carte.

## Origine du mécanisme

Reproduit le flow legacy V1 :

- **Côté Fedow** : `OLD_REPOS/Fedow/fedow_core/serializers.py:174 CardRefundOrVoidValidator`
  + endpoint `card/refund` (`OLD_REPOS/Fedow/fedow_core/views.py:253`).
- **Côté LaBoutik** : `OLD_REPOS/LaBoutik/webview/views.py:1396 methode_VC` (Vider Carte) et
  `methode_VV` (Void Carte). 2 `ArticleVendu` créés (encaissement FED + sortie CASH du total),
  miroir des `LigneArticle` actuels.

La V2 fait la même chose en accès DB direct (plus de HTTP inter-service), via un service
unique réutilisable par l'admin web (Phase 1) et le POS Cashless (Phase 3).

## Roadmap

| Phase | Périmètre |
|---|---|
| **1** (en cours) | Admin web cartes + page remboursement + service `WalletService.rembourser_en_especes()` |
| **2** | Action `Transaction.BANK_TRANSFER` + suivi de la dette pot central → tenant |
| **3** | Bouton POS Cashless « Vider Carte / Void Carte », utilise le même service |
