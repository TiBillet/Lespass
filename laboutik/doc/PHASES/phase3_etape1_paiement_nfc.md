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

⚠️ PREREQUIS — Wallet du lieu :
Le receiver du paiement NFC est le wallet du lieu (tenant).
Verifier COMMENT obtenir ce wallet :
- Option A : Configuration.get_solo() a-t-il un champ wallet/primary_wallet ?
- Option B : Le tenant (Client) a-t-il un wallet ?
- LIRE les modeles Configuration et Client AVANT de coder.
Si aucun wallet lieu n'existe, signaler au mainteneur. Ne PAS inventer un champ.

⚠️ PREREQUIS — PriceSold/ProductSold :
Phase 2 a du etablir le pattern pour creer PriceSold + ProductSold.
REUTILISER exactement le meme pattern ici. Ne pas creer un chemin different.

Tache (1 fichier : laboutik/views.py) :

1. _payer_par_nfc(request, articles_du_panier, tag_id, primary_card_tag_id) :

   a) CarteCashless.objects.get(tag_id=tag_id) → carte client
   b) wallet client :
      - Si carte.user existe → carte.user.wallet
      - Si carte.wallet_ephemere existe → carte.wallet_ephemere
      - Sinon → erreur "Carte non associee"
   c) Determiner l'asset pour chaque article :
      - Price.asset (FK fedow_core.Asset)
      - Si Price.asset is None → asset TLF par defaut du tenant
   d) Verifier le solde AVANT le bloc atomic :
      WalletService.obtenir_solde(wallet, asset) >= total_centimes
   e) Si solde insuffisant → retourner partial hx_funds_insufficient
      avec le montant manquant. NE PAS debiter.
   f) Si suffisant → transaction.atomic() :
      - TransactionService.creer_vente(
          sender_wallet=wallet_client,
          receiver_wallet=wallet_lieu,
          asset=asset,
          montant_en_centimes=total_centimes,
          tenant=connection.tenant,   ← NE PAS OUBLIER
          card=carte_cashless,
          primary_card=carte_primaire
        )
      - Pour chaque article : creer ProductSold + PriceSold + LigneArticle
        (MEME pattern que Phase 2 especes/CB)
   g) Retourner partial hx_payment avec le nouveau solde

2. Gestion d'erreur :
   - SoldeInsuffisant → partial avec message, PAS de 500
   - CarteCashless.DoesNotExist → partial avec message
   - Toute autre exception → log + partial erreur generique

3. Ajouter data-testid :
   - data-testid="paiement-nfc-solde"
   - data-testid="paiement-nfc-insuffisant"
   - data-testid="paiement-nfc-succes"

⚠️ NE PAS toucher aux services fedow_core (deja faits).
⚠️ NE PAS modifier les modeles.
⚠️ Verifier le solde AVANT d'entrer dans le bloc atomic.
⚠️ Le parametre `tenant` est OBLIGATOIRE dans TransactionService.creer_vente().
```

## Tests

### pytest — tests/pytest/test_paiement_cashless.py

```python
# Tests CRITIQUES a ecrire dans cette session :
#
# 1. test_paiement_nfc_atomique
#    Setup : wallet client avec 5000 centimes, asset TLF, produit a 3000
#    Action : _payer_par_nfc
#    Verify : Transaction creee, Token.value == 2000, LigneArticle creee
#
# 2. test_paiement_nfc_rollback_solde_insuffisant
#    Setup : wallet avec 1000 centimes, produit a 3000
#    Action : _payer_par_nfc
#    Verify : RIEN ne change — Token.value == 1000, Transaction.count == 0, LigneArticle.count == 0
#
# 3. test_paiement_nfc_carte_inconnue
#    Action : _payer_par_nfc avec tag_id inexistant
#    Verify : partial erreur, rien en DB
#
# 4. test_paiement_nfc_wallet_ephemere
#    Setup : carte avec wallet_ephemere (pas de user)
#    Action : _payer_par_nfc
#    Verify : debite le wallet_ephemere, pas un autre wallet
#
# 5. test_paiement_nfc_cree_pricesold_productsold
#    Verify : LigneArticle.pricesold.productsold pointe vers le bon Product
#
# 6. test_paiement_nfc_tenant_sur_transaction
#    Verify : Transaction.tenant == connection.tenant (pas None, pas un autre)
#
# 7. test_atomicite_si_erreur_lignearticle
#    Setup : simuler une erreur lors de la creation de LigneArticle (mock raise)
#    Verify : Token.value revient a l'etat initial, pas de Transaction creee
```

Lancer : `docker exec lespass_django poetry run pytest tests/pytest/test_paiement_cashless.py -v`

### Playwright — tests/playwright/tests/33-laboutik-paiement-nfc.spec.ts

```
Scenario (necessite des donnees de test avec wallet + tokens) :
1. Setup : creer wallet client avec solde, creer carte cashless liee
2. Login admin, naviguer vers /laboutik/caisse/
3. Scanner carte primaire → PV
4. Ajouter un article au panier
5. Choisir paiement NFC → simuler scan carte client
6. Verifier message succes + nouveau solde affiche
7. Verifier en DB : Transaction + Token + LigneArticle coherents
```

### Verification manuelle

- Paiement NFC avec solde suffisant → Transaction creee, Token debite, LigneArticle cree
- Paiement NFC avec solde insuffisant → rien ne change (Token, Transaction, LigneArticle)
- Le tout est atomique : si LigneArticle.create echoue → Token revient a son etat initial
- Pas de traceback dans les logs

## Checklist fin d'etape

- [ ] `manage.py check` passe
- [ ] 7 tests pytest verts
- [ ] Test Playwright vert
- [ ] Pas de traceback dans les logs serveur
- [ ] **Transaction.tenant == connection.tenant** (verifier en shell)
- [ ] Le pattern PriceSold/ProductSold est identique a Phase 2
- [ ] i18n : makemessages + compilemessages si nouveaux textes
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase3-etape1-paiement-nfc.md`

## Modele recommande

**Opus** — atomicite, argent reel, zero marge d'erreur
