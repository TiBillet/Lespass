# Produit archivé et produit actif du même nom — limites à traiter / Archived and active product with the same name — open limits

**Date :** 2026-09-30
**Origine :** la contrainte d'unicité (catégorie, nom) de `Product` ne s'applique plus
qu'aux produits non archivés.
Voir `CHANGELOG/2026-09-30-produit-archive-ne-bloque-plus-son-nom.md`.

Depuis ce changement, un produit archivé et un produit actif peuvent porter le même nom
dans la même catégorie. Plusieurs endroits du code supposaient qu'un nom désigne un seul
produit. Ce fichier liste ce qui a été relevé mais **non traité**, avec le risque concret
et le correctif envisagé.
/ Items found and deliberately left undone, with the concrete risk and the planned fix.

---

## 1. Rapports de caisse et comptabilité : ventes fusionnées par nom

**Ce qui se passe.** Les rapports regroupent les ventes par *nom* de produit, pas par
identifiant. Si « Concert » est archivé puis recréé, les ventes de l'ancien et du nouveau
produit sont additionnées sur une seule ligne « Concert ».

**Où.**
- `comptabilite/services.py:231-236` : regroupement par (catégorie, nom, TVA, offert).
- `laboutik/reports.py:347-363` puis la clé `(catégorie, produit, taux de TVA)` construite
  juste après : deux produits homonymes finissent sur la même ligne.
- `laboutik/reports.py:431-434` : le poids ou volume vendu est filtré par nom seul.
  Les quantités des deux produits sont additionnées, et l'unité (grammes ou centilitres)
  est prise sur un seul des deux.
- Même regroupement par nom dans `laboutik/reports.py` lignes 592, 713, 788 et 1005.

**Risque.**
- Les totaux restent justes : rien n'est perdu ni compté deux fois.
- On ne peut plus distinguer l'ancien produit du nouveau dans un rapport.
- Si les deux produits n'ont pas le même prix d'achat, le coût et la marge de la ligne
  fusionnée sont faux (le prix d'achat retenu est celui d'un seul des deux).
- Si les deux produits n'ont pas la même unité de stock, le poids total mélange des
  grammes et des centilitres.

**Déjà vrai avant.** Deux produits du même nom dans deux catégories différentes étaient
déjà fusionnés dans les rapports de caisse (`laboutik/reports.py` ne regroupe pas par
catégorie d'article). Le changement rend le cas plus fréquent.

**Correctif envisagé.** Regrouper par identifiant du produit
(`pricesold__productsold__product__uuid`) et n'utiliser le nom que pour l'affichage.
Pour le poids vendu, filtrer par identifiant au lieu du nom.

---

## 2. Produits « système » retrouvés par leur nom

**Ce qui se passe.** Certains produits sont créés automatiquement par le code, qui les
retrouve ensuite avec `get_or_create` sur leur nom. `get_or_create` plante en
`MultipleObjectsReturned` (erreur 500) dès que deux produits correspondent.

**Où.**
- `BaseBillet/views.py:1871` : « Sale via QR code link », catégorie `QRCODE_MA`.
- `Administration/management/commands/launch_payment.py:90` : « Sale via management
  command », catégorie `QRCODE_MA`.
- `api_v2/views.py:966` : « Recharge {nom de l'asset} », catégorie `RECHARGE_CASHLESS`.
- `fedow_core/signals.py:121` : « {préfixe} {nom de l'asset} », cherché par **nom seul**,
  sans la catégorie.

**Scénario qui casse.**
1. Un admin archive un de ces produits.
2. Il crée à la main un produit du même nom dans la même catégorie (possible depuis
   ce changement).
3. Le prochain paiement par lien QR code, ou la prochaine recharge par l'API, plante.

**Deuxième effet, sans plantage.** Si le produit système est archivé et qu'aucun autre
ne porte son nom, `get_or_create` retrouve le produit archivé et la vente se fait dessus.
Ce comportement existait déjà avant.

**Cas non concerné.** « Free booking » (`BaseBillet/validators.py:1302`,
`batch_new_tenant.py:227`) : la création est protégée par un test « aucun produit de
réservation gratuite n'existe », et ne tourne qu'à la création d'un lieu.

**Déjà vrai avant.** `fedow_core/signals.py:121` cherchait déjà par nom seul : deux
produits du même nom dans deux catégories le faisaient déjà planter.

**Correctif envisagé.** Dans chaque `get_or_create`, ajouter `archive=False` à la
recherche : le code retrouve le produit actif, ou en recrée un si le seul existant est
archivé. Pour `fedow_core/signals.py`, chercher plutôt par le lien `asset` que par le nom.

---

## 3. Message « Désarchiver » non traduit

**Ce qui se passe.** Quand on désarchive un produit dont le nom est pris par un produit
actif, l'admin affiche :
« A product named « … » already exists. Rename one of them before unarchiving. »
Ce message s'affiche en anglais, même pour un admin en français.

**Où.** `Administration/admin/products.py`, action `desarchive`.

**Pourquoi ce n'est pas fait.** `makemessages` a été lancé plus tôt dans la journée et a
réécrit `locale/fr` et `locale/en` en entier (environ 11 000 lignes, plus de 400 entrées
« fuzzy »). Tant que le sort de cette régénération n'est pas décidé (la garder, ou
`git checkout -- locale/`), ajouter une traduction n'a pas de sens : elle serait perdue
ou noyée.

**Sont dans le même cas**, ajoutés le même jour :
- `%(name)s (will be archived, past sales are kept)` (archivage des tarifs) ;
- `The price "%(name)s" was archived. Past sales are kept.` (archivage des tarifs).
  Ces deux-là sont traduits dans le fichier régénéré, mais pas compilés.

**Correctif envisagé.** Décider du sort des fichiers `.po`, relancer `makemessages`
(avec `-i "laboutik_client_android_v2/*"`, sinon il échoue sur un problème de droits),
relire les « fuzzy », ajouter la traduction française, puis `compilemessages`.

---

## 4. Vérifications non faites / Checks not done

- **Aucun clic dans l'admin.** Le refus de désarchiver est testé sur la fonction de
  contrôle `un_autre_produit_non_archive_porte_ce_nom`, pas sur l'action elle-même :
  Unfold vérifie les droits dans l'action et le test n'a pas d'admin connecté. À dérouler
  à la main : `A TESTER et DOCUMENTER/produit-archive-ne-bloque-plus-son-nom.md`, test 3.
- **Formulaire produit.** Le test vérifie que `validate_constraints()` refuse un doublon
  actif. L'affichage de l'erreur dans le formulaire admin (création, et décochage de
  « Archive » dans la fiche) n'a pas été vérifié à l'écran.
- **Import d'adhésions.** Le filtre « produits non archivés » n'a pas de test automatique
  (test 4 de la fiche « A TESTER »).
- **Migration en production.** La migration `0232` a été appliquée sur la base de dev
  seulement. Elle ne peut pas échouer sur des données existantes (la nouvelle contrainte
  est moins stricte que l'ancienne), mais elle n'a pas été jouée sur une copie de prod.
- **Retour arrière.** Dès qu'un lieu a un produit archivé et un produit actif du même nom,
  ou deux produits archivés du même nom, on ne peut plus remettre l'ancienne contrainte
  sans renommer ces produits.

---

## 5. Tests en échec dans la base de dev

Aucun des deux ne teste ce changement, mais ils sortent en rouge dans la suite complète.

- `tests/pytest/test_pos_models.py::test_create_test_pos_data_command` : il compare le
  nombre d'adhésions publiées au contenu du point de vente « Adhesions ». La base de dev
  contient un produit adhésion « TEST », archivé et non publié, encore rattaché à ce point
  de vente : 159 produits dans le point de vente pour 158 adhésions publiées.
  Piste : retirer ce produit du point de vente, ou faire comparer le test aux seuls
  produits publiés du point de vente.
- `tests/pytest/test_caisse_navigation.py::TestCartePrimaireVue::test_carte_non_primaire` :
  la vue « carte primaire » de la caisse renvoie une réponse vide. Cause non cherchée.
  Il échouait déjà avant ce changement, dès la première suite complète lancée ce jour-là.
