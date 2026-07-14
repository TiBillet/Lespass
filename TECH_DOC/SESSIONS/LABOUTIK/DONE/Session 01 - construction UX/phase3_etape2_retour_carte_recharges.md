# Phase 3, Etape 2 — Retour carte + recharges + adhesions

## Prompt

```
On travaille sur la Phase 3 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 2 sur 3 : les vues restantes qui utilisent fedow_core.

L'etape 1 est faite : _payer_par_nfc() est fonctionnel et atomique.
Lis le plan section 12 (retour_carte, recharges, adhesions).

Tache (1 fichier principal : laboutik/views.py) :

1. retour_carte() — vrai solde depuis fedow_core :
   - CarteCashless.objects.get(tag_id=tag_id) → carte
   - wallet = carte.user.wallet (ou carte.wallet_ephemere)
   - WalletService.obtenir_tous_les_soldes(wallet) → tous les tokens
   - Membership.objects.filter(user=carte.user, status__in=['valid', 'active'])
     → adhesions actives
   - Passer au template partial hx_card_feedback
   - data-testid="retour-carte-soldes"

2. Recharges (methode RE/RC/TM dans le panier) :
   - RE = recharge euros :
     transaction.atomic() :
       TransactionService.creer_recharge(
         sender=wallet_lieu, receiver=wallet_client,
         asset=TLF_du_tenant, montant_en_centimes=montant,
         tenant=connection.tenant
       )
       + LigneArticle (sale_origin='LB', payment_method depend du moyen utilise)
   - RC = recharge cadeau :
     Idem avec asset=TNF_du_tenant
   - TM = recharge temps :
     Idem avec asset=TIM_du_tenant
   - ⚠️ Pour chaque recharge, creer aussi PriceSold + ProductSold + LigneArticle
     (meme pattern que Phase 2)

3. Adhesions (methode AD dans le panier) :
   - LIRE BaseBillet/models.py pour comprendre le modele Membership :
     → quels champs obligatoires, quels statuts, quels liens avec Product ?
   - Creer/renouveler une Membership dans BaseBillet
   - Si paiement en tokens : TransactionService pour le debit
   - Si paiement en EUR (especes/CB) : juste LigneArticle
   - Toujours dans transaction.atomic()

4. Nettoyer : supprimer les derniers imports mockData dans les vues modifiees.

5. data-testid sur les nouveaux elements :
   - data-testid="retour-carte-soldes"
   - data-testid="retour-carte-adhesions"
   - data-testid="recharge-succes"
   - data-testid="adhesion-succes"

⚠️ NE PAS supprimer mockData.py/method.py (Phase 7).
⚠️ Verifier que verifier_carte() et lire_nfc() fonctionnent encore.
⚠️ Attention au sens de la recharge : sender=lieu, receiver=client
   (l'inverse d'une vente).
```

## Tests

### pytest — tests/pytest/test_retour_carte_recharges.py

```python
# Tests a ecrire :
#
# 1. test_retour_carte_affiche_vrais_soldes
#    Setup : wallet avec 3 tokens (TLF=5000, TNF=2000, TIM=1000)
#    Action : retour_carte(tag_id)
#    Verify : response contient les 3 soldes corrects
#
# 2. test_retour_carte_affiche_adhesions
#    Setup : user avec Membership active
#    Action : retour_carte(tag_id)
#    Verify : response contient l'adhesion
#
# 3. test_retour_carte_sans_wallet
#    Setup : carte sans user ni wallet_ephemere
#    Verify : message erreur, pas de 500
#
# 4. test_recharge_euros
#    Setup : wallet client vide, asset TLF
#    Action : recharge RE, montant 5000
#    Verify : Token.value == 5000, Transaction(action=REFILL) creee,
#             LigneArticle creee
#
# 5. test_recharge_cadeau
#    Action : recharge RC, montant 3000
#    Verify : Token TNF credite, Transaction REFILL
#
# 6. test_recharge_temps
#    Action : recharge TM, montant 200
#    Verify : Token TIM credite
#
# 7. test_adhesion_cree_membership
#    Setup : user sans adhesion, product methode_caisse=AD
#    Action : paiement adhesion
#    Verify : Membership creee pour cet user
#
# 8. test_adhesion_renouvelle
#    Setup : user avec adhesion expiree
#    Action : paiement adhesion
#    Verify : Membership renouvelee (date_end mise a jour)
#
# 9. test_recharge_sens_correct
#    Verify : Transaction.sender == wallet_lieu, Transaction.receiver == wallet_client
#             (inverse de la vente)
```

Lancer : `docker exec lespass_django poetry run pytest tests/pytest/test_retour_carte_recharges.py -v`

### Playwright — tests/playwright/tests/33-laboutik-paiement-nfc.spec.ts (suite)

```
Ajouter au test existant :
1. Depuis l'interface PV
2. Ajouter un article "Recharge 10€" (methode_caisse=RE)
3. Scanner carte client
4. Verifier solde augmente de 1000 centimes
5. Verifier LigneArticle + Transaction en DB
```

### Verification manuelle

- retour_carte affiche les vrais soldes depuis Token
- Recharge EUR → Token TLF credite, Transaction REFILL creee
- Recharge cadeau → Token TNF credite, Transaction REFILL creee
- Adhesion → Membership creee/renouvelee
- Le sender d'une recharge est le lieu, le receiver est le client

## Checklist fin d'etape

- [ ] `manage.py check` passe
- [ ] 9 tests pytest verts
- [ ] Test Playwright vert
- [ ] Pas de traceback dans les logs serveur
- [ ] Sens recharge correct (lieu → client)
- [ ] i18n : makemessages + compilemessages
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase3-etape2-retour-carte-recharges.md`

## Modele recommande

**Opus** — recharges atomiques, adhesions cross-module
