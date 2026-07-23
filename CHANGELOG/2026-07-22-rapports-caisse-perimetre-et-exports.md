# Rapports de caisse : perimetre et exports repares / Register reports: scope and exports fixed

**Date :** 2026-07-22
**Migration :** Non

## Resume / Summary

**Quoi / What :** Le ticket X et le ticket Z voyaient un perimetre de ventes incomplet, et
leurs exports PDF / CSV sortaient sans aucun detail. Les deux sont corriges.
/ The X and Z tickets covered an incomplete sales scope, and their PDF/CSV exports came out
with no detail at all. Both are fixed.

**Pourquoi / Why :** Deux defauts distincts, tous deux silencieux — aucune erreur, seulement
des montants faux ou des sections vides.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `fedow_core/services.py` | `rembourser_en_especes` ecrit `sale_origin=LABOUTIK` (etait `ADMIN`) |
| `laboutik/reports.py` | Nouvelle constante `ORIGINES_ENCAISSEES_PAR_LE_LIEU` ; nouvelle fonction `sections_de_detail_pour_export()` |
| `laboutik/pdf.py` | Lit les sections traduites au lieu de cles inexistantes |
| `laboutik/csv_export.py` | Idem |
| `tests/pytest/test_cloture_export.py` | **+4 tests** partant d'un rapport reellement produit par le service |
| `tests/pytest/test_card_refund_service.py`, `test_pos_vider_carte.py`, `test_remboursement_especes_trace_comptable.py` | Assertions basculees de `ADMIN` vers `LABOUTIK` ; les deux `xfail` retires |

---

## Defaut 1 — le remboursement de carte etait invisible du rapport

`WalletService.rembourser_en_especes` etiquetait ses lignes `sale_origin=ADMIN`, alors que
son **unique appelant** est la caisse (`laboutik/views.py`, flow « vider une carte », avec
carte primaire et controle d'acces au point de vente). Le rapport ne lisant que les lignes de
caisse, un remboursement disparaissait : ni dans les totaux, ni dans la section
remboursements, ni dans le solde de caisse.

**Scenario** : un client fait vider sa carte, le caissier lui rend 15 € du tiroir. Le ticket Z
annonce 500 € d'especes, le tiroir en contient 485 €, et l'ecart n'est explique nulle part.

Corrige a la source plutot que dans le rapport : elargir le filtre du rapport a `ADMIN` aurait
fait entrer les virements bancaires recus (`PaymentMethod.TRANSFER`), les avoirs et les
adhesions saisies a la main dans le tiroir-caisse. Le defaut etait l'etiquette, pas le filtre.

## Defaut 2 — le perimetre du rapport

Le filtre est desormais une constante nommee et commentee, `ORIGINES_ENCAISSEES_PAR_LE_LIEU`,
avec le critere ecrit noir sur blanc : **cet encaissement a-t-il eu lieu au comptoir, dans le
perimetre que le caissier cloture en fin de service ?**

| Origine | Dans le rapport ? | Pourquoi |
|---|---|---|
| `LABOUTIK` | oui | la caisse, remboursements compris |
| `TIREUSE` | **oui — c'etait le trou** | une biere tiree est une vente du comptoir ; elle porte un point de vente et decremente le stock |
| `QRCODE_MA`, `NFC_MA` | non | autre usage : les lieux qui pratiquent l'un ne pratiquent pas l'autre |
| `LESPASS`, `API`, `WEBHOOK` | non | ventes en ligne, suivies par `comptabilite/services.py` qui exclut justement `LABOUTIK` |
| `ADMIN` | non | avoirs, virements, adhesions saisies a la main : hors tiroir |

**Le trou de la tireuse** : un lieu avec 800 € tires a la tireuse et 200 € au comptoir voyait
200 € au ticket Z. Le stock des futs etait decompte sans recette en face, donc la marge
affichee etait fausse.

**Chantier a venir** : rattacher les encaissements QR code / NFC a un point de vente. Leur
place dans la cloture se reposera a ce moment-la.

## Defaut 3 — PDF et CSV de cloture sans aucun detail

`laboutik/pdf.py` et `laboutik/csv_export.py` lisaient `par_produit`, `par_categorie`,
`par_tva` et `commandes`. `generer_rapport_complet()` produit `totaux_par_moyen`,
`detail_ventes`, `tva`, `solde_caisse`… — **aucune intersection**. Et comme les exports
utilisent `.get(cle, {})`, aucune erreur n'etait levee : les sections sortaient vides.

**Scenario** : le gerant recoit par mail le PDF de cloture de sa soiree. En-tete et totaux
presents, sections produits / categories / TVA vides. Il ne peut pas justifier sa ventilation
TVA.

**Pourquoi personne ne le voyait** : `test_cloture_export.py` fabriquait un `rapport_json` a
la main, avec exactement les anciennes cles. Le test passait, et ne pouvait structurellement
pas voir le probleme.

La correction passe par `sections_de_detail_pour_export()` (`laboutik/reports.py`), partagee
par les deux exports. Elle traduit `detail_ventes` (groupe par categorie) vers les sections a
plat, et **renvoie tel quel** le contenu des cloture archivees avant le changement de format —
une cloture d'il y a deux ans doit se reimprimer a l'identique.

La section `commandes` n'a plus aucune source dans le rapport. Le gabarit et le CSV la
conditionnent, elle disparait donc proprement.

---

## Comment tester (a la main) / Manual test

### Test 1 — un remboursement pese sur le ticket Z

1. Caisse → vider une carte portant de la monnaie locale, rendre les especes.
2. Ticket X (rapport temps reel) : le total especes doit avoir **diminue** du montant rendu.
3. Cloturer : le ticket Z doit refleter la meme diminution.

### Test 2 — le PDF de cloture contient le detail

1. Faire au moins une vente au comptoir, puis cloturer.
2. Telecharger le PDF de la cloture depuis l'admin.
3. Les sections « detail par produit », « par categorie » et « ventilation TVA » doivent etre
   **remplies**. Avant le correctif, elles etaient absentes.
4. Meme verification sur le CSV, et sur le mail de cloture qui porte les deux en pieces jointes.

### Test 3 — la tireuse entre dans le chiffre d'affaires

1. Servir un volume depuis une tireuse connectee, sur une carte creditee.
2. Ticket X : le total cashless doit inclure ce montant.
3. La ventilation par point de vente doit faire apparaitre le PV de la tireuse.

### Tests automatiques

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_cloture_export.py -v
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_remboursement_especes_trace_comptable.py -v
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

Etat au moment de l'ecriture : **1019 tests verts**, aucun echec.

## Ce qui reste a faire / Remaining work

L'audit de couverture a montre que **les tests de vente verifient que la vente est creee, mais
presque jamais qu'elle pese sur le ticket Z**. Un seul test du depot faisait ce lien avant ce
chantier (`test_paiement_complementaire.py`, cascade NFC fractionnee). Les familles non
couvertes de bout en bout : especes/CB au comptoir, billetterie POS, tireuse connectee,
recharges cashless, adhesions vendues en caisse.

Par ailleurs, les tests de cloture (`test_cloture_caisse.py`, `test_cloture_enrichie.py`)
injectent leurs lignes directement en base avec `sale_origin` code en dur, sans passer par la
route de paiement. Ils valident l'arithmetique du rapport mais sont **structurellement
incapables** de detecter une regression dans l'attribution de l'origine, du statut ou du point
de vente — c'est exactement le mecanisme qui a laisse passer le defaut 1.
