# Chantier 04 — Mélanges de caisses d'argent (tronc commun)

> **Statut** : 📋 SPEC RÉDIGÉE — relue par Fable (×2) et Opus, décisions prises le 2026-09-27, en attente du « go »
> **Date spec** : 2026-09-27
> **Branche** : `main-fedow-import`
> **Contexte** : environnement de **dev uniquement** (pas encore en production).
> Aucune donnée historique à rattraper. On ne migre AUCUNE ligne existante.

Ce fichier est le **tronc commun** du chantier. Il pose les règles partagées par
toutes les fiches. Chaque fiche (`CHANTIER-04-A` à `F`) se livre et se teste
seule, dans l'ordre du tableau §4.

---

## 1. Objectif

Un montant d'argent enregistré par Lespass doit être **juste** et **à sa place** :

- pas d'argent inventé (des points de fidélité comptés comme des euros) ;
- pas d'argent perdu (un paiement réparti sur deux monnaies qui enregistre 5,20 €
  au lieu de 10 €) ;
- pas de mélange (un cadeau compté dans la TVA, une vente en points comptée dans
  le total du ticket Z) ;
- une trace inaltérable pour toutes les ventes (chaînage HMAC LNE).

## 2. La règle d'or : `total = amount × qty`

C'est la convention du projet. Toutes les fiches s'y conforment.

| Champ de `LigneArticle` | Sens |
|---|---|
| `amount` | **Prix UNITAIRE**, en centimes (entier). Jamais la part d'argent d'un paiement réparti. |
| `qty` | Quantité, `Decimal(12, 6)`. Peut être fractionnaire quand un article est payé avec plusieurs monnaies. |
| `total()` | `int(amount × qty)` — le montant de la ligne. |

Références qui respectent déjà la règle :

- `laboutik/reports.py` → `montant_ttc_centimes()` : `Round(Sum(F("amount") * F("qty")))` ;
- `BaseBillet/models.py` → `LigneArticle.total()` ;
- `laboutik/views.py` → `_creer_lignes_articles_cascade()` : un article payé avec
  deux monnaies donne deux lignes au même `amount` (prix unitaire), et des `qty`
  partielles calculées par `_calculer_qty_partielles()` (6 décimales, la dernière
  ligne prend le reste pour que la somme des `qty` soit exacte).

**Exemple** — un verre à 10 € payé 6 € en monnaie cadeau et 4 € en monnaie locale :

| Ligne | `amount` | `qty` | `total()` |
|---|---|---|---|
| Cadeau (LG) | 1000 | 0,600000 | 600 |
| Local (LE) | 1000 | 0,400000 | 400 |
| **Somme** | | **1,000000** | **1000** |

Tout code qui lit `amount` seul (sans `qty`) pour en tirer de l'argent est suspect.

**Arrondi** : en Python, pour un montant de ligne, on écrit
`int(Decimal(amount * qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP))`. Le
`round()` de Python arrondit « au pair » (0,5 → 0), alors que `Round()` de
PostgreSQL, utilisé par les rapports, arrondit « loin de zéro » (0,5 → 1).

## 3. Décisions du mainteneur (2026-09-27)

### 3.1 Argent et hors argent

| # | Décision |
|---|---|
| D1 | Les tarifs en **points / temps** (FID, TIM) deviennent **vendables à la caisse**, sur les **articles de vente** et les **adhésions** (pas les recharges ni les billets). Nouveau moyen de paiement **`NM`** (non monétaire), un seul code pour FID et TIM. |
| D2 | Une ligne NM garde **`amount` = prix en unités de la monnaie**. Les calculs d'argent l'excluent. |
| D3 | Le rapport sépare les ventes NM **par nom de monnaie**. |
| D4 | **Une seule monnaie par panier** : euros, OU une seule monnaie non monétaire. Points + heures dans le même panier : refusé. |
| D5 | Un panier en points / temps se paie **uniquement par NFC**. |
| D6 | **OFFRIR** : une carte primaire en **mode gérant** (`CartePrimaire.edit_mode`, lu en base) fait apparaître « OFFRIR » dans les moyens de paiement, comme dans LaBoutik v1. Autorisé pour les articles de vente, les **adhésions et les billets** (la carte primaire passe aussi dans la popup « client identifié »). Refusé : retour de consigne, recharge euros, panier en points, session sans carte primaire. La ligne garde `amount` = prix (valeur offerte), `payment_method = FREE`. |
| D7 | Les lignes `FREE` et `NM` sont exclues de **tout calcul d'argent**. Une seule définition : `MOYENS_HORS_ARGENT = [FREE, NON_MONETAIRE]` et `self.lignes_argent` dans le service de rapport. |
| D8 | Le Z a une section **« Offerts »** (quantités, valeur offerte, coût) et une section **« Non monétaire »** (une ligne par monnaie). La colonne actuelle `qty_offerts` du détail des ventes (articles payés en **monnaie cadeau**, LG) est **libellée « Payé en cadeau »** (les clés JSON ne changent pas). |
| D9 | **Recharges cadeau** (ligne FREE avec montant) : elles restent dans la section « Recharges », sur une ligne **« Cadeau émis (hors argent) »**, hors du total encaissé. |
| D10 | **Billets et adhésions gratuits** (FREE, 0 €) : les sections Billets / Adhésions comptent le **nombre** sur toutes les lignes, et les **montants** sur `lignes_argent` seulement. |
| D11 | **Archive fiscale LNE** : les lignes FREE et NM y restent, avec **`vat = 0`** (règle posée dans `LigneArticle._compute_default_vat`). |
| D12 | La monnaie d'une ligne est choisie par un mapping **sans repli** : une catégorie inconnue est refusée **avant tout débit** (à la classification des articles). |
| D13 | Solde de points insuffisant : **refus simple**, sans 2ᵉ carte. Le solde est comparé à la **somme** du panier. |
| D14 | Tarifs en points **refusés dans les commandes de table** (`ouvrir_commande`, `ajouter_articles`, `payer_commande`). |
| D15 | Correction de moyen de paiement à la caisse (`corriger_moyen_paiement`) : **FREE et NM refusés en source** (la cible est déjà limitée à espèces / CB / chèque). Le menu admin du mapping FEC (`MappingMoyenDePaiementAdmin`) ne propose plus NA ni NM. |
| D16 | **Unité** des points et heures : **centièmes partout** (300 points = 30000), comme la caisse et l'affichage des soldes. L'API v2 (rechargement de portefeuille, qui crédite l'unité brute) est à corriger dans une **fiche à part**, hors chantier, avant la mise en production. |
| D17 | Tri des tarifs à la caisse : **euros d'abord**, puis `order`. |

### 3.2 Montants, ticket, chaînage

| # | Décision |
|---|---|
| D18 | Paiement QR/NFC et tireuse répartis sur deux monnaies : corriger `amount`/`qty` selon la règle d'or. |
| D19 | HT d'une ligne = HT de `amount × qty` (LNE exigence 3). |
| D20 | Ticket client imprimé : **regrouper** les parts d'un même article ; détailler **tous** les moyens de paiement du ticket, **imprimé seulement si au moins deux moyens** ont servi (les deux imprimantes sont modifiées). |
| D21 | Chaînage HMAC étendu à la **tireuse**, au **paiement QR/NFC** et au **« vider carte »**. Le webhook legacy `Membership_fwh` est laissé tel quel. L'**archive fiscale** exporte aussi la **tireuse** (périmètre du Z). |
| D22 | **Verrou** par chaîne (`pg_advisory_xact_lock`) et **horodatage sous verrou** : `chainer_lignes` repose `datetime` au moment du chaînage. |
| D23 | QR/NFC : **garde anti-rejeu** (réservation `CREATED → UNPAID` avant le débit), livrée **en premier** dans la fiche F. Refus explicite de Fedow → la ligne redevient payable ; **erreur réseau ou délai dépassé → `FAILED`** (vérification manuelle, jamais de double débit). Puis appels réseau d'abord et une seule transaction. |
| D24 | Lignes sans empreinte au milieu d'une chaîne : `verify_integrity` les **signale** (lignes `VALID` seulement), sans faire échouer la vérification. |
| D25 | `send_sale_to_laboutik` (synchro vers l'ancien LaBoutik) : **gardé**, lancé en `transaction.on_commit`. |
| D26 | TVA des paiements QR/NFC : **taux par défaut du lieu**, inchangé. |
| D27 | Tireuse, solde insuffisant : **hors chantier**, comportement actuel gardé. |

### 3.3 Tests

| # | Décision |
|---|---|
| D28 | Un test qui lit un **rapport** (service de rapport, FEC, archive) tourne dans un **schéma de test dédié** (`FastTenantTestCase`, modèle : `tests/pytest/test_ventes_remontent_au_ticket_z.py` ~l.81-103, `tests/pytest/test_paiement_complementaire.py`). Le service lit toutes les ventes du lieu dans la période (`laboutik/reports.py` ~l.180, `point_de_vente` n'y filtre rien) : sur la base partagée, un total absolu dépendrait des autres tests. Un test qui ne lit que **ses propres lignes** (filtre `uuid_transaction`) peut rester sur la base partagée. |

## 4. Les fiches, dans l'ordre de livraison

| Fiche | Sujet | Effort estimé | Dépend de |
|---|---|---|---|
| [A](CHANTIER-04-A-paiement-reparti.md) | Paiement QR/NFC et tireuse réparti sur deux monnaies | 0,5 j | — |
| [B](CHANTIER-04-B-ht-fois-quantite.md) | HT d'une ligne = HT de `amount × qty` (LNE) | 0,5 j | — |
| [C](CHANTIER-04-C-ticket-imprime.md) | Ticket client : regroupement, détail des moyens, impression | 1 j | — |
| [D](CHANTIER-04-D-offerts.md) | `lignes_argent`, OFFRIR en mode gérant, recharges cadeau, section « Offerts », correction de paiement | 3 j | — |
| [E](CHANTIER-04-E-vente-en-points.md) | Vente en points/temps à la caisse (`NM`) + section « Non monétaire » | 5 à 6 j | D |
| [F](CHANTIER-04-F-chainage-hmac.md) | Anti-rejeu QR, chaînage HMAC tireuse, QR/NFC, vider carte, verrou, archive | 3 j | A, B |

**Total estimé : 13 à 14 jours** (relectures Opus et Fable du 2026-09-27). Risques de
dérapage : la session d'affichage de E (JS, Cotton, écrans, imprimantes, E2E) et la
restructuration QR/NFC de F.

A, B et C sont des corrections courtes et indépendantes. D pose la mécanique
« hors argent » que E réutilise. F scelle `amount`, `qty` et `total_ht`, qui doivent
être justes avant d'être scellés. E et F touchent les mêmes fichiers
(`controlvanne/billing.py`, blocs de chaînage de `laboutik/views.py`) : jamais en
parallèle.

## 5. Méthode de travail (valable pour chaque fiche)

1. **Le test d'abord, et on le voit échouer** sur le code actuel. On note la
   sortie d'échec dans le CHANGELOG de la fiche.
2. **Le correctif**, puis le test passe.
3. **Mutation** du code de production pour chaque assertion structurante :
   prévenir le mainteneur avant et après, restaurer dans un `finally` par Edit
   inverse (jamais git), vérifier l'empreinte `sha256sum` du fichier avant/après.
4. **Aucun** `pytest.skip`, aucun `if ... count() > 0`, aucune assertion toujours
   vraie. Un test compare des **montants** (totaux du rapport, `amount × qty`), pas
   seulement `amount`.
5. Tests lancés par `make` dans le conteneur, **jamais deux pytest en parallèle** :
   `docker exec lespass_django pgrep -af pytest` avant chaque lancement.
   Base de dev partagée : `django_db`, jamais `transaction=True`. Rapports : schéma
   dédié (D28). Après une migration, les schémas `test_*` de `FastTenantTestCase`
   sont à migrer ou supprimer (skill `tibillet-test`).
6. Pas de `ruff format` ni de `ruff check --fix` sur un fichier existant.
7. Commentaires FALC bilingues FR/EN au présent. Texte source des `_()` en
   français. Pas de `makemessages` / `compilemessages` : signaler les nouvelles
   chaînes au mainteneur.
8. Un fichier `CHANGELOG/2026-09-27-melanges-argent-<fiche>.md` par fiche, avec
   le tableau des mutations jouées.

## 6. Hors de ce chantier (constats qui restent à trancher)

| Code | Sujet |
|---|---|
| — | `crowds/views.py` vue `allocate` : la cagnotte additionne les recharges cashless au financement participatif (front débranché, vue encore en place). |
| A1 | Ticket X/Z et total perpétuel : recharges ET consommation cashless comptées deux fois. |
| A3 | FEC LaBoutik : consommation de crédit cadeau (LG) passée en « Avances clients » 4191. |
| A4 | Lignes TIREUSE dans les deux clôtures (LaBoutik et compta en ligne). |
| A5 | Compta en ligne : lignes « offert » avec montant (API : 74 lignes en dev) comptées comme ventes. |
| A6 | `STRIPE_FED` porte trois argents différents. |
| B1–B4 | Montants affichés au public (solde caisse multi-asset, crowds). |
| C1–C6 | Admin et rapports internes (dont C5 panier moyen avec remboursements, C6 détail par monnaie du ticket Z). |
| — | FEC en ligne : 706/756 crédités en TTC et TVA créditée en plus. |
| — | `calculer_hash_lignes` (`laboutik/reports.py` ~l.1042) hache `uuid, amount, status` mais **pas `qty`** : une altération de `qty` après clôture échappe à ce filet (le HMAC, lui, la couvre). L'ajouter invaliderait la vérification des clôtures existantes. |
| — | Webhook legacy `fedow_connect/views.py` `Membership_fwh` : crée une ligne LABOUTIK non chaînée (`TODO` dans le code). |
| — | Auto-clôture (`laboutik/tasks.py` ~l.441) : ne cherche la première vente que sur `LABOUTIK` ; un lieu qui n'a eu que des ventes tireuse ne déclenche pas la clôture. |
| D27 | Tireuse, solde insuffisant. |
| D16 | API v2 : rechargement de points en unité brute au lieu de centièmes (fiche à part, avant production). |

## 7. Vérifications communes

```bash
docker exec lespass_django pgrep -af pytest          # rien ne doit tourner
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
make test ARGS="tests/pytest/<fichier_de_la_fiche>.py"
make test                                             # suite complète en fin de fiche
```

État de départ annoncé (2026-09-27, non relancé pendant la rédaction) :
`make test` 1926 passed, `make e2e` 110 passed.
