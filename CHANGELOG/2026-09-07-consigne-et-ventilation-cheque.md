# Consigne au POS V2 et ventilation du chèque / Deposit return at the V2 POS and check ventilation

**Date :** 2026-09-07
**Migration :** Oui — `laboutik/migrations/0003_cloturecaisse_total_cheque_and_more.py`
(`migrate_schemas --executor=multiprocessing`)

## Resume / Summary

**Quoi / What :** le retour de consigne devient une opération réelle au point de vente V2
— ligne comptable négative en espèces, **recharge du portefeuille** en cashless — et le
chèque encaissé cesse de disparaître de la clôture, des exports et de l'archive fiscale.
/ Deposit returns become a real operation at the V2 POS — negative accounting line in
cash, **wallet top-up** in cashless — and collected checks stop vanishing from the
closure, the exports and the tax archive.

**Pourquoi / Why :** deux fonctionnalités vivantes n'avaient aucun test, et l'audit a
montré que ce n'était pas un oubli de couverture : le code ne marchait pas.

1. **La consigne ne pouvait pas se déclencher.** Elle était détectée par un UUID en dur
   (`8f08b90d-…`) qui ne correspondait à **aucun produit** — sur aucun des 15 tenants,
   ni ailleurs dans le dépôt, ni dans la V1. Le champ prévu pour ça,
   `Product.RETOUR_CONSIGNE = "CR"`, n'était utilisé nulle part.
2. **Le chèque disparaissait de la comptabilité stockée.** Correctement encaissé et
   correctement calculé par `reports.py`, il n'avait pas de colonne sur `ClotureCaisse` :
   l'archivage LNE écrivait donc **`total_cheque = '0'` en dur**. Dès qu'un chèque était
   encaissé, l'archive fiscale était fausse et
   `especes + carte + cashless ≠ total_general`.
/ Two live features had no tests, and the audit showed the code did not work: the deposit
  UUID matched no product, and the tax archive hard-coded zero checks.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `- UUID_ARTICLE_CONSIGNE` et son import devenu mort ; `+ _panier_contient_retour_consigne`, `+ _panier_est_uniquement_retour_consigne` ; moyens réduits à espèces/cashless sur un panier consigne ; deux gardes dans `payer()` (panier mixte, moyen interdit) ; `+ _rembourser_consigne_par_nfc` et `_refuser_le_retour_de_consigne` ; garde des monnaies multiples ; exclusion du stock ; `+ total_cheque` à la clôture manuelle |
| `laboutik/models.py` | `+ ClotureCaisse.total_cheque` |
| `laboutik/migrations/0003_…` | `AddField total_cheque` |
| `laboutik/tasks.py` | `total_cheque` sur la clôture journalière **et** dans les agrégats hebdo/mensuel/annuel (`Sum('total_cheque')`) |
| `laboutik/archivage.py` | suppression du `'0'` en dur → le vrai `cloture.total_cheque` |
| `laboutik/csv_export.py`, `laboutik/pdf.py` + template PDF | ligne « Chèque » |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | bouton ESPÈCE conditionné aux moyens réellement disponibles |
| `laboutik/management/commands/create_test_pos_data.py` | produits de démo `Consigne` (+1 €) et `Retour Consigne` (−1 €, asset TLF) ; `total_cheque` sur la clôture de démo |
| `tests/pytest/test_pos_retour_consigne.py` | **neuf** — 18 tests |
| `tests/pytest/test_pos_paiement_cheque.py` | **neuf** — 3 tests |
| `tests/pytest/test_rapports_cheque.py` | **neuf** — 9 tests |

**Décisions actées** (détail et preuves dans `TECH_DOC/SESSIONS/CONSIGNE/SPEC.md`) :

- **En cashless, un retour de consigne est une RECHARGE**, comme en V1 (`methode_CR`) :
  la cascade de débit de `_payer_par_nfc` s'arrête au premier tour sur un montant
  négatif et n'écrit rien, tout en affichant un succès. D'où un flux dédié.
- **Le crédit et la ligne comptable partagent la même transaction.**
  `TransactionService.creer_recharge` est une écriture en base, pas un appel réseau
  (`fedow_core/services.py` n'importe ni `requests`, ni `httpx`, ni `FedowAPI`). Les
  séparer laisserait passer « client crédité, ligne comptable en échec ».
- **Le panier mixte est refusé** (400) : le total passe en valeur absolue dès qu'une
  consigne est présente, ce qui ferait afficher « à rembourser 2 € » quand le client
  *doit* 2 €.
- **Le refus CB/chèque est côté serveur** : `payer()` ne confronte jamais le moyen posté
  à la liste proposée, donc le filtrage des boutons ne protège rien.
- **Un article `CR` ne touche pas au stock** : `decrementer_pour_vente` « décrémente
  toujours », ce qui retirait un gobelet de l'inventaire au moment où le client en
  rapportait un, et `_valider_stock_panier` bloquait le retour dès stock zéro.
- **Pas de backfill** des clôtures existantes : le montant réel dort dans
  `rapport_json`, mais la V2 n'est pas en production. Sur une instance qui aurait des
  clôtures réelles avec chèques, un backfill serait **nécessaire** — et le ré-export LNE
  produirait alors un ZIP au hash différent.

**Traductions :** cette modification ajoute **12 chaînes traduisibles** — 8 messages de
refus dans `views.py`, le libellé « Chèque » (déjà présent dans le `.po` FR) et 3
libellés de champ dans `models.py`. Ces trois derniers sont en anglais, comme leurs
voisins immédiats du même modèle, alors que la règle du projet veut des msgid en
français : à trancher au moment du workflow. **Le workflow i18n est à lancer par le
mainteneur.**

**Non couvert par un test automatique :** la clôture journalière **automatique**
(`tasks.py:489`) remplit `total_cheque` de la même façon que la clôture manuelle, qui est
testée — mais son déclenchement dépend de l'heure locale du tenant, et n'est pas rejoué
en test. La clôture manuelle et l'agrégation mensuelle le sont.

---

## Comment tester (a la main) / Manual test

Prérequis : un tenant avec `module_caisse` actif et une monnaie locale (asset TLF).

### Créer les deux produits

Dans l'admin, deux produits de catégorie de vente :

| Produit | Méthode caisse | Prix | Asset |
|---|---|---|---|
| `Consigne` | Vente | **+1,00 €** | — |
| `Retour Consigne` | **Retour de consigne** | **−1,00 €** | la monnaie locale (TLF) |

L'asset se pose sur le **produit**, jamais sur le prix : un `Price` porteur d'un asset
est ignoré en silence par le panier, avec le message trompeur « n'a pas de prix EUR
publié ».

⚠ **`Product.asset` n'est exposé dans aucun formulaire de l'admin** (il est normalement
rempli par le signal `post_save` de `fedow_core.Asset`, pour les produits de recharge).
Hors données de démo, il faut donc le poser au shell :
```python
produit.asset = Asset.objects.get(category=Asset.TLF, tenant_origin=tenant)
produit.save()
```
Le rendre éditable dans l'admin est la suite naturelle de ce chantier — sans quoi le
message « Prévenez le gestionnaire » désigne une action que le gestionnaire ne peut pas
faire.

**Le produit ne doit porter aucune TVA, et le tenant non plus.**
`LigneArticle._compute_default_vat` (`BaseBillet/models.py:3523`) lit `Product.tva`,
puis retombe sur `Configuration.vat_taxe` — il ne consulte **jamais**
`CategorieProduct.tva`. Sur un tenant dont `vat_taxe` est non nul, un retour de consigne
produirait donc une TVA négative et une écriture FEC négative, même avec une catégorie
non taxée. La consigne est un dépôt de garantie, pas un produit taxé.

### Test 1 — rendre une consigne en espèces
1. Au POS, mettre `Retour Consigne` au panier. Le total s'affiche en positif.
2. Attendu à l'écran de paiement : **seuls** ESPÈCE et CASHLESS. Ni carte bancaire ni
   chèque, même si le point de vente les accepte.
3. Payer en espèces. Attendu : « Retour de consigne ok — A rembourser : 1,00 € ».
4. Vérifier que le tiroir a bien baissé : la clôture doit montrer 1,00 € de moins en
   espèces.

### Test 2 — rendre une consigne sur la carte du client
1. Même geste, scanner une carte NFC, payer en CASHLESS.
2. Attendu : la carte est **créditée** de 1,00 € (et non débitée).
3. Vérification en base :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from fedow_core.models import Token
from BaseBillet.models import LigneArticle
tenant = Client.objects.get(schema_name='<votre schema>')
with tenant_context(tenant):
    carte = CarteCashless.objects.get(tag_id='<TAG>')
    wallet = carte.user.wallet if carte.user else carte.wallet_ephemere
    for token in Token.objects.filter(wallet=wallet):
        print('solde :', token.asset.name, token.value)
    ligne = LigneArticle.objects.filter(carte=carte).latest('datetime')
    print('ligne  :', ligne.amount, ligne.payment_method)
"
```
Le solde doit avoir **augmenté** de 100, et `ligne.amount` valoir **−100** avec le moyen
`LE`. Les deux ensemble : l'argent est rendu, et la comptabilité l'enregistre comme une
sortie.

### Test 3 — les refus
- Payer un retour de consigne en **carte bancaire** ou en **chèque** (POST forgé, le
  bouton n'existe pas) : attendu **400**, message « Un retour de consigne se rembourse
  en espèces ou sur la carte du client. », et **aucune** ligne en base.
- Mettre une bière **et** un retour de consigne au même panier : attendu **400**,
  « Un retour de consigne se règle seul, sans autre article dans le panier. »
- Retirer l'asset du produit `Retour Consigne`, puis payer en cashless : attendu 400,
  aucun crédit.

### Test 4 — le stock ne bouge pas
1. Associer un `Stock` au produit `Retour Consigne`, quantité 10.
2. Rendre une consigne. Attendu : le stock vaut **toujours 10**.
3. Mettre la quantité à 0 avec « vente hors stock » interdite, et rendre une consigne.
   Attendu : **ça passe** — le client rapporte un gobelet, il ne peut pas en manquer.

### Test 5 — le chèque va jusqu'à l'archive
1. Encaisser une vente par **chèque** au POS.
2. Clôturer la caisse depuis le comptoir.
3. Attendu sur la clôture : `total_cheque` renseigné, et
   `especes + carte + cashless + cheque == total_general`.
   ⚠ Cette identité vaut tant qu'aucun paiement **fédéré** (`STRIPE_FED`) n'a lieu :
   `reports.py:242` l'inclut dans le total général, mais `ClotureCaisse` n'a pas de
   colonne pour lui. Même trou que le chèque, autre moyen — chantier séparé.
4. Le CSV et le PDF de clôture montrent une ligne « Chèque ».
5. Générer l'archive LNE : la colonne `total_cheque` porte le **vrai** montant.
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from laboutik.models import ClotureCaisse
tenant = Client.objects.get(schema_name='<votre schema>')
with tenant_context(tenant):
    c = ClotureCaisse.objects.latest('datetime_cloture')
    print('especes  :', c.total_especes)
    print('carte    :', c.total_carte_bancaire)
    print('cashless :', c.total_cashless)
    print('cheque   :', c.total_cheque)
    print('general  :', c.total_general)
    print('somme des moyens == general ?',
          c.total_especes + c.total_carte_bancaire + c.total_cashless + c.total_cheque
          == c.total_general)
"
```

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_pos_retour_consigne.py \
  tests/pytest/test_pos_paiement_cheque.py \
  tests/pytest/test_rapports_cheque.py -v
```
30 tests couvrent ce chantier (18 + 3 + 9).

**Validation par mutation : 16 mutations**, chacune cassant volontairement un point
précis du correctif et faisant tomber **exactement** le ou les tests qui le surveillent —
détection par méthode, garde du panier mixte, garde CB/chèque, valeur absolue du crédit,
garde de l'asset manquant, garde de l'asset cadeau, exclusion du stock (les deux points),
élargissement abusif de cette exclusion, mapping du chèque, remplissage de la clôture
manuelle, agrégation des clôtures mensuelles, garde des monnaies multiples,
archive LNE, CSV, PDF.

Cela ne veut pas dire que les 30 tests ont chacun leur mutation : quelques-uns
documentent un comportement déjà correct (la ligne négative en espèces, le solde de
caisse qui baisse de lui-même) et servent de garde-fous contre une régression future.
