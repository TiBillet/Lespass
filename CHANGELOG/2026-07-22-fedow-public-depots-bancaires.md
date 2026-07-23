# Remises en banque : couverture de test + garde sur les monnaies encaissables
# / Bank deposits: test coverage + guard on collectable currencies

**Date :** 2026-07-22
**Migration :** Non

## Resume / Summary

**Quoi / What :** 15 tests sur l'app `fedow_public` (ventilation d'une monnaie par lieu,
historique des remises en banque, releve de transactions, et la remise elle-meme), plus une
garde serveur qui limite les paiements par QR code aux monnaies adossees a l'euro.
/ 15 tests on the fedow_public app, plus a server-side guard limiting QR code payments to
euro-backed currencies.

**Pourquoi / Why :** Cette app n'avait **aucun test**, alors qu'elle sert en production a
suivre de l'argent reel : une association qui rembourse ses producteurs, un festival qui
declare avoir recu son virement.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Constante `TYPES_DE_MONNAIE_ENCAISSABLES_PAR_QRCODE` + garde dans `generate_qrcode` |
| `tests/pytest/test_handlers_erreur.py` | Fixture de protection : pose `public` en setup (voir plus bas) |
| `tests/pytest/test_fedow_public_depots_bancaires.py` | **Nouveau** — 15 tests |

---

## Garde sur les monnaies encaissables par QR code

Le formulaire du generateur ne proposait deja que « EURO » — « CADEAU » et « TEMPS » y sont
`disabled` (`generator.html`). Mais rien ne le validait cote serveur : un POST se falsifie.

Les deux vues de paiement ne savent traduire que deux categories Fedow en moyen de paiement
comptable : `FED` (monnaie federee) et `TLF` (token local fiduciaire). Toute autre monnaie
serait debitee par le Fedow **sans qu'aucune vente ne puisse etre enregistree en face** —
l'adherent perdrait sa monnaie sans contrepartie.

La garde vit desormais dans `generate_qrcode` : un type de monnaie non encaissable renvoie au
generateur avec un message, sans creer de demande de paiement.

Note : cela ne ferme pas completement le sujet. C'est le Fedow distant qui decide dans quelle
monnaie il debite lors de la cascade ; si sa cascade puise dans un token cadeau, le probleme
reapparaitrait au moment de la traduction. Le comportement est verrouille par
`test_une_monnaie_non_fiduciaire_ne_produit_aucune_vente`
(`tests/pytest/test_qrcodescanpay_flux_complet.py`).

---

## Ce que couvrent les 15 tests

**Qui peut consulter** — la ventilation d'une monnaie par lieu et l'historique des remises
exposent la tresorerie : un adherent et un visiteur anonyme sont refuses, un uuid inconnu
repond 404 sans casser la page.

**Ce que la page affiche** — la repartition de la monnaie entre les lieux (ce qui permet de
savoir combien chacun detient avant de declencher un virement), l'historique des remises
passees (la piece justificative du gestionnaire), le cas d'une monnaie neuve sans aucune
remise, et le cas ou le Fedow renvoie sa ventilation en JSON deja serialise plutot qu'en
dictionnaire — la vue accepte les deux formes, et ne traiter que l'une ferait afficher une page
vide sans erreur, avec de l'argent bien reel derriere.

**Le releve de transactions** — tri chronologique impose (le Fedow ne garantit pas l'ordre de sa
reponse, et un releve en desordre est inutilisable pour un rapprochement), refus d'une periode
a l'envers et d'une demande sans dates **sans appeler le Fedow**, et reservation aux
gestionnaires.

**La remise en banque** — le test central verifie que la demande part avec **exactement** le
portefeuille et l'asset choisis : se tromper de portefeuille viderait la monnaie d'un autre
lieu, se tromper d'asset remettrait en banque une monnaie que le lieu n'a pas encaissee, et le
Fedow obeit sans pouvoir verifier a notre place. Plus : un refus du Fedow ne passe pas pour un
succes (annoncer une remise qui n'a pas eu lieu fausserait le rapprochement bancaire), un succes
est confirme a l'ecran, et un adherent ne peut pas declencher l'operation.

### Ou se fait la decrementation, et ce que les tests prouvent

C'est le Fedow **distant** qui decremente le token : Lespass poste
`wallet/local_asset_bank_deposit`, le Fedow debite et renvoie la transaction creee
(`fedow_connect/fedow_api.py`).

Les tests prouvent donc deux choses, et deux seulement :

1. la demande part avec le bon portefeuille et le bon asset ;
2. la reponse du Fedow, dont le solde deja decremente, est fidelement affichee.

Ils ne prouvent **pas** que le Fedow decremente correctement — c'est le travail de sa propre
suite. Verifie par mutation : remplacer le portefeuille vise par celui d'origine de l'asset
fait echouer le test central.

---

## Effet de bord traite : un test voisin devenu rouge

Ajouter ce fichier a fait tomber
`test_handlers_erreur.py::test_handler404_sur_schema_public_ne_touche_pas_la_base`, qui passait
seul : « Expected to perform 0 queries but 1 was done ».

Cause : ce test verifie qu'une 404 se rend **sans aucune requete SQL sur le schema public**. Le
nouveau fichier passe par des clients HTTP, ce qui colle la connexion sur le tenant `lespass` —
et l'ordre alphabetique le place juste avant. La garde testee ne s'appliquant qu'au schema
public, une requete partait.

Correction conforme a la regle du projet (`tests/PIEGES.md` 12.5.bis) : **c'est la victime qui
se protege, en SETUP**. `test_handlers_erreur.py` pose desormais `public` lui-meme via une
fixture `module`-scoped sans teardown, comme le fait deja `test_fedow_core.py`.

---

## Comment tester (a la main) / Manual test

### Test 1 — la page des remises en banque

1. En tant que gestionnaire, ouvrir `/fedow/asset/<uuid-d-une-monnaie-locale>/retrieve_bank_deposits/`.
2. La ventilation par lieu doit lister les lieux detenant la monnaie et leurs totaux.
3. L'historique doit lister les remises passees, avec date, montant et organisation remettante.

### Test 2 — une remise en banque decremente bien

1. Noter le total du lieu dans la ventilation.
2. Declencher la remise en banque pour ce portefeuille depuis l'admin.
3. Recharger la page : le total du lieu doit avoir diminue du montant remis, et une nouvelle
   ligne doit apparaitre dans l'historique.

C'est le seul controle qui verifie la decrementation reelle cote Fedow — les tests
automatiques s'arretent a la demande et a l'affichage.

### Test 3 — le releve de transactions

1. Sur la meme page, demander les transactions d'une periode.
2. Verifier l'ordre chronologique croissant.
3. Saisir une date de fin anterieure au debut : un message d'erreur, pas de releve.

### Tests automatiques

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_fedow_public_depots_bancaires.py -v
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

Etat au moment de l'ecriture : **1081 tests verts**, aucun echec.

## Ce qui reste a couvrir / Still uncovered

- `global_asset_bank_stripe_deposit` (`fedow_connect/fedow_api.py`) : la remise en banque de la
  monnaie federee, distincte de la remise locale testee ici. Aucun test.
- Le comportement des trois vues quand le Fedow distant est injoignable : aucune n'a de garde,
  une panne reseau y produit une erreur serveur.
