# Recherche 08 — S6 (hybride additif) : creusage profond

Date : 2026-06-10
Méthode : 5 investigations parallèles (cartes/wallets, contrat de débit legacy,
flux en ligne, insertion POS, avocat du diable).
Clarification de nommage : la « variante additive » du doc 07 n'est PAS le S5
pur (tout legacy) — c'est un hybride S5+S3 restreint aux nouveaux tenants,
nommé **S6** : monnaies locales en `fedow_core` local, tokens legacy (FED +
fédérés existants) acceptés via l'API du Fedow standalone.

---

## 1. Les bonnes nouvelles (vérifiées dans le code)

### 1.1 Le débit legacy sans handshake est CONFIRMÉ — et meilleur qu'espéré
`POST /transaction/qrcodescanpay` (Fedow/serializers.py:992-1113) :
- permission `HasPlaceKeyAndWalletSignature` = **clé API du lieu (FedowConfig
  l'a déjà) + signature RSA du user (Lespass détient les clés)**. Aucun
  handshake cashless.
- **La cascade legacy est faite CÔTÉ SERVEUR** : on envoie un montant et
  `asset_type="EURO"`, Fedow débite TLF acceptés puis FED, et renvoie la liste
  des transactions créées (une par asset). Le POS n'a PAS à connaître les
  assets legacy — il demande « X centimes » et reçoit le détail.
- Fail-fast : refus total si solde insuffisant (pas de débit partiel) — le POS
  connaît le dépensable avant (cf. 1.2), donc il demande toujours ≤ solde.
- **Déjà utilisé en prod** par Lespass V1 (scan QR pay, BaseBillet/views.py:1475-1540).

### 1.2 La consultation du solde legacy est réutilisable telle quelle
`retrieve_by_signature` (cache 10 s) + helper
`get_total_fiducial_and_all_federated_token()` (fedow_api.py:463) : calcule
déjà « ce qui est dépensable ici » (FED + TLF du lieu + TLF fédérés). Prêt
pour l'affichage POS.

### 1.3 L'insertion dans la cascade POS est propre et localisée
`_payer_par_nfc()` a déjà la mécanique du « reste à payer »
(`total_complementaire` + écran complément espèces/CB/2e carte,
views.py:5704-5763). Le segment legacy s'insère comme **un cran de cascade
après les assets locaux**, débité en HTTP AVANT le bloc atomic local :
échec HTTP → le montant repart en complément (modèle TPE), pas de
compensation distribuée. Estimation de l'agent : ~400-500 lignes, complexité
moyenne, **zéro migration** (le legacy se mappe sur `PaymentMethod.LOCAL_EURO`
comme le FED local → clôtures, ventilation et FEC passent sans modification).

### 1.4 La comptabilité absorbe le legacy sans changement
`MAPPING_ASSET_CATEGORY_PAYMENT_METHOD` assimile déjà FED → LOCAL_EURO ;
reports.py détaille par `asset_name`. Aucun nouveau mapping comptable requis.

## 2. Les vrais problèmes découverts (et leurs parades)

### 2.1 ❗ Les cartes legacy sont INCONNUES de CarteCashless — le pont à construire
Vérifié : CarteCashless (V1) est peuplée par imports locaux, **pas de sync
depuis Fedow**. Une carte du réseau scannée au POS V2 → `DoesNotExist` → 404
« Carte inconnue ». Il faut un **pont au scan** : sur tag_id inconnu, appeler
`card_tag_id_retrieve` (existant), créer la ligne CarteCashless miroir
(uuid = qrcode_uuid Fedow, identifiants compatibles 8-hex des deux côtés).

**Le piège en dessous** : pour une carte legacy ANONYME, créer un
wallet_ephemere local en miroir = **deux wallets éphémères pour une carte**
(soldes divergents, fusion non synchronisée). C'est le point le plus dangereux
de S6.

**Parade structurante (périmètre de phase 1)** :
> Le segment legacy n'est accessible qu'aux cartes legacy **liées à un user**
> (wallet user connu → signature possible, débit qrcodescanpay).
> Carte legacy anonyme → message « liez votre carte à votre compte »
> (le flux /qr/ existant de Lespass V1 fait exactement ça, en prod) →
> puis complément espèces/CB.
Aucun wallet éphémère miroir n'est créé, jamais. La ligne CarteCashless miroir
ne sert que de cache d'identité.

### 2.2 ❗ L'ordre de création du wallet user — parade obligatoire
`fusionner_wallet_ephemere` (et le POS) créent un Wallet LOCAL avec un uuid
aléatoire si le user n'en a pas. Si le legacy crée ensuite le « vrai » wallet
(uuid différent), `get_or_create_wallet` lève « Wallet and member mismatch »
(fedow_api.py:589). **Règle S6** : la création du wallet d'un USER passe
TOUJOURS par le legacy d'abord (il est vivant pour tout le monde) ; les
wallets locaux à uuid aléatoire sont réservés aux éphémères de cartes et au
wallet du tenant. Garde à poser dans `fusionner_wallet_ephemere` et
`_obtenir_ou_creer_wallet`.

### 2.3 ❗ Recharge locale : garde anti-asset-étranger
`creer_recharge` ne vérifie pas `asset.tenant_origin == tenant` — une
mauvaise config de produit pourrait créditer un asset d'un autre tenant.
Parade : 5 lignes dans le service + test.

### 2.4 ❗ Carte perdue : double déclaration
`declarer_perdue` (local) et `lost_my_card_by_signature` (legacy) ne se
connaissent pas → carte bloquée d'un côté, active de l'autre. Parade : pour
une carte ayant une existence legacy (miroir), déclarer côté legacy D'ABORD,
puis localement (~20 lignes).

### 2.5 ❗ Le Postgres de Lespass devient un registre monétaire
Dès que `fedow_core` local porte de la valeur, un restore de backup Lespass
non coordonné peut effacer des recharges/débits locaux. Exigence d'exploitation
(valable pour TOUT scénario à fedow_core local, S6 comme V2 mono-repo) :
procédure de backup/restore « ledger » (dump dédié du schéma public +
rejouabilité des transactions + alerte admin). À écrire avant le 1er tenant réel.

### 2.6 Limites actées (pas des bugs, des choix à assumer)
- **Pas de remboursement du débit legacy par signature user** : annuler une
  vente avec segment legacy n'est pas possible automatiquement (le refund
  par signature n'existe que pour le FED global). Limitation documentée au
  POS (comme une vente TPE annulée → geste commercial), OU petit endpoint
  refund à ajouter côté Fedow plus tard (on le garde, on peut).
- **Pas de recharge du legacy au POS V2** : la recharge POS ne crédite que les
  assets locaux. Recharge FED = flux en ligne existant.
- **Recharge en ligne des monnaies locales** : à différer (les monnaies de
  lieu se rechargent au POS, c'est le mode normal) — le flux V2
  « CASHLESS_REFILL » pourra être adapté plus tard.
- **Fédération entre nouveaux tenants** : non câblée (audit M6) — les
  nouveaux lieux fédèrent entre eux via… le legacy (leurs places y existent),
  ou attendront le câblage `fedow_core.Federation`. À arbitrer plus tard.

### 2.7 Attaques écartées après examen
- « PK violation .re/.coop » : confondait les deux instances (deux DB
  séparées) ; le partage de wallet cross-instance existe déjà en V1, inchangé.
- « Email changé » : cas marginal, déjà vrai en V1, pas spécifique à S6.

## 3. Estimation révisée

| Lot | Contenu | Sessions |
|---|---|---|
| C-A | Copier-coller du socle (inchangé, doc 07) | 1 grosse |
| C-B | Durcissement : audit (B1, B2, M1-M4) **+ parades S6** (2.2 garde wallet, 2.3 garde recharge, anti-FED-local) | 2 |
| C-C | Interop legacy : solde au scan (cache 10 s, timeout court), pont carte miroir (liées seulement), segment cascade + complément, double déclaration carte perdue | 3-4 |
| C-D | Flux en ligne (affichage fusionné tokens locaux + legacy dans my_account), onboarding, procédure backup ledger, tests, pilote | 2-3 |

**Total révisé : 8-10 sessions** (contre 6-8 estimés avant creusage, et 15-22
pour le recâblage S5 intégral). Le surcoût vient du pont cartes et des parades.

## 4. Verdict

S6 est **viable et reste le meilleur compromis**, à trois conditions actées :
1. **Périmètre de phase 1** : segment legacy réservé aux cartes liées à un
   user ; anonymes → liaison de carte (flux existant) puis complément.
2. **Les 4 parades** (2.2 à 2.5) sont dans le C-B, non négociables avant un
   tenant réel.
3. Les **limites 2.6** sont assumées et documentées (annulation legacy,
   recharge legacy POS, recharge en ligne locale différée).

L'alternative si on refuse tout risque hybride : étanchéité stricte par
population (S2) — plus simple, mais réseau scindé. Le choix reste celui du
doc 03 : la valeur d'un réseau unique vaut-elle le pont cartes ?
