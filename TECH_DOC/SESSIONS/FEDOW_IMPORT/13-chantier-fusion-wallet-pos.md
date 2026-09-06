# Chantier — Fusion du wallet éphémère au POS V2 (adhésion)

**Date d'ouverture :** 2026-09-05
**Statut :** à faire — spec écrite, aucun code produit
**Criticité :** argent réel. Le chemin touché déplace le solde d'une carte anonyme vers un usager.

---

## 1. Le problème en une phrase

Quand un adhérent est identifié au POS V2 avec une carte NFC anonyme, Lespass fusionne le
wallet éphémère **en local** et n'en dit **rien à Fedow**. Le FED que la carte portait reste
sur un wallet éphémère que plus personne ne référence : il devient invisible au point de
vente, sans aucun message.

Chemin fautif : `laboutik/views.py::_creer_adhesions_depuis_panier`, appel à
`WalletService.fusionner_wallet_ephemere` (~ligne 4835) sans déclaration ni fusion côté Fedow.

## 2. La règle établie, à respecter

`08-s6-creusage-profond.md` §2.2 :

> la création du wallet d'un USER passe **TOUJOURS** par le legacy d'abord ; les wallets
> locaux à uuid aléatoire sont réservés aux éphémères de cartes et au wallet du tenant.

§2.1 nomme « le point le plus dangereux de S6 » : deux wallets éphémères pour une carte, avec
une fusion non synchronisée. La garde est listée en ROADMAP **B1 #4** (« garde à poser dans
`fusionner_wallet_ephemere` ») et le verrou en **B2 #5** — ni l'une ni l'autre n'est faite.

**La procédure correcte est en trois étapes, dans cet ordre :**

1. `FedowAPI().wallet.get_or_create_wallet(user)` — déclare le user à Fedow **avec sa clé
   publique** ; le miroir local prend l'uuid renvoyé par Fedow.
2. `FedowAPI().NFCcard.linkwallet_card_number(user, card_number)` — **Fedow** fusionne son
   wallet éphémère dans celui du user et pose `Card.user`.
3. `WalletService.fusionner_wallet_ephemere(...)` — fusion locale des Tokens.

Le parcours QR web fait déjà exactement ça : `BaseBillet/views.py:671` → `:689` → `:717`.
C'est le modèle à suivre.

**Pourquoi l'ordre compte** : Fedow authentifie chaque requête signée via l'en-tête `Wallet`
→ `Wallet.objects.get(uuid)` → `wallet.public_pem` (`Fedow/fedow_core/permissions.py:69-103`).
Un wallet local à uuid aléatoire est inconnu de Fedow : plus aucun FED n'est lisible ni
débitable, et `get_or_create_wallet` lève ensuite « Wallet and member mismatch » à vie.

## 3. Ce qui a été tenté le 2026-09-05, et RETIRÉ

Une insertion de `get_or_create_wallet` juste avant la fusion locale. **Retirée le jour même**,
pour deux raisons — à ne pas refaire :

- **Elle ne faisait que l'étape 1 sur 3.** Le wallet éphémère Fedow n'était toujours pas
  fusionné : le bug visé restait entier.
- **Elle plaçait un appel réseau DANS le bloc atomic.** La docstring de
  `_creer_adhesions_depuis_panier` (`laboutik/views.py:4708`) dit « Appelée dans le bloc atomic
  des fonctions de paiement ». Conséquence : `get_or_create_user` crée le user **et sa clé RSA**
  dans la transaction, l'appel déclare cette clé à Fedow, puis un rollback (jauge pleine, solde
  insuffisant, worker tué) fait disparaître le user local **pendant que Fedow garde la clé**.
  Au retry : nouvelle clé → `Invalid pub pem` 400 (`Fedow/fedow_core/serializers.py:619-620`)
  → **cet email ne peut plus jamais être déclaré depuis Lespass** sans réparation manuelle.

Le pattern correct est dans le même fichier, `laboutik/views.py:5732-5737` et `:5919-5924` :

> Résolution du wallet client **AVANT** le bloc atomic … tiendrait un verrou DB pendant toute
> la latence réseau

## 4. Le travail, par ordre de priorité

1. **Sortir les appels réseau de l'atomic.** Résoudre user + wallet + liaison Fedow avant le
   `with db_transaction.atomic()`, et passer le résultat à `_creer_adhesions_depuis_panier`.
   Supprime le scénario du rollback ci-dessus et le verrou DB tenu pendant la latence réseau.
2. **Ajouter l'étape 2** (`linkwallet_card_number`), après la déclaration, avant la fusion
   locale, si `carte.user is None`. **Si Fedow refuse** (400 carte déjà liée, 409 anti-vol,
   timeout) : **ne pas fusionner en local non plus**. Ne pas déplacer les Tokens, ne pas poser
   `carte.user`. Le solde reste où il est, récupérable par le parcours `/qr/` normal.
3. **Remplacer le repli.** Sur échec Fedow avec `can_fedow()` vrai : pas de wallet local, pas
   de fusion — mais **l'adhésion est créée quand même** (une Membership n'a pas besoin de
   wallet), avec un message au caissier. Puis poser la garde ROADMAP B1 #4 dans
   `fusionner_wallet_ephemere` : exiger `user.wallet` non None, et laisser l'appelant créer un
   wallet local **uniquement** si `can_fedow()` est faux. Le moteur `fedow_core` doit rester
   hermétique au réseau (aucun import de `fedow_connect`) — c'est le point de débranchement du
   Fedow legacy.
4. **Verrouiller la carte** au POS (`select_for_update`, comme `CarteService.lier_a_user`
   `services.py:1433`) — ou faire passer le POS par `lier_a_user`, en décidant quoi faire de
   `UserADejaCarte` / `CarteDejaLiee` au comptoir.
5. **Réparer le stock existant.** Tout adhérent créé au POS avant ce correctif porte un wallet
   local divergent. La primitive existe (`aligner_wallet_user_sur_fedow`, `demo_data_v2.py:53`)
   mais elle est enfermée dans le seed : la sortir en management command avec `--dry-run`, plus
   un rapport des users dont `wallet.uuid` est inconnu de Fedow.

## 5. Les tests

**Modèle de référence — LaBoutik V1**, `APIcashless/tests.py:2226` et `:1910-1950`. Il teste
exactement l'invariant recherché, contre le **vrai Fedow** :

```python
carte = self.refill_card_wallet_4242_API(amount=6600)   # 66 € sur le wallet éphémère, chez Fedow
email, carte = self.link_email_with_wallet_on_lespass(card=carte)
self.check_carte_total_WV(carte, 66)                     # le solde a survécu
```

et dans `link_email_with_wallet_on_lespass` :

```python
self.assertTrue(before['is_wallet_ephemere'])
self.assertFalse(after['is_wallet_ephemere'])
self.assertNotEqual(before['wallet']['uuid'], after['wallet']['uuid'])   # ← l'assertion clé
```

L'`assertNotEqual` sur les uuid prouve que l'éphémère a été **absorbé** par le wallet du user,
et pas l'inverse. Couplée au solde retrouvé, elle démontre qu'aucun centime n'est orphelin.

⚠️ Ce test ne peut pas tourner en CI : `APIcashless/tests.py` contient au moins 7
`ipdb.set_trace()` (lignes 549, 632, 651, 824, 1469… et à la fin du méga-test). Il est conçu
pour être joué à la main.

**À écrire côté Lespass** — socle existant : `tests/pytest/test_wallet_carte_fedow_integration.py`
(marqueur `pytest.mark.integration`, skip explicite si Fedow absent, `override_settings(DEBUG=True)`
pour la vérification SSL du certificat auto-signé, helper `_tag()` à 8 caractères).

1. **Le test qui échoue d'abord** (TDD) : après identification d'un adhérent au POS avec une
   carte anonyme, la carte doit être liée au user **des deux côtés**. Il doit échouer sur le
   code actuel — c'est la preuve du bug.
2. Non-régression du parcours QR web (celui qui fonctionne déjà), sur le modèle LaBoutik.
3. Sur échec Fedow : aucun `Wallet` créé, aucun Token déplacé, `carte.user` inchangé.
4. **Valider chaque test par mutation.** Un test qui ne peut pas échouer ne vaut rien — piège
   éprouvé ce jour : un `mock.MagicMock()` accepte n'importe quel attribut et valide un appel
   sur la mauvaise classe. Utiliser `mock.create_autospec(WalletFedow)` /
   `create_autospec(NFCcardFedow)`.

## 6. Scénarios de référence (audit du 2026-09-05)

| # | Situation | Effet |
|---|---|---|
| S1 | Nominal, carte anonyme portant du FED | FED **inaccessible** au POS. Pas détruit — récupérable par `/qr/` web, mais personne ne le dit à l'usager |
| S2 | Suite de S1 : liaison ultérieure par un tiers | Le FED anonyme part chez l'autre usager ; Lespass et Fedow divergent sur le propriétaire |
| S3 | Fedow lent (>30 s) ou erreur après traitement | Wallet local committé → « mismatch » à vie |
| S4 | Rollback après déclaration Fedow | `Invalid pub pem` définitif — **créé par le correctif retiré**, à ne pas réintroduire |
| S6 | Adhérents créés au POS avant le correctif | Stock existant à réparer (point 4.5) |
| S7 | Deux caisses, même carte | Pas de double crédit (le débit verrouille), mais dernier écrit gagne sur `carte.user` |

Jamais de destruction ni de duplication de solde : les ledgers sont disjoints et
`TransactionService.creer` est atomique et verrouillé. Le risque est **l'argent rendu
inaccessible**, et l'usager mis hors réseau FED.

## 7. Points non tranchés

- Aucune exécution bout en bout contre un Fedow réel n'a été faite pour cet audit.
- Comment LaBoutik V1 crée ses users Fedow (avec ou sans pem) — détermine la fréquence réelle
  de S5 (user déjà connu de Fedow avec une clé différente).
- Quelles vues web rattrapent « Wallet and member mismatch » — rayon d'impact de S3.
