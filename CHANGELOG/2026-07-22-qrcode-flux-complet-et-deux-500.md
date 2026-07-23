# Paiement par QR code : flux teste, deux erreurs serveur corrigees
# / QR code payment: flow tested, two server errors fixed

**Date :** 2026-07-22
**Migration :** Non

## Resume / Summary

**Quoi / What :** 18 tests couvrant le parcours complet du paiement par QR code depuis « Ma
tirelire » — generation, scan, confirmation — et la correction de deux erreurs serveur qu'ils
ont revelees.
/ 18 tests covering the full QR code payment journey, plus two server errors they revealed.

**Pourquoi / Why :** Ce parcours n'avait **aucun test**. Le seul fichier qui touchait
`qrcodescanpay` verifiait les permissions d'acces aux ecrans, jamais ce qui s'y passe. Cinq
routes etaient sans couverture : `generate_qrcode`, `process_qrcode`, `valid_payment`,
`process_with_nfc`, `check_payment`.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/.../insufficient_funds.html` | `{% load %}` complete : le filtre `dround` manquait |
| `BaseBillet/views.py` — `generate_qrcode` | Le montant est verifie AVANT d'etre converti |
| `tests/pytest/test_qrcodescanpay_flux_complet.py` | **Nouveau** — 18 tests |

---

## Erreur serveur 1 — l'ecran « fonds insuffisants » repondait 500

`insufficient_funds.html` chargeait `{% load i18n static %}` et utilisait deux fois le filtre
`dround`, qui vit dans `tibitags`. Un `{% load %}` n'est **jamais herite** du gabarit parent :
le rendu levait `TemplateSyntaxError: Invalid filter: 'dround'`.

**Scenario** : un adherent scanne un QR code de 12,50 € alors qu'il n'a que 8 € sur sa carte.
Au lieu de l'ecran qui lui explique qu'il doit recharger, il recoit une erreur serveur. Il n'a
aucun moyen de comprendre ce qui s'est passe, ni de savoir si son compte a ete debite.

Les quatre autres gabarits du dossier chargent bien `tibitags` — celui-ci etait le seul oubli,
et c'est aussi le seul que personne n'avait jamais affiche en test.

## Erreur serveur 2 — generer un QR code sans montant repondait 500

`generate_qrcode` convertissait d'abord (`Decimal(data.get('amount'))`), verifiait ensuite. Sur
un POST sans montant, `Decimal(None)` levait une `TypeError` avant que le garde-fou ne soit
atteint. Le meme chemin cassait sur un montant non numerique (`InvalidOperation`).

La verification passe donc avant la conversion, et la conversion est encadree. Le message
d'erreur existant est reutilise tel quel.

---

## Ce que les tests couvrent

**Generation** — la ligne creee reste EN ATTENTE (une ligne validee compterait dans le chiffre
d'affaires avant que quiconque ait paye), porte le montant demande, l'origine QR code, et garde
en memoire l'encaisseur qui l'a demandee.

**Scan, selon l'utilisateur** — c'est ce qui distingue les cas, puisque le solde depensable vient
du Fedow distant :

| Situation du scanneur | Attendu |
|---|---|
| non connecte | envoye au login, avec retour prevu vers le QR code |
| email non confirme | renvoye au compte : payer engage de l'argent |
| sans portefeuille | le portefeuille est cree a la volee |
| portefeuille vide | ecran « fonds insuffisants », solde a 0 |
| solde inferieur au montant | ecran « fonds insuffisants » |
| solde suffisant | ecran de validation |
| QR code inconnu | message lisible, pas d'erreur serveur |
| QR code deja paye | refus : la garde anti-rejeu, le QR code reste affiche apres paiement |

**Confirmation** — la ligne en attente est **remplacee** par une ligne validee par transaction
Fedow (une ligne en attente qui survivrait resterait encaissable une seconde fois), le moyen de
paiement suit la monnaie reellement debitee (federee ou locale), un paiement reparti sur deux
monnaies produit deux lignes dont la somme fait le montant demande, et un refus pour fonds
insuffisants ne consomme pas la ligne — l'adherent peut recharger et rescanner.

Fedow est mocke : les vues l'importent **localement** dans la methode, donc le patch vise
`fedow_connect.fedow_api.FedowAPI` et non un attribut de `BaseBillet.views`.

---

## Comment tester (a la main) / Manual test

### Test 1 — l'ecran de fonds insuffisants s'affiche

1. Avec un compte habilite : `/qrcodescanpay/get_generator/`, generer un QR code d'un montant
   superieur au solde d'un compte de test.
2. Avec ce compte de test, scanner le QR code.
3. L'ecran doit annoncer le montant requis et le solde disponible. Avant le correctif : page
   d'erreur serveur.

### Test 2 — un montant vide ne casse pas la page

1. Sur le generateur, soumettre sans saisir de montant.
2. Retour au generateur avec un message d'erreur. Avant le correctif : erreur serveur.

### Test 3 — un QR code ne se paie qu'une fois

1. Generer, payer avec un compte suffisamment approvisionne.
2. Rescanner le meme QR code, avec le meme compte ou un autre.
3. Le message doit indiquer que ce paiement a deja ete traite.

### Tests automatiques

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_qrcodescanpay_flux_complet.py -v
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

Etat au moment de l'ecriture : **1053 tests verts**, aucun echec.

## Les monnaies acceptees au paiement

Les deux vues de paiement traduisent la categorie de monnaie renvoyee par le Fedow en moyen de
paiement comptable. Elles n'en connaissent que DEUX :

| Categorie Fedow | Moyen de paiement | Teste |
|---|---|---|
| `FED` — monnaie federee du reseau | `STRIPE_FED` | oui |
| `TLF` — token local fiduciaire (legacy) | `LOCAL_EURO` | oui |
| `TNF` — cadeau | *aucun* | oui, constate |
| `TIM` — monnaie temps | *aucun* | oui, constate |
| `FID` — points de fidelite | *aucun* | oui, constate |

**Constat verrouille par un test** : si le Fedow debite un bon cadeau, des heures de benevolat
ou des points de fidelite, la traduction echoue et **aucune vente n'est enregistree** — alors
que le portefeuille a bien ete debite cote Fedow. L'adherent perd sa monnaie sans contrepartie
comptable.

`test_une_monnaie_non_fiduciaire_ne_produit_aucune_vente` decrit ce comportement pour les trois
categories, et echouera le jour ou elles seront prises en charge.

Non corrige ici : decider du moyen de paiement a attribuer a un bon cadeau ou a des heures de
benevolat est une question comptable, pas technique.

**Note sur les mocks** : `fedow_api.asset.retrieve()` interroge le Fedow distant par le reseau.
Les tests simulent sa reponse ; ils ne verifient donc pas que le Fedow classe correctement ses
propres assets, seulement que Lespass reagit correctement a chaque classement possible.

## Ce que couvrent les deux routes ajoutees

**`check_payment`** — l'ecran du caissier interroge cette route en boucle pour savoir si le QR
code affiche a ete paye. Teste : un paiement en attente n'est pas annonce comme recu, un
paiement valide l'est, et un adherent lambda ne peut pas sonder l'etat des paiements du lieu.

**`process_with_nfc`** — meme paiement, mais l'adherent presente sa carte au lecteur du caissier.
Teste : tag mal forme, carte inconnue du Fedow, carte anonyme (portefeuille ephemere), paiement
deja regle (garde anti-rejeu), solde insuffisant (refus AVANT tout debit), cas nominal, trace de
la lecture (tag, lecteur, porteur), et reservation aux membres habilites.

Deux details du comportement reel, decouverts en ecrivant ces tests : la vue repond **202** avec
un JSON de confirmation, et elle enregistre la vente sous l'origine **NFC**, pas celle du QR
code — c'est le canal reellement emprunte qui compte.

## Ce qui reste a couvrir / Still uncovered

- Le rattachement des encaissements QR code / NFC a un point de vente — chantier a venir. Tant
  qu'il n'est pas fait, ces ventes restent hors du ticket Z, ce que verrouille
  `test_ventes_remontent_au_ticket_z.py`.
- L'envoi des courriels de confirmation (admin et payeur) apres un paiement reussi : les taches
  Celery sont declenchees mais leur contenu n'est pas verifie.
