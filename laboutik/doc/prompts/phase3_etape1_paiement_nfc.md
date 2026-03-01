# Phase 3, Etape 1 — Paiement NFC cashless (fedow_core)

## Prompt

```
On travaille sur la Phase 3 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 12 + section 17.1). Etape 1 sur 3 : le paiement NFC.

Phases 0-2 faites. fedow_core (modeles + services) et laboutik (modeles + vues)
existent. Les paiements especes/CB creent des LigneArticle.
Lis le plan section 12 (_payer_par_nfc) et section 17.1 (atomicite).

⚠️ C'EST LE MORCEAU LE PLUS CRITIQUE DU PROJET.
Un bug ici = argent perdu ou cree ex nihilo. Prends ton temps.

Contexte :
- _payer_par_nfc() doit etre 100% atomique (transaction.atomic)
- Token (SHARED) + LigneArticle (TENANT) dans le meme atomic — c'est OK car
  meme connexion PostgreSQL (cf. plan section 17.1)
- WalletService et TransactionService existent dans fedow_core/services.py
- Le verrou est sur Token (select_for_update par ligne), pas sur Asset

Tache (1 fichier : laboutik/views.py) :

1. _payer_par_nfc(request, articles_du_panier, tag_id, primary_card_tag_id) :

   a) CarteCashless.objects.get(tag_id=tag_id) → carte client
   b) carte.user.wallet (ou carte.wallet_ephemere si carte anonyme)
   c) Determiner l'asset : Price.asset (FK fedow_core.Asset, ou asset TLF par defaut si null)
   d) WalletService.obtenir_solde(wallet, asset)
   e) Si solde insuffisant → retourner partial hx_funds_insufficient
      avec le montant manquant. NE PAS debiter.
   f) Si suffisant → transaction.atomic() :
      - TransactionService.creer_vente(
          sender_wallet=wallet_client,
          receiver_wallet=wallet_lieu,
          asset=asset,
          montant=total_centimes,
          card=carte_cashless,
          primary_card=carte_primaire
        )
      - Pour chaque article : LigneArticle.objects.create(
          sale_origin='LB', payment_method='NFC', ...
        )
   g) Retourner partial hx_payment avec le nouveau solde

2. Le wallet du lieu = Configuration.get_solo().primary_wallet
   (ou un mecanisme equivalent — verifier ce qui existe)

3. Gestion d'erreur :
   - SoldeInsuffisant → partial avec message, PAS de 500
   - CarteCashless.DoesNotExist → partial avec message
   - Toute autre exception → log + partial erreur generique

⚠️ NE PAS toucher aux services fedow_core (deja faits).
⚠️ NE PAS modifier les modeles.
⚠️ Verifier le solde AVANT d'entrer dans le bloc atomic.

Verification :
docker exec lespass_django poetry run python manage.py check
Lancer les tests de memory/tests_validation.md Phase 3 :
- test_paiement_cashless_atomique
- test_paiement_cashless_rollback_si_solde_insuffisant
```

## Verification

- Paiement NFC avec solde suffisant → Transaction creee, Token debite, LigneArticle cree
- Paiement NFC avec solde insuffisant → rien ne change (Token, Transaction, LigneArticle)
- Le tout est atomique : si LigneArticle.create echoue → Token revient a son etat initial
- Pas de traceback dans les logs

## Modele recommande

**Opus** — atomicite, argent reel, zero marge d'erreur
