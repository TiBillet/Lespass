# Parcours Fedow reel en E2E + couverture des pannes
# / Real Fedow journey in E2E + failure coverage

**Date :** 2026-07-22
**Migration :** Non

## Resume / Summary

**Quoi / What :** Un test de bout en bout qui parle au **vrai Fedow** — credit d'une monnaie
locale, vente par QR code, remise en banque, verification de l'affichage — plus la couverture
pytest du meme parcours avec un Fedow simule, et le comportement des vues en cas de panne.
/ An end-to-end test talking to the REAL Fedow, plus pytest coverage of the same journey with
a simulated Fedow, and the views' behaviour under failure.

**Pourquoi / Why :** Aucun test du depot ne parlait au Fedow. Les vues qui manipulent de
l'argent etaient couvertes par des mocks cloisonnes : chaque etape verifiee seule, jamais la
chaine, et jamais contre le service reel.

### Fichiers ajoutes / Added files

| Fichier / File | Contenu / Content |
|---|---|
| `tests/e2e/test_parcours_fedow_reel.py` | 3 tests contre le **vrai Fedow** (dont 1 Stripe, ignore par defaut) |
| `tests/pytest/test_parcours_vente_fed_et_remise_en_banque.py` | 6 tests : la chaine avec un Fedow simule a etat, et les pannes |

---

## Ce que l'E2E prouve, et que le pytest ne pouvait pas

Le test `test_vente_en_monnaie_locale_puis_remise_en_banque` enchaine, **sur le Fedow reel** :

1. le lieu credite un adherent de 5 € en monnaie locale ;
2. un membre habilite genere un QR code de 2,50 € ;
3. l'adherent le paie ;
4. **le Fedow a debite l'adherent** de exactement 2,50 € — relu sans cache ;
5. la vente est enregistree cote Lespass ;
6. **le Fedow a credite le lieu** du meme montant ;
7. le gestionnaire declenche la remise en banque ;
8. **le Fedow a vide le portefeuille du lieu** ;
9. la page affiche la remise dans l'historique.

Chaque etape relit l'etat **sur le Fedow**, pas dans une variable de test. Duree : ~50 s.

### Le contrat que seul le Fedow reel a revele

La premiere version echouait :

```
Exception: {'metadata': ['No data in metadata for ligne_article_uuid']}
```

Le Fedow **exige** `ligne_article_uuid` dans les metadonnees d'une recharge, et
`rewarded_from_ticket_scanned` pour contourner sa validation de vente (une recharge directe
n'a pas de vente derriere elle). C'est le contrat que respecte deja l'API v2 de recharge
(`api_v2/views.py`).

Un Fedow simule aurait accepte n'importe quoi. C'est exactement ce que ce test apporte : il
verifie que Lespass respecte un contrat que personne n'avait ecrit ailleurs que dans le code
d'un appelant.

### Effets de bord assumes

Ces tests **ne s'annulent pas**. Une vente debite un vrai portefeuille, une remise en banque
vide celui du lieu pour la monnaie concernee — le Fedow n'a pas de marche arriere. A lancer en
dernier, sur un Fedow de developpement.

---

## Le volet Stripe — `stripe listen` requis

`test_recharge_federee_par_carte_bancaire` recharge un portefeuille en **monnaie federee** par
carte bancaire (carte de test `4242 4242 4242 4242`). C'est le seul moyen d'en obtenir : la
monnaie federee s'achete, elle ne se cree pas.

Il est **ignore par defaut**. Pour le lancer :

```bash
# 1. Dans un terminal, cote hote :
stripe listen

# 2. Puis :
docker exec -e E2E_STRIPE_LISTEN=1 lespass_django poetry run pytest \
    /DjangoFiles/tests/e2e/test_parcours_fedow_reel.py -v
```

Sans `stripe listen`, le webhook de confirmation n'arrive jamais, le portefeuille reste a zero,
et le test echouerait pour une raison sans rapport avec le code.

### Trois pieges du checkout Fedow, trouves en ecrivant ce test

1. **`refill_wallet` renvoie un en-tete `HX-Redirect`**, pas une redirection HTTP. Seul htmx
   la suit : il FAUT cliquer le bouton `[hx-get="/my_account/refill_wallet"]`. Un `page.goto`
   sur cette route recoit un 200 vide et n'arrive jamais chez Stripe.
2. **Le checkout est a montant LIBRE** : le payeur saisit la somme dans `input#customUnitAmount`,
   sur la page Stripe. Sans montant, le bouton « payer » reste inerte, sans message.
3. **`input#billingName` est obligatoire** et Stripe refuse la soumission **sans quitter la
   page** s'il est vide. La fixture partagee `fill_stripe_card` ne le remplit qu'avec un
   `is_visible(timeout=2_000)` : si le champ React n'est pas monte a temps, il est saute en
   silence. Le test le remplit donc explicitement apres l'appel a la fixture.

Les champs sont montes par React **apres** l'arrivee sur la page : les viser trop tot ne
trouve rien du tout — le premier diagnostic relevait zero `input`.

**Limite connue** : ce test s'arrete apres la recharge. La remise en banque de la monnaie
federee ne passe pas par le meme chemin que la monnaie locale — elle est declenchee par le
webhook Stripe `transfer.created` (`ApiBillet/views.py`), que Stripe n'emet pas sur commande.
`global_asset_bank_stripe_deposit` reste donc sans test.

---

## Le comportement en panne du Fedow

Constate, pas suppose :

| Situation | Comportement |
|---|---|
| Remise en banque, Fedow injoignable | message d'erreur au gestionnaire ✓ |
| Paiement QR code, Fedow injoignable | **aucune vente enregistree** ✓ |
| Page des remises, Fedow injoignable | **erreur serveur** — aucune garde |
| Relevé de transactions, Fedow injoignable | **erreur serveur** — aucune garde |

Les deux premieres lignes sont les bonnes : ne jamais annoncer une remise qui n'a pas eu lieu,
ne jamais enregistrer une vente que le Fedow n'a pas encaissee.

Les deux dernieres sont decrites par des tests qui **echoueront le jour ou une garde sera
posee** — ce sera le signal de verifier ce que la page affiche alors. A noter que
`tokens_table` de la page compte, elle, se degrade proprement en pareil cas : l'ecart entre
les deux n'a pas l'air volontaire.

---

## Comment tester (a la main) / Manual test

Les tests automatiques couvrent le parcours. La verification manuelle utile porte sur ce
qu'ils ne voient pas : l'aspect des pages.

1. `/fedow/asset/<uuid-monnaie-locale>/retrieve_bank_deposits/` : la ventilation par lieu et
   l'historique doivent etre lisibles et correctement formates (montants en euros).
2. Declencher une remise depuis l'admin, recharger : le total du lieu doit avoir diminue et une
   ligne s'ajouter a l'historique.

### Tests automatiques

```bash
# Le serveur de developpement doit tourner.
docker exec lespass_django poetry run pytest /DjangoFiles/tests/e2e/test_parcours_fedow_reel.py -v
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

Etat au moment de l'ecriture : **3 tests E2E verts** (parcours monnaie locale, relevé de
transactions, recharge federee par Stripe) et **1087 tests pytest verts**.

Le parcours monnaie locale a ete verifie sur deux executions consecutives : il ne depend
pas de l'etat laisse par la precedente.
