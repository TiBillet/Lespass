# Phase 3, Etape 2 — Retour carte + recharges + adhesions

## Prompt

```
On travaille sur la Phase 3 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 2 sur 3 : les vues restantes qui utilisent fedow_core.

L'etape 1 est faite : _payer_par_nfc() est fonctionnel et atomique.
Lis le plan section 12 (retour_carte, recharges, adhesions).

Tache (1 fichier : laboutik/views.py) :

1. retour_carte() — vrai solde depuis fedow_core :
   - CarteCashless.objects.get(tag_id=tag_id) → carte
   - wallet = carte.user.wallet (ou carte.wallet_ephemere)
   - WalletService.obtenir_solde_total(wallet) → tous les tokens
   - Membership.objects.filter(user=carte.user) → adhesions actives
   - Passer au template partial hx_card_feedback

2. Recharges (methode RE/RC dans le panier) :
   - RE = recharge euros : TransactionService.creer_recharge(
       sender=wallet_lieu, receiver=wallet_client, asset=TLF, montant=...)
   - RC = recharge cadeau : idem avec asset TNF
   - Creer aussi la LigneArticle correspondante (sale_origin='LB')

3. Adhesions (methode AD dans le panier) :
   - Creer/renouveler une Membership dans BaseBillet
   - Si necessaire : TransactionService pour le paiement en tokens
   - Verifier comment BaseBillet.Membership fonctionne (lire le modele d'abord)

4. Nettoyer : supprimer les derniers imports mockData dans les vues modifiees.

⚠️ NE PAS supprimer mockData.py/method.py (Phase 7).
⚠️ Verifier que verifier_carte() et lire_nfc() fonctionnent encore
   (elles peuvent rester mockees si le hardware NFC n'est pas disponible).
```

## Verification

- retour_carte affiche les vrais soldes depuis Token
- Recharge EUR → Token credite, Transaction REFILL creee
- Recharge cadeau → Token cadeau credite, Transaction REFILL creee
- Adhesion → Membership creee/renouvelee

## Modele recommande

**Opus** — recharges atomiques, adhesions cross-module
