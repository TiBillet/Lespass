# CHANTIER 04 — Mesurer l'usage, pas seulement l'argent / Measure usage, not only money

**Statut :** Implémenté, non commité (2026-11-13), relu par Fable 5
**Migration :** Non
**Touche :** Lespass (`seo/observatoire.py`, `seo/views_observatoire.py`,
`seo/static/seo/observatoire.js`, `seo/templates/seo/observatoire.html`, tests) et
Fedow (`fedow_core/views.py`, à redéployer)

## Le constat

En prod, l'observatoire classe **7 lieux « actifs » sur 524**. Les lieux qui se servent
de TiBillet comme agenda, pour des réservations gratuites, pour leurs adhésions ou pour
la caisse V1 n'apparaissent pas.

Comptages sur la copie anonymisée de la prod du 2026-11-02 (539 lieux, novembre 2025 à
octobre 2026), avec les règles de ce chantier. Des nombres seulement.

| Mesure | Lieux |
|---|---|
| « Actif » avec la règle actuelle (≥ 10 000 € ou ≥ 1 000 billets payants) | 10 |
| Au moins 1 événement publié (hors sous-événements) | 126 |
| Billets gratuits seulement, aucun billet payant | 53 |
| Billets payants | 24 |
| Adhésions | 40 |
| Ventes cashless NFC dans Fedow legacy (`SAL`) | 27 |
| Ventes par QR code dans Fedow legacy (`QRS`, page `/my_account`) | 38 |
| Location de salle ou de matériel (`booking`) | 3 |

Billets valides des événements de la période : 13 820, dont **7 613 gratuits (55 %)**.

Lieux selon leurs mois d'usage sur 12 (§ 3, ventes cashless comprises), pour les deux
seuils d’événements comparés (décision 5 : ≥ 1) :

| Mois d'usage sur 12 | ≥ 1 événement par mois | ≥ 2 événements par mois |
|---|---|---|
| au moins 1 | 159 | 101 |
| au moins 3 (actif) | 56 | 41 |
| au moins 6 | 35 | 26 |
| au moins 9 (très actif) | 20 | 17 |

## Les trois causes

1. **La plupart des billets gratuits ne sont pas comptés.** Le produit « réservation
   gratuite » ne crée pas de ligne de vente, donc rien dans les clôtures
   (`BaseBillet/validators.py:354-390`). Un tarif billet à 0 € en crée une, à 0 €
   (`validators.py:311-332`). Le compteur `inscriptions` ne voit donc qu'une partie des
   billets gratuits.
2. **« Actif » est un seuil de gros lieu** : 10 000 € ou 1 000 billets par an.
3. **La caisse V1 n'est pas vue lieu par lieu.** Les ventes NFC et QR code passent par
   Fedow legacy. L'observatoire ne lui demande que des totaux du réseau. La colonne
   « Cartes » ne lit que Fedow V2, et un paiement QR code n'a jamais de carte (0 sur
   2 321 en prod).

Ce qui est juste : l'historique des ventes. La reprise a créé les clôtures mensuelles
depuis avril 2022 pour les 110 lieux qui vendent.

## Décisions du mainteneur (2026-11-13)

1. La **nature** d'un lieu devient ses **usages**. Un lieu peut en avoir plusieurs.
2. **« Actif » se mesure par la régularité** : un nombre de mois d'usage sur 12. L'argent
   ne sert plus qu'à la **taille**.
3. **Fedow legacy renvoie ses ventes par lieu et par mois** (NFC et QR code) dans ce
   chantier.
4. **La catégorie déclarée disparaît de la page** : colonne, regroupement, découpe et
   pastille « écart ».
5. **Un événement publié suffit** à faire un mois d'usage : un conseil d'administration
   ou une assemblée de bénévoles montre que le lieu est vivant.
6. **« Bidouillage » est retiré.**
7. **Le rythme est gardé, calculé sur le volume d'activité** et plus sur le CA (§ 3).
8. **Les seuils des usages sont fixes** dans le code, pas dans le panneau des seuils.

## 1. Les compteurs mensuels (Python, `seo/observatoire.py`)

`CLES_DES_COMPTEURS` devient :

| Clé | Source | Changement |
|---|---|---|
| `evenements` | `Event` publiés, sans parent (`parent__isnull=True`), par mois de l'événement | **filtres ajoutés** |
| `billets_gratuits` | `Ticket` valides (`K`, `S`) gratuits (définition plus bas), par mois de l'événement | **nouveau** |
| `billets_payants` | `Ticket` valides non gratuits, par mois de l'événement | **nouveau** |
| `billets_scannes` | inchangé | |
| `adhesions` | voir « Les adhésions » plus bas | **source changée** |
| `ca_total`, `ca_billetterie`, `ca_adhesions`, `ca_caisse`, `recharges_ligne`, `recharges_place` | clôtures, inchangé | |
| `locations` | `booking.Booking` aux statuts `PA`, `AU`, `VA`, `FU`, par mois de `start_datetime` | **nouveau** |
| `transactions_cashless` | transactions de vente Fedow V2 (`SALE`) du lieu + Fedow legacy (`SAL` + `QRS`) de sa Place | **nouveau** |
| `portemonnaies_actifs` | porte-monnaie distincts qui ont payé : le plus grand des deux nombres, V2 ou legacy | **remplace `cartes_actives`** |
| `usagers` | inchangé | |

Retirés : `inscriptions` (remplacé par les deux compteurs de billets),
`cartes_actives`, `connexions_admin` (jamais enregistré, toujours 0).

### Le mois d'un billet

C'est **le mois de l'événement**, comme `billets_scannes`. `Reservation.created_at`
est inutilisable : la migration `BaseBillet 0235` l'a rempli avec sa propre date. Sur la
copie de prod, 13 032 réservations sur 13 401 sont datées du 17 au 20 octobre 2026.

### Billet gratuit

Un billet est gratuit si **une** de ces conditions est vraie :
- `payment_method == PaymentMethod.FREE` (billet offert depuis l'admin, qui garde le
  tarif payant dans `pricesold`, `Administration/admin_tenant.py:5261-5267`) ;
- pas de `pricesold` (billet de créneau bénévole, `validators.py:343-348`) ;
- `pricesold.prix == 0` (tarif gratuit, prix libre à 0, code promo à 100 %).

Les deux compteurs viennent d'une seule requête (`Count` avec `filter=Q(...)`).

Limite connue : une réservation gratuite dont l'e-mail n'est pas vérifié a des billets
`NOT_ACTIV`. Ils ne sont pas comptés.

### Les adhésions

`Membership.date_added` ne convient pas seul. La fiche est créée avant le paiement
(`validators.py:1227-1231`), et un renouvellement en caisse V2 ou par abonnement Stripe
met à jour la même fiche (`laboutik/views.py:7998-8014`, `BaseBillet/triggers.py:78-95`).

**Proposé :** compter les `LigneArticle` liées à une adhésion (`membership` non nul),
aux statuts payés, par mois de `datetime`. Une adhésion à 0 € ouvre aussi une ligne
(`validators.py:1290-1298`). À vérifier pendant le code, sur la copie de prod : les
adhésions créées depuis l'admin ou par import ont-elles une ligne ? Si non, ajouter les
`Membership` sans ligne, par `date_added`, hors statuts `WP`, `AW`, `C`, `AC`, `PP`.

### Valeurs fixes du lieu

La ligne d'un lieu devient `[schema, nom, cree, pdv, admins, federe, compteurs]` :
- `categorie` est retirée ;
- `federe` (nouveau) : vrai si le lieu **affiche l'agenda d'un autre lieu** ou si **un
  autre lieu affiche le sien**.

`FederatedPlace` vit dans le schéma du lieu qui affiche ; son champ `tenant` désigne le
lieu affiché (`BaseBillet/models.py:5674-5675`). Pendant la boucle des lieux, on lit
les `tenant_id` des `FederatedPlace` du lieu courant. On ajoute le lieu courant et les
lieux cités à un ensemble. Après la boucle, `federe` = le lieu est dans l'ensemble.
Aucune requête de plus qu'une par lieu.

### Lien avec Fedow legacy

- `statistiques_de_fedow_legacy()` est appelée **une seule fois, avant la boucle des
  lieux**. Son résultat sert aux ventes par lieu et au bloc « réseau depuis le début ».
- Dans `tenant_context(lieu)`, on lit
  `FedowConfig.objects.values_list("fedow_place_uuid", flat=True).first()`.
  Jamais `get_solo()` : il crée une ligne dans les lieux sans configuration, et le
  calcul ne doit rien écrire dans les lieux.
- Clé de jointure : `uuid.hex` des deux côtés (sans tirets).
- Lieu sans Place, ou absent de la réponse : 0 vente legacy.
- Si Fedow n'a pas répondu : le bandeau existant le dit déjà. On y ajoute : « Les ventes
  de caisse V1 manquent : des lieux qui n'utilisent que la caisse V1 apparaissent en
  sommeil. »

### Coût

On passe de 8 à environ 12 requêtes par lieu (billets, adhésions, locations, Place
Fedow, fédération), plus 1 appel Fedow pour tout le réseau. Le calcul de prod prend
27 s aujourd'hui pour 524 lieux.

## 2. Fedow : les ventes par lieu (`fedow_core/views.py`, `StatistiquesReseauAPI`)

Un troisième agrégat dans la réponse de `/statistiques_reseau/` :

```json
"ventes_par_lieu": {
  "<uuid.hex de la Place>": {
    "2026-10": {"transactions": 812, "portemonnaies": 240}
  }
}
```

- Transactions `SAL` et `QRS` des **25 derniers mois**, reçues par le wallet d'une
  Place (`receiver__place`).
- Une requête groupée par Place et par mois : `Count("uuid")` et
  `Count("sender", distinct=True)`.
- Clés de dict en `str` (`uuid.hex`, `"AAAA-MM"`) : un `UUID` en clé fait planter le JSON.
- Mois en UTC (`Fedow/fedowallet_django/settings.py:196-200`) : Fedow ne connaît pas le
  fuseau des lieux. L'écart est de quelques heures en fin de mois, acceptable.
- **Mesuré** sur la copie anonymisée de Fedow : 235 379 transactions, 500 groupes en
  0,36 s (pas d'index sur `action`, lecture de toute la table).
- **Nouvelle clé de cache** (`statistiques_reseau_pour_observatoire_v2`) : sinon un
  déploiement moins d'une heure avant le calcul rend l'ancienne réponse.

Ce que compte `transactions` : des transactions, pas des paniers. Un panier de caisse V2
payé en assets locaux puis en complément FED donne une transaction V2 et une legacy
(`laboutik/views.py:1927`). D'où le nom `transactions_cashless`.

## 3. Le classement (JS, `seo/static/seo/observatoire.js`)

### Le mois d'usage

Un mois compte comme « mois d'usage » si au moins une condition est vraie :

| Condition | Seuil fixe |
|---|---|
| événements publiés | ≥ 1 |
| billets (gratuits + payants) | ≥ 10 |
| chiffre d'affaires | ≥ 200 € |
| adhésions | ≥ 5 |
| recharges | ≥ 200 € |
| transactions cashless | ≥ 20 |
| locations | ≥ 1 |

Ces seuils restent des constantes, comme aujourd'hui (`compteurs.reel`).

### L'activité

| Activité | Règle (sur les 12 derniers mois) | Seuil réglable |
|---|---|---|
| très actif | mois d'usage ≥ `tresActifMois` **et** ≥ `actifMois` | `tresActifMois` (inchangé, 9) |
| actif | mois d'usage ≥ `actifMois` | `actifMois` (**nouveau**, 3 ; remplace `actifCA` et `actifInscr`) |
| peu utilisé | mois d'usage ≥ 1 | |
| sommeil | aucun mois d'usage, ou règle d'abandon | |

La règle d'abandon reste la même, avec les mois d'usage à la place des mois « réels ».

« Bidouillage » disparaît.

### Les usages (remplace la nature)

Un lieu reçoit **chaque usage** qu'il a sur les 12 derniers mois :

| Usage | Règle (12 mois) |
|---|---|
| agenda | événements publiés ≥ 3 |
| billetterie gratuite | billets gratuits ≥ 10 |
| billetterie payante | billets payants ≥ 10 |
| adhésions | adhésions ≥ 5 |
| caisse | transactions cashless ≥ 20, ou CA de caisse ≥ 200 € |
| location | locations ≥ 1 |
| réseau | `federe` |

Un lieu qui n'a aucun de ces usages reçoit « aucun usage », pour rester visible dans les
filtres et les regroupements. « Réseau » est une valeur fixe : un lieu en sommeil peut
l'avoir.

Les natures « lieu », « mixte », « adhésions » et le seuil `adhesionsPart`
disparaissent. Les seuils des usages sont des constantes (décision 8).

### Le rythme (remplace la partie « forme du CA » de l'ancienne nature)

Calculé sur le **volume d'activité** du mois, et plus sur le CA : un festival en caisse
V1 ou une fête gratuite a peu de CA dans Lespass, mais beaucoup d'activité.

Volume du mois = billets (gratuits + payants) + adhésions + transactions cashless.

| Rythme | Règle (12 derniers mois) |
|---|---|
| saisonnier | les 2 meilleurs mois consécutifs font ≥ `festivalConcentration` % du volume, et mois d'usage ≤ 5, et (récurrent ou nouveau) |
| ponctuel | même concentration, ni récurrent ni nouveau |
| temps forts | le meilleur mois vaut ≥ `mixtePic` fois le mois médian (des mois d'usage) |
| régulier | sinon |

- Récurrent (marque « ↻ ») : inchangé, un mois d'usage revient à la même saison un an
  plus tard.
- Nouveau : aucun mois d'usage avant les 12 derniers.
- Un lieu en sommeil, ou sans volume, n'a pas de rythme.
- Le rythme a une seule valeur par lieu : il sert aussi de couleur et de regroupement.

Sur la copie de prod : 73 lieux ont au moins 30 actes sur 12 mois ; 20 sont
saisonniers, dont 18 avec moins de 10 000 € de CA Lespass.

### La taille

Inchangée : CA des 12 derniers mois (`petitMax`, `moyenMax`).

### La tendance

- Si le lieu avait du CA avant les 12 derniers mois : tendance sur le **CA**, comme
  aujourd'hui.
- Sinon : tendance sur les **mois d'usage** (nouveau si aucun mois d'usage avant ; en
  baisse, en hausse, stable avec les mêmes seuils).

Raison : sur les mois d'usage seuls, un lieu à 12 mois sur 12 qui double son CA reste
« stable », et « en hausse » devient impossible dès 8 mois avant.

## 4. La page (JS et `seo/templates/seo/observatoire.html`)

Une règle pour toutes les vues : **« usage » sert là où un lieu peut compter plusieurs
fois** (colonne, filtres, barres). **Partout où il faut une seule valeur par lieu, on
prend le rythme** (là où l'ancienne nature servait : couleurs, anneau, courbes par
groupe, matrice taille × rythme, vue « moyenne par rythme »).

- **Liste** : la colonne « Nature » devient « Usages » (une pastille par usage). La
  colonne « Catégorie » et la pastille « écart » disparaissent. Une colonne « Rythme »
  s'ajoute (avec « ↻ »).
  « Cartes » devient « Porte-monnaie ».
- **Filtres** : un filtre par usage (« a l'usage agenda », etc.).
- **Barres par usage** : un lieu compte dans chacun de ses usages. La somme des barres
  peut dépasser le nombre de lieux, et la page le dit sous le graphique.
- **Onglet « Sur mesure »** : l'usage y est un filtre seulement. Ses regroupements,
  couleurs et anneaux demandent une seule valeur par lieu.
- **Listes de choix** (`VUES`, `DISTINCTIONS`, `COULEURS_DU_NUAGE`, `DECOUPES`, replis
  sur `"nature"`, options écrites dans le gabarit) : « nature » et « catégorie »
  retirées ou remplacées comme ci-dessus.
- **Tuiles de synthèse** : « Cartes NFC actives » devient « Porte-monnaie actifs ».
- **Exemples sur mesure** (`EXEMPLES`) : refaits avec les nouvelles clés.
- **Configuration gardée dans le navigateur** : la clé `observatoire-sur-mesure-v3`
  passe en `v4`. Une ancienne configuration (`y: "cartes_actives"`, `g: "categorie"`)
  ferait planter la page.
- **Seuils** : `actifMois` remplace `actifCA` et `actifInscr`. `adhesionsPart`
  disparaît ; `festivalConcentration` et `mixtePic` restent, pour le rythme.
- **Bulles d'aide et libellés** : en Python (`views_observatoire.py`), msgid en
  français. Le mainteneur lance makemessages.

## 5. Ordre de déploiement

1. Fedow (nouvel agrégat, nouvelle clé de cache), relance de gunicorn.
2. Lespass, puis **tout de suite** `manage.py refresh_observatoire`. Entre les deux, le
   cache contient l'ancien format et la nouvelle page ne sait pas le lire.

## 6. Tests

- `tests/pytest/test_observatoire.py` :
  - billets gratuits (tarif à 0, billet offert, sans tarif vendu) et payants, au mois
    de l'événement ;
  - adhésion à 0 € comptée ; adhésion en attente de paiement ignorée ;
  - événement non publié et sous-événement ignorés ;
  - location payée comptée, location annulée ignorée ;
  - ventes legacy rattachées au bon lieu par sa Place ; Place absente → 0 ;
  - réponse Fedow sans `ventes_par_lieu`, ou Fedow muet → 0, pas d'erreur ;
  - `federe` vrai des deux côtés d'une `FederatedPlace` ;
  - aucune ligne `FedowConfig` créée par le calcul ;
  - ligne sans catégorie, avec `federe`.
  - À adapter : `:237` (`inscriptions == 4`) et `:535-537` (positions dans la ligne).
- `Fedow/fedow_core/tests/test_statistiques_reseau.py` : `ventes_par_lieu` (SAL et QRS
  comptés, REFILL ignoré, porte-monnaie distincts, clés en `str`).
- `tests/e2e/test_admin_observatoire.py` : à adapter (`CLES` `:37-51`, catégorie en
  position 2 `:90, 99`, seuil `actifCA` `:168, 194`, bulle « 10 k » `:190-198`). Le test
  « seuil reclasse » passe sur `actifMois`. Un test : un lieu avec seulement des
  billets gratuits sur 3 mois est « actif » et porte l'usage « billetterie gratuite ».
- Vérification par mutation sur chaque nouveau compteur et sur la règle d'activité.

## 7. Documentation

- En-tête de `seo/observatoire.py` (`:39-42`, nombre de requêtes) et `SPEC.md` du
  chantier 01 (compteurs, classement).
- `CHANGELOG/` : une entrée pour ce chantier.

## Hors périmètre

- Les connexions admin : `last_login` est commun à tous les lieux d'une personne, il
  ne dit rien d'un lieu précis. À reprendre avec l'historique (chantier 02).
- Les pages du site : créées à l'installation de chaque lieu, elles ne mesurent rien.
- Le bénévolat, le financement participatif : volumes faibles en prod (1 et 12 lieux).
- L'import LaBoutik V1 (ventes de caisse détaillées) : reste à faire.
