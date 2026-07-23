# Garde anti-FED-local + tests de la page solde / Local-FED guard + balance page tests

**Date :** 2026-07-22
**Migration :** Non

## Resume / Summary

**Quoi / What :** La page `/my_account/balance/` passe de zero a 32 tests, couvrant
l'agregation des soldes des deux moteurs de monnaie, l'affichage, le remboursement en ligne
et la recharge. Avec les fichiers voisins (solde depensable, garde, trace comptable du
remboursement), le chantier ajoute 68 tests dont 55 nouveaux. En chemin, une garde de
production est posee : la creation d'un asset local de categorie FED est desormais refusee
explicitement.
/ The balance page goes from zero to 32 tests, covering balance aggregation across both
currency engines, display, online refund and refill. With the neighbouring files the batch
adds 68 tests, 55 of them new. Along the way a production guard is added: creating a local
FED asset is now explicitly refused.

**Pourquoi / Why :** Cette page est l'endroit ou le Fedow distant et le moteur local
`fedow_core` se rencontrent. Une erreur d'agregation n'y casse rien visiblement : elle
affiche un solde faux, en double, ou en fait disparaitre un. Et la protection contre un
asset FED local, prevue par la feuille de route, n'existait que par accident — elle tenait a
une categorie `Client.FED` manquante et a un appel commente.
/ This page is where the remote Fedow and the local engine meet, and an aggregation error
fails silently. The protection against a local FED asset existed only by accident.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `fedow_core/models.py` | `Asset.save()` leve `AssetFedLocalInterdit` sur la categorie FED |
| `fedow_core/exceptions.py` | Nouvelle exception `AssetFedLocalInterdit` |
| `TiBillet/settings.py` | `FEDOW_AUTORISER_ASSET_FED_LOCAL = False` (reglage transitoire) |
| `fedow_core/services.py` | `RefillService` : commentaire de tete « chantier en cours, aucun appelant » |
| `fedow_core/management/commands/bootstrap_fed_asset.py` | Commentaire de tete « ne pas lancer avant la migration » |
| `laboutik/management/commands/create_test_pos_data.py` | Recherche du FED local commentee (requete inatteignable), import `call_command` commente avec son appel |
| `tests/pytest/test_card_refund_service.py` | Fixture FED : `override_settings` pour lever la garde |
| `tests/pytest/test_bank_transfer_service.py` | Idem |
| `tests/pytest/test_asset_recharge_signal.py` | Idem |
| `tests/pytest/test_verify_transactions.py` | Teardown repare : `tenant_context` + suppression des Products de recharge |

### Fichiers ajoutes / Added files

| Fichier / File | Contenu / Content |
|---|---|
| `tests/pytest/test_balance_soldes_et_recharge.py` | 32 tests : agregation, tableau des monnaies, remboursement, recharge, boutons |
| `tests/pytest/test_qrcodescanpay_permissions.py` | 9 tests : encaisser demande un droit, payer non |
| `tests/pytest/test_fedow_solde_depensable.py` | 11 tests : ce qui est depensable dans un lieu |
| `tests/pytest/test_fedow_garde_asset_fed_local.py` | 9 tests : l'invariant de la garde |
| `tests/pytest/test_remboursement_especes_trace_comptable.py` | 8 tests + 2 `xfail` : la trace comptable d'un vidage de carte, monnaie locale ET federee, et sa remontee dans les rapports X / Z |

`tests/pytest/test_balance_refill_et_permissions_paiement.py` (non commite) a ete scinde
entre les deux premiers fichiers ci-dessus. Aucun test perdu.

### Ce que l'audit a etabli / What the audit established

Trois constats qui ne se voient pas dans le diff :

1. **La collision d'UUID entre les deux moteurs est impossible aujourd'hui.** La
   deduplication de `_agreger_tokens_locaux` (`BaseBillet/views.py:894`) compare
   `AssetFedowPublic.uuid` et `fedow_core.Asset.uuid`, deux familles d'identifiants
   independantes : les points de creation locaux n'imposent jamais d'uuid, et rien ne pousse
   un uuid local vers le Fedow distant. Base de dev : intersection vide. La branche est donc
   inatteignable — un test la couvre quand meme, en forcant la coincidence.
2. **Aucun asset FED local n'existe.** `RefillService.process_cashless_refill` n'a aucun
   appelant, et `bootstrap_fed_asset` ne peut pas s'executer (`Client.FED` n'existe pas).
3. **`WalletService.rembourser_en_especes` traite pourtant le FED local.** C'est du code en
   service, appele a chaque vidage de carte au point de vente (`laboutik/views.py:8271`). Sa
   branche FED est vide uniquement parce que l'asset n'existe pas. C'est ce que la garde
   transforme en protection explicite.
4. **Le remboursement mixte n'etait teste par personne.** `test_card_refund_service.py` et
   `test_pos_vider_carte.py` couvrent chaque monnaie SEULE : la ligne de sortie de caisse y
   vaut `-(1000 + 0)` ou `-(0 + 500)`, ce qui ne distingue pas une somme d'une recopie du
   plus grand des deux. Le nouveau fichier de trace comptable rembourse les deux ensemble
   (1000 + 500) et verifie que le tiroir sort bien 1500.
5. **Un teardown qui echouait en silence depuis des mois.** Celui de
   `test_verify_transactions.py` supprimait ses assets hors `tenant_context` : la cascade
   vers `BaseBillet.Product` levait, le `except Exception: pass` avalait, et 22 assets
   s'etaient accumules dans la base de dev. L'accumulation finissait par faire echouer
   `test_verify_clean` en suite complete, alors que le fichier passait seul. Repare, et le
   motif est documente dans `tests/PIEGES.md`.

### Ecart comptable identifie ici, CORRIGE depuis / Accounting gap found here, since FIXED

> Cette section a conduit au chantier decrit dans
> `CHANGELOG/2026-07-22-rapports-caisse-perimetre-et-exports.md`, qui corrige le defaut et
> supprime les deux `xfail`. Elle est conservee parce qu'elle explique **comment** le defaut
> a ete trouve.

**Les remboursements de carte n'apparaissaient ni dans le ticket X, ni dans le ticket Z.**

Mesure faite en conditions reelles : un remboursement de 1500 centimes cree bien sa
`LigneArticle` (`amount=-1500`, `payment_method=CA`, `sale_origin=AD`), mais le rapport
renvoie `especes: 0`, `remboursements: 0`, `solde de caisse: 0`.

La cause : `RapportComptableService.__init__` (`laboutik/reports.py:81`) construit son jeu de
lignes avec un filtre **exact** `sale_origin=SaleOrigin.LABOUTIK`, alors que
`WalletService.rembourser_en_especes` ecrit ses lignes avec `sale_origin=SaleOrigin.ADMIN`.
`calculer_remboursements()` (l.586) porte le meme filtre, et `calculer_solde_caisse()`
(l.417) ne compte que ces lignes-la plus les `SortieCaisse` — un remboursement n'entre dans
aucune des deux categories.

**Consequence concrete :** un caissier vide une carte et sort des billets du tiroir ; le
ticket Z annonce le meme solde qu'avant. L'ecart physique n'est explique nulle part.

Le filtre `sale_origin=LABOUTIK` est volontaire — il exclut les lignes `LABOUTIK_TEST` du
mode ecole (exigence LNE 5). Le corriger touche le rapport comptable, la cloture, les
exports et le chainage LNE : ce n'est pas une decision a prendre au detour d'un chantier de
tests.

Deux tests marques `xfail(strict=True)` decrivent le comportement **attendu** dans
`test_remboursement_especes_trace_comptable.py`. Le jour ou le filtre sera corrige, ils
passeront et `strict=True` fera echouer la suite tant que le marqueur n'aura pas ete retire.
La correction ne peut donc pas passer inapercue.

/ **Card refunds appear in neither the X nor the Z report.** Measured in real conditions:
the report shows zero. Cause: the report filters on `sale_origin=LABOUTIK` while refund
lines carry `sale_origin=ADMIN`. Consequence: cash leaves the drawer, the Z ticket does not
know. The filter is deliberate (it excludes training-mode lines, LNE req. 5), so fixing it
touches the closure, exports and LNE chaining — not a decision for a testing batch. Two
`xfail(strict=True)` tests describe the expected behaviour.

### Questions ouvertes / Open questions

- **Import de la phase suivante.** Si l'import du Fedow legacy vers `fedow_core` conserve
  les uuid d'origine, la collision decrite au point 1 devient la norme et la branche de
  deduplication reprend du sens. Tant que cette semantique n'est pas ecrite, on ne durcit
  pas — l'option d'une erreur franche reste ouverte, mais elle demanderait aussi de modifier
  les deux appelants, qui avalent toute exception (`views.py:1041` et `1314`).
- **`transactions_table` n'a pas de garde.** Contrairement a `tokens_table`, un Fedow
  distant injoignable y produit une erreur serveur. Non corrige ici.
- **Autres teardowns a auditer.** Le meme piege (suppression d'`Asset` hors
  `tenant_context`, exception avalee) existe peut-etre ailleurs. Le symptome est discret :
  des objets qui s'accumulent, et un test qui finit par echouer en suite complete tout en
  passant seul. Une passe sur les `except Exception: pass` des teardowns serait utile.

---

## Comment tester (a la main) / Manual test

### Test 1 — la page solde affiche bien les deux moteurs

1. Se connecter avec un compte qui possede a la fois de la monnaie federee et une monnaie
   locale du lieu.
2. Aller sur `https://lespass.tibillet.localhost/my_account/balance/`.
3. Le tableau « Liste des monnaies » se charge apres un court instant (spinner local).
4. Verifier que les monnaies du moteur local portent le badge « Local », et que celles d'un
   collectif non federe apparaissent grisees.

### Test 2 — le remboursement ne touche que la monnaie federee

1. Sur la meme page, ouvrir « Demander un remboursement ».
2. Avec un compte qui n'a QUE de la monnaie locale : la demande doit etre refusee avec un
   message, sans qu'aucun virement ne parte.
3. Avec un compte qui a de la monnaie federee : le courriel de confirmation annonce le
   montant federe seul, pas le total du portefeuille.

### Test 3 — le vidage de carte au point de vente n'a pas bouge

Couvert automatiquement par
`test_remboursement_especes_trace_comptable.py::test_vider_une_carte_depuis_la_caisse_ecrit_les_deux_lignes`,
qui passe par la vraie route HTTP avec la carte primaire, le controle d'acces au point de
vente et la garde active. A refaire a la main uniquement pour verifier l'impression du
recu, que le test ne couvre pas :

1. Ouvrir la caisse, scanner une carte primaire, puis « vider une carte ».
2. Scanner une carte client qui porte de la monnaie locale.
3. Le remboursement se deroule, et le ticket sort de l'imprimante.

### Verifs DB

La garde en action — doit lever `AssetFedLocalInterdit` :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from fedow_core.models import Asset
from Customers.models import Client
from AuthBillet.models import Wallet
Asset.objects.create(name='essai', category=Asset.FED, currency_code='EUR',
                     wallet_origin=Wallet.objects.first(),
                     tenant_origin=Client.objects.get(schema_name='lespass'))"
```

Aucun asset FED local en base — doit afficher `0` :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from fedow_core.models import Asset
print(Asset.objects.filter(category='FED').count())"
```

### Tests automatiques

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

Etat au moment de l'ecriture : **1009 tests verts + 2 xfail attendus, en 2 min 30**, aucun
echec, resultat identique sur deux runs consecutifs.

Les 2 `xfail` sont les tests de remontee des remboursements dans les rapports X / Z (cf.
l'ecart comptable ci-dessus). S'ils apparaissent en `XPASS`, c'est que le filtre
`sale_origin` a ete corrige : retirer alors les marqueurs `xfail` et cette section.
