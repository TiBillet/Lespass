# BÉNÉVOLAT — Planning des besoins en bénévoles (façon Framadate)

> **Status :** spec du 2026-09-23, **non commencée**. Exploration : aucun code écrit.
> Relue le même jour par un agent Fable (exactitude face au code, inventaire, sur-ingénierie).
> Ses corrections sont intégrées. Les décisions D6 à D19 et P1 à P10 ont eu une **seconde relecture
> Fable** le 2026-09-24 (exactitude, pièges techniques, contradictions) ; ses corrections sont intégrées.
> **Pré-requis :** aucun.
> **Maquette interactive :** [`BENEVOLAT-maquette.html`](BENEVOLAT-maquette.html), à ouvrir
> dans un navigateur (page publique, vue mobile, bloc d'accueil, « Mes créneaux », schéma de
> l'admin, modèle de données). **La spec fait foi** : la maquette ne montre ni le rappel et le
> désistement (§5.9), ni la colonne « Fermé » de l'admin (P8), ni le nom de famille (D18),
> ni l'inscription par l'équipe (§5.10), ni l'API (§6 bis). Son champ « Publié : visible sur
> /booking/ » est périmé (D14).
> **Décisions :** tranchées par le mainteneur le 2026-09-23 (§2.1), complétées le 2026-10-12
> (D18 revue, D21 à D24). Questions ouvertes : aucune (§10).
> **Hors périmètre :** la suppression d'`Event.ACTION` et d'`Event.parent`. Chantier à part, plus tard.

## Lexique

| Terme | Sens |
|---|---|
| Planning | un tableau de besoins, publié sur le site. Ex : « Bar associatif : octobre » |
| Tâche | ce qu'on demande de faire : « Tenir le bar », « Faire le ménage », « Checker la com' ». Catalogue du lieu, réutilisé d'un planning à l'autre |
| Besoin | une case du tableau : une tâche, un jour, une plage horaire facultative, un nombre de personnes souhaité |
| Inscription | une personne s'est positionnée sur un besoin |
| Place | une unité de `nombre_souhaite`. Un besoin « 3 personnes » a 3 places |
| Renfort | une inscription au-delà du nombre souhaité. Toujours permise (D7) |
| Inscription par l'équipe | un·e admin du lieu inscrit une autre personne sur un besoin, à sa place (D23, §5.10) |
| Fermeture | une `ClosedPeriod` d'un `Calendar` de `booking` : les mêmes jours fermés que les ressources (D9) |
| Période modèle | les besoins déjà saisis entre deux dates, que l'action « Répéter » recopie (§5.7) |
| Lettre d'information | la newsletter du lieu, envoyée par son instance Ghost (§5.8) |
| Action (legacy) | un `Event` de catégorie `ACTION` (`"ACT"`), enfant d'un autre événement. Le bénévolat actuel, laissé en place par ce chantier |
| Lieu | un tenant (un schéma PostgreSQL) |

## 1. Pourquoi ce chantier

Un lieu a besoin de monde : tenir le bar, faire le ménage, relayer la com'. Aujourd'hui il
passe par un Framadate, un tableur partagé ou des SMS. Le besoin :

1. L'équipe déclare **des jours** où il faut 1, 2 ou 3 personnes **par tâche**.
2. Sur le site, chacun voit le tableau et **se positionne en un clic** sur une case.
3. Chacun retrouve ses créneaux dans « Mon compte » et peut se retirer, jusqu'à un délai.

Ce qui existe ne convient pas :

| Brique | Pourquoi elle ne suffit pas |
|---|---|
| `booking` (ressources, coworking) | Pensé pour des créneaux **récurrents** (`WeeklyOpening`, « ouvert chaque semaine sauf fermetures »). Le besoin est inverse : **des dates précises**. `Resource.product` est obligatoire (`booking/models.py`), et `validate_new_booking` crée toujours un `LigneArticle`, même à 0 € (`booking/booking_engine.py`) : chaque inscription bénévole finirait dans les ventes et l'export comptable. |
| `Event.ACTION` (bénévolat actuel) | Une action = un événement enfant avec `jauge_max`. On ne peut prendre **qu'une action par événement parent** (`BaseBillet/views.py:3277`). Chaque inscription crée une `Reservation` + un `Ticket` (`method_A`, `validators.py:320`). Aucune vue « jours × tâches ». Personne ne s'en sert en prod. |

**Le but :** un petit module dans `booking`, qui reprend les **idées** du moteur de
ressources (nombre de places, délai d'annulation, admin, onglet « Mon compte ») et ses
**jours de fermeture** tels quels, sans en reprendre le couplage à la vente.

## 2. Décisions

### 2.1 Tranchées par le mainteneur (2026-09-23)

| # | Sujet | Décision |
|---|---|---|
| D1 | Fondation | **Modèles dédiés dans l'app `booking`**. Pas de `Product`, `Price`, `LigneArticle`, ni Stripe, ni panier. |
| D2 | Visibilité des noms | **Prénoms publics** : tout le monde, même anonyme, voit les prénoms positionnés sur une case. |
| D3 | Qui peut s'inscrire | **Réglable par planning** : « tout compte connecté » ou « adhérent·es d'une ou plusieurs adhésions ». |
| D4 | Granularité | **Jour + plage horaire facultative**. Plusieurs besoins possibles pour la même tâche le même jour (bar 18h–21h et 21h–minuit). |
| D5 | Legacy | **`Event.ACTION` reste en place.** Sa suppression (avec `Event.parent`) est un chantier à part, plus tard. |
| D6 | Saisie répétitive | **Action admin « Répéter des besoins »** : répéter une période modèle tous les N jours ou toutes les N semaines, X fois (§5.7). |
| D7 | Au-delà du nombre souhaité | **On peut toujours s'inscrire**, même quand le besoin est couvert : « on peut être 3 sur une tâche prévue pour 2, c'est plus rigolo ». `nombre_souhaite` est un objectif, **pas un plafond**. |
| D8 | Couleur des jours | **En-têtes de jours colorés** selon le remplissage : dégradé rouge (rien de couvert) → vert (tout couvert) (§5.2). Exception assumée à la règle de la DA V2 « pas de couleur sur le contenu d'un lieu » (`pages/static/V2/css/V2.css`, en-tête) : ici la couleur porte un **état**, pas une identité. |
| D9 | Jours de fermeture | **Les mêmes que `booking`** : le planning pointe un `Calendar` existant. « Répéter » saute les jours fermés (§5.7). |
| D10 | Se tenir informé·e | **Un champ email + un bouton « Je m'inscris à la lettre d'information »** sur la page du planning, pour recevoir les prochains besoins (§5.8). |
| D11 | Lettre sur `/booking/` | **Non en v1** : le bloc lettre n'est que sur la page du planning (ex-Q12). |
| D12 | Étiquettes sur les personnes | **Spec à part** (`TODO/USERS-etiquettes.md`, écrite le 2026-09-24) : des étiquettes par lieu sur les utilisateurs, bénévoles et adhérent·es, pour écrire à des groupes précis via Ghost ou Brevo (« seulement les bénévoles bar », « seulement les adhérent·es »). Contrainte connue : `TibilletUser` est en schéma `public`, le catalogue d'étiquettes dans le schéma du lieu, donc une table de liaison côté lieu, pas un champ sur l'utilisateur. Catalogue à part, distinct des `Tag` (D4 de cette spec-là). Le bénévolat s'en servira si elle existe (champ facultatif `TacheBenevole.etiquette`, FK `Etiquette` : l'inscription pose l'étiquette de la tâche, voir `TODO/USERS-etiquettes.md` §5) ; sinon il envoie seulement l'étiquette Ghost « Bénévolat » (§5.8). (ex-Q11) |
| D13 | Lettre : consentement | **Comme le reste du site** : inscription directe par `send_to_ghost_email` pour tout le monde, connecté·e ou non, sans double confirmation (même comportement que la case « newsletter » des formulaires). Limite connue et acceptée : n'importe qui peut abonner l'email d'une autre personne. (ex-P10) |
| D14 | Où on découvre les besoins | **Une page dédiée par planning** (son nom, son adresse `/booking/benevolat/<slug>/`) **+ un bloc sur l'accueil du lieu**, dans la même veine que « les prochains évènements » : une nouvelle **source** du bloc CMS « Liste automatique » (§5.1). Pas de section sur `/booking/` en V1. (ex-Q1) |
| D15 | Deux créneaux qui se chevauchent | **Aucune vérification**, comme Framadate : chacun fait attention, et voit ses créneaux dans « Mes créneaux ». (ex-Q2) |
| D16 | Rappel la veille | **En V1, avec un lien « Je ne peux plus venir »** qui marche **même après le délai de retrait**. Dans ce cas, l'équipe est prévenue par mail du désistement (§5.9). (ex-Q3) |
| D17 | Autres mails | **Aucun en V1** : pas de mail à l'équipe à chaque inscription ou retrait avant le délai, et pas de mail aux inscrit·es quand l'admin supprime un besoin. L'admin prévient à la main : la page de confirmation de suppression de Django liste déjà les inscriptions qui partent avec le besoin (`CASCADE`). (ex-Q5) |
| D18 | Prénom ou nom manquant | **Une fenêtre (modale) demande le prénom et le nom** au clic sur « Je viens » si le compte n'a pas l'un des deux (seuls les champs vides sont affichés). Elle prévient que le prénom sera **visible par tout le monde** sur le planning, et que le nom ne sera **vu que par l'équipe du lieu** (il sert à retrouver la personne, §5.10). Les deux sont **enregistrés dans le compte** (`TibilletUser.first_name`, `last_name`), puis l'inscription est faite dans la foulée (§5.3). La phrase de l'en-tête (« Ton prénom sera visible sur ce planning ») reste, pour celles et ceux qui ont déjà tout rempli. (ex-Q8, nom ajouté le 2026-10-12) |
| D19 | Plafond | **Pas en V1.** Aucune limite au nombre d'inscrit·es. Si un vrai cas arrive (covoiturage, postes de formation), on ajoutera un champ `plafond` vide par défaut, et un `select_for_update` pour ces besoins-là seulement. (ex-Q10) |
| D20 | Carte du bloc d'accueil | **On garde la rangée des 5 prochains jours colorés en V1** (§5.1), malgré l'avis « superflu » de la seconde relecture. |
| D21 | Compteur de l'en-tête | **Trois chiffres + une jauge**, comme la maquette : « 12 / 34 places couvertes · 2 en renfort · 3 créneaux encore vides », et une barre de remplissage sous le compteur (§5.2). Un créneau vide = un besoin sans aucune inscription. (2026-10-12) |
| D22 | Anonyme sur un besoin couvert | **Badge « Couvert » + « Me connecter pour venir »**, comme la maquette (§5.2). (2026-10-12) |
| D23 | Inscrire quelqu'un à sa place | **Un·e admin du lieu peut inscrire une autre personne** sur un besoin, depuis la page du planning : recherche par nom, prénom ou email parmi les personnes connues du lieu, ou création par email si elle n'y est pas (§5.10). Pour celles et ceux qui ne vont pas sur le site (planning noté au tableau, appel téléphonique). (2026-10-12) |
| D24 | API v2 | **API v2 complète** sur les quatre modèles, plus l'inscription d'une personne et la répétition des besoins (§6 bis). (2026-10-12) |

### 2.2 Proposées par cette spec, validées par le mainteneur (2026-09-24)

| # | Sujet | Proposition | Pourquoi |
|---|---|---|---|
| P1 | Concurrence | **Aucun verrou.** Pas de plafond (D7), donc pas de course sur une « dernière place ». | Ni `select_for_update`, ni isolation SERIALIZABLE : il n'y a rien à protéger. |
| P2 | Double clic | `InscriptionBenevole.objects.get_or_create(besoin=…, user=…)` + `UniqueConstraint(besoin, user)`. | `get_or_create` rattrape lui-même l'`IntegrityError` d'un double clic simultané et relit la ligne (§7). |
| P3 | Se retirer | **Suppression** de la ligne `InscriptionBenevole`. Pas de statut. Supprimer un besoin en admin supprime ses inscriptions (`CASCADE`), sans prévenir (D17). | Le plus simple. Pas de compta ni de remboursement derrière. |
| P4 | Un clic, pas de formulaire | « Je viens » inscrit directement (comme Framadate), toast texte seul. | Pas d'écran de confirmation. Pour se défaire : « Me retirer », déjà présent dans la case. |
| P5 | Prénom affiché | `user.first_name`. Grâce à D18, presque toujours rempli. Repli si vide quand même (compte modifié après coup) : `None` **ou** `""` → « Bénévole » (`first_name` est `null=True`, `AuthBillet/models.py:134`). Jamais l'email, jamais le nom de famille. | D2 rend le prénom public : on n'expose rien de plus. |
| P6 | Besoins passés | Un besoin est passé quand sa **fin** est passée (`fin() <= now`). Masqués côté public. Un planning dont tous les besoins sont passés disparaît du bloc d'accueil. | La page reste courte. L'admin garde tout. Un besoin 18h–21h reste visible jusqu'à 21h. |
| P7 | Module | Sous `module_booking` (pas de nouveau module). Comme `/booking/` aujourd'hui, les vues ne vérifient pas `module_booking` : seuls les menus sont conditionnés. Hérité, pas corrigé ici. | Même app, même entrée de menu admin. |
| P8 | Besoin saisi à la main un jour fermé | **Permis**, avec un avertissement dans l'admin. Seul « Répéter » saute les jours fermés. | Un lieu fermé au public peut avoir besoin de bénévoles ce jour-là (chantier, inventaire, ménage de fond). |
| P9 | Fermeture ajoutée après coup | Les besoins déjà saisis restent affichés. L'admin les supprime s'il le veut. | Même règle que `booking` : « c'est à vous de gérer les réservations à annuler » (`booking/doc/tibillet-booking-presentation_fr.md`). |
| P10 | Retrait après le délai, depuis le site | **Même règle que le lien du mail (D16)** : après le délai, « Me retirer » devient « Je ne peux plus venir », le retrait marche, et l'équipe est prévenue. Avant le délai : retrait silencieux, comme avant. | Sinon, le site serait plus strict que le mail : on se retirerait en fouillant sa boîte mail plutôt qu'en cliquant sur la grille. Et « préviens l'équipe » laisse la personne se débrouiller, alors que le serveur peut le faire. |

## 3. Ce qu'on réutilise, ce qu'on laisse

| On reprend de `booking` | On laisse |
|---|---|
| **Tels quels :** `Calendar` et `ClosedPeriod` (D9) | `Product` / `Price` / `LigneArticle` / Stripe / panier |
| L'idée de nombre de places : `Resource.capacity` → `BesoinBenevole.nombre_souhaite`, mais comme objectif, pas comme plafond (D7) | `WeeklyOpening` / `OpeningEntry` : on déclare des dates réelles, et « Répéter » (§5.7) couvre la récurrence |
| Le délai d'annulation : `Resource.cancellation_deadline_hours` → `PlanningBenevole.delai_desinscription_heures` | L'isolation SERIALIZABLE : sans plafond, rien à verrouiller (P1) |
| Le contrôle d'adhésion : bloc `price.adhesions_obligatoires` de `validate_new_booking` (`booking_engine.py:553-568`, branche `deadline__gte=now` seulement ; la branche `commande` est propre au panier), à recopier (pas à factoriser) | `booking_engine.compute_slots` : rien à calculer, les besoins sont en base |
| Le gabarit `booking/booking_base.html` et le skin courant (`base_template`) | |
| L'onglet « Mon compte » : sur le modèle de `MyAccount.my_bookings` (`BaseBillet/views.py:1353`) | |
| L'email en tâche Celery : sur le modèle de `booking/tasks.py` | |

## 4. Modèle de données (`booking/models.py`)

```
PlanningBenevole ──< BesoinBenevole >── TacheBenevole
   │   │                  │
   │   │                  └──< InscriptionBenevole >── TibilletUser
   │   └──> Calendar (booking, existant, facultatif) ──< ClosedPeriod
   └──< >── Product (adhésions requises, facultatif)
```

### `TacheBenevole` — catalogue du lieu

| Champ | Type | Note |
|---|---|---|
| `name` | `CharField(200)` | « Tenir le bar » |
| `description` | `TextField(blank)` | Affichée sous le nom dans la grille, et reprise dans l'email de confirmation (où, quoi apporter, à qui parler) |
| `etiquette` | FK `Etiquette`, `null`, `blank`, `SET_NULL` | **Seulement si** `TODO/USERS-etiquettes.md` est livré avant (D12). L'inscription pose cette étiquette sur la personne (source `BENEVOLAT`) |

### `PlanningBenevole`

| Champ | Type | Note |
|---|---|---|
| `name` | `CharField(250)` | « Bar associatif : octobre » |
| `slug` | `SlugField(unique)` | URL publique |
| `description` | `TextField(blank)` | Chapô de la page |
| `published` | `BooleanField(default=False)` | Brouillon tant que faux |
| `adhesions_requises` | `ManyToManyField(Product, blank, limit_choices_to={"categorie_article": Product.ADHESION})` | **Vide = ouvert à tout compte connecté. Non vide = réservé aux adhérent·es d'une de ces adhésions (D3).** Un seul champ : pas de choix `acces` ni de `clean()`, donc pas d'état incohérent. Même motif que `Price.adhesions_obligatoires` (`BaseBillet/models.py:1947`) |
| `calendrier` | FK `Calendar`, `null`, `blank`, `PROTECT`, `related_name="plannings_benevoles"` | Jours de fermeture (D9). Vide = aucun jour fermé. `PROTECT`, comme `Resource.calendar` |
| `delai_desinscription_heures` | `PositiveIntegerField(default=24)` | Au-delà, « Me retirer » devient « Je ne peux plus venir » et l'équipe est prévenue (P10) |
| `created_at` | `DateTimeField(auto_now_add)` | |

Méthode `date_est_fermee(une_date)` : renvoie la `ClosedPeriod` qui couvre ce jour, ou `None`.
Pour l'afficher : son `label` (`booking/models.py:217`, peut être vide → repli « fermé du 14 au
15 juil. », à partir de `start_date` / `end_date`).
Un jour est fermé si `start_date <= une_date` et (`end_date` vide **ou** `end_date >= une_date`)
— `end_date` vide veut dire « fermé sans fin » (`booking/models.py`, `ClosedPeriod`).

### `BesoinBenevole`

| Champ | Type | Note |
|---|---|---|
| `planning` | FK `PlanningBenevole`, `CASCADE`, `related_name="besoins"` | |
| `tache` | FK `TacheBenevole`, `PROTECT` | On ne supprime pas une tâche utilisée |
| `date` | `DateField` | |
| `heure_debut` | `TimeField(null, blank)` | Vide = toute la journée |
| `heure_fin` | `TimeField(null, blank)` | Si `heure_fin <= heure_debut` : se termine le lendemain (21:00 → 00:00) |
| `nombre_souhaite` | `PositiveSmallIntegerField(default=1)` | ≥ 1 (`CheckConstraint`). **Objectif, pas plafond** (D7) : on peut s'inscrire au-delà |

Contraintes : les deux heures sont vides ou les deux remplies (`CheckConstraint`).

Méthodes (datetimes aware dans le fuseau du lieu, `Configuration.get_solo().get_tzinfo()`,
même mécanisme que `Event.save()`) :

| Méthode | Calcul | Sert à |
|---|---|---|
| `debut()` | `date` + `heure_debut`, ou `date` à 00:00 si journée | Délai de retrait (`debut() - delai`) |
| `fin()` | `date` + `heure_fin` (+1 jour si `heure_fin <= heure_debut`) ; journée → lendemain 00:00 | `est_passe()` |
| `est_passe()` | `fin() <= now` | Masquer côté public (P6), refuser l'inscription |
| `nombre_inscrits()` | comptage des inscriptions | Compteur « 3/2 » |
| `places_couvertes()` | `min(nombre_inscrits, nombre_souhaite)` | Remplissage, couleurs (D8) |
| `places_libres()` | `max(0, nombre_souhaite - nombre_inscrits)` | « 1 libre » |
| `nombre_de_renforts()` | `max(0, nombre_inscrits - nombre_souhaite)` | « +1 en renfort » |

**Affichage des heures.** `TIME_ZONE = 'UTC'` (`TiBillet/settings.py:539`) et le projet
n'active jamais le fuseau du lieu (`timezone.activate`). Un gabarit qui rendrait `debut()` ou
`fin()` avec `|date` afficherait l'heure UTC. Règle : **les gabarits et les mails affichent
`date`, `heure_debut`, `heure_fin`** (champs sans fuseau, saisis en heure locale).
`debut()` et `fin()` ne servent qu'aux comparaisons.

### `InscriptionBenevole`

| Champ | Type | Note |
|---|---|---|
| `besoin` | FK `BesoinBenevole`, `CASCADE`, `related_name="inscriptions"` | |
| `user` | FK `AUTH_USER_MODEL`, `PROTECT` | |
| `created_at` | `DateTimeField(auto_now_add)` | Ordre d'affichage des prénoms : les premiers inscrits d'abord |
| `rappel_envoye_le` | `DateTimeField(null, blank)` | Rempli quand le rappel de la veille part. Empêche un second envoi (§5.9) |
| `inscrit_par` | FK `AUTH_USER_MODEL`, `null`, `blank`, `SET_NULL`, `related_name="+"` | Traçabilité. Vide = la personne s'est inscrite elle-même. Rempli = l'admin qui l'a inscrite (§5.10), ou le compte de la clé API (`ExternalApiKey.user`, §6 bis) |

`UniqueConstraint(fields=["besoin", "user"])` (P2).

Migrations : **trois**.
- `BaseBillet` : le booléen `ExternalApiKey.volunteering` de l'API (§6 bis).
- `booking/0002_benevolat.py` (il n'existe que `0001_initial`). App en TENANT_APPS.
- une migration `pages` pour la nouvelle source du bloc (§5.1) : les `choices` font partie
  de l'état des migrations. `pages` est aussi en SHARED_APPS : elle passe sur `public`,
  sans SQL.

## 5. Parcours

### 5.1 Découvrir (D14)

- **La page du planning** : `/booking/benevolat/<slug>/`, titrée du nom du planning (§5.2).
- **Le bloc sur l'accueil du lieu** : le bloc CMS « Liste automatique » (`Bloc.LISTE`,
  `pages/models.py`) choisit déjà sa source parmi « les sous-pages d'une page » et « les
  prochains évènements de l'agenda ». On ajoute une **troisième source** :

  ```python
  COUPS_DE_MAIN = "COUPS_DE_MAIN"
  SOURCE_CHOICES = [
      (SOUS_PAGES, _("Les sous-pages d'une page")),
      (EVENEMENTS, _("Les prochains évènements de l'agenda")),
      (COUPS_DE_MAIN, _("Les prochains coups de main (bénévolat)")),
  ]
  ```

  Le lieu pose le bloc où il veut, comme l'agenda. Même mécanique que la source
  `EVENEMENTS` :
  - une balise `{% plannings_benevoles_a_venir bloc.nombre_max as plannings %}` dans
    `pages/templatetags/pages_tags.py`, à côté de `evenements_a_venir` (≈ l.788) ;
  - une branche **`{% elif bloc.source == "COUPS_DE_MAIN" %}`** dans
    `pages/{V2,classic}/partials/bloc_liste.html`, avec les mêmes cartes `tb-bloc--carte`.
    Ces gabarits sont écrits `{% if EVENEMENTS %} … {% else %}` (le `else` = sous-pages) :
    la nouvelle branche va **avant** le `else`, sinon les sous-pages l'avalent. Mettre à jour
    aussi les commentaires d'en-tête des deux gabarits (« les deux sources »), le libellé du
    type LISTE (`pages/models.py:634`), et les `help_text` de `source` et de `nombre_max`
    (≈ l.922).
  - API v2 : `block-types` (`api_v2/views.py` ≈ l.1231) lit les choix du modèle. Vérifier
    `api_v2/openapi-schema.yaml` (≈ l.2454) et `api_v2/GUIDELINES.md` (≈ l.296) : les
    mettre à jour si la liste des sources y est écrite en dur.
- **Une carte par planning** publié qui a au moins un besoin à venir : nom du planning,
  période (« du 2 au 31 oct. »), « 12 places libres », et une **rangée des 5 prochains
  jours** colorés comme les en-têtes (D8). La carte mène à la page du planning.
  Tri : le planning dont le prochain besoin est le plus proche d'abord. `nombre_max` du
  bloc limite le nombre de cartes.
- **Piège multi-tenant** : l'app `pages` est aussi dans `SHARED_APPS` (schéma `public`),
  mais les tables du bénévolat n'existent que dans les schémas des lieux. La balise
  renvoie une liste vide si `connection.schema_name == "public"`. Import du modèle
  **dans** la fonction, comme `evenements_a_venir` (pas d'import circulaire). Note :
  `evenements_a_venir` n'a pas cette garde ; hors périmètre ici.
- **Pas de section sur `/booking/`** en V1.

### 5.2 La page du planning (maquette : onglet « Page publique »)

- En-tête : titre (Unbounded), chapô, badge d'accès, compteur « 12 / 34 places couvertes ·
  2 en renfort · 3 créneaux encore vides » avec une jauge de remplissage dessous (D21), et la
  mention « Ton prénom sera visible sur ce planning. » (D2). La jauge est décorative
  (`aria-hidden="true"`) : le compteur écrit déjà la même information. Le compteur porte
  `aria-live="polite"` et il est rafraîchi en hors bande, comme l'en-tête du jour (§5.3).
- **Desktop** : tableau. Lignes = tâches, colonnes = jours qui ont au moins un besoin.
  Une case peut empiler plusieurs besoins (plages horaires). Case sans besoin : hachurée,
  « pas besoin ». Première colonne collante, défilement horizontal **dans** le conteneur.
- **Mobile** (< 760 px) : liste par jour, chaque besoin porte le nom de sa tâche. En haut,
  une **barre de jours** qui défile à l'horizontale : un bouton par jour (« ven. 2 ·
  3 libres »), coloré comme l'en-tête du jour (D8). Un appui fait défiler jusqu'au jour.
  Pas de JS métier : de simples ancres `#jour-<date>` suffisent (repli sans JS).

**En-têtes de jours colorés (D8).** Pour chaque jour :
`taux = somme des places_couvertes / somme des nombre_souhaite` (0 à 100 %, les renforts ne
le font pas dépasser 100 %). Calcul côté serveur, dans une fonction pure
`taux_de_remplissage(besoins_du_jour)`. Le gabarit pose le résultat en variable CSS
(`style="--remplissage: 67"`), et le CSS fabrique la couleur :

```css
/* 0 % = letchi (rouge) … 100 % = chouchou (vert). Le mélange passe par un orange. */
--remplissage: 0;  /* valeur par défaut sur le conteneur : sans elle, la couleur est invalide */
--couleur-jour: color-mix(in oklch, var(--chouchou) calc(var(--remplissage) * 1%), var(--letchi));
```

La couleur sert de **liseré épais** sous l'en-tête et de **fond très clair** (mélangée au
blanc), jamais de fond sous le texte : le texte reste à l'encre. L'état est **toujours aussi
écrit** (« 3 places libres », « tout est couvert », « +1 en renfort ») : la couleur ne
porte jamais seule l'information (accessibilité, daltonisme). Même traitement pour les
titres de jours de la vue mobile.

- Chaque besoin affiche : plage (« 18h–21h » ou « Journée »), compteur `2/3` (ou `3/2` en
  renfort), une pastille par inscrit·e (prénom, ou « Toi »), une pastille « libre » en
  pointillés par place restante, puis **une** action :

| État de la personne | Action affichée |
|---|---|
| Anonyme, besoin pas encore couvert | « Me connecter pour venir » → ouvre `#loginPanel` |
| Anonyme, besoin couvert | badge « Couvert » + « Me connecter pour venir » (D22) |
| Connectée, pas le droit (D3) | badge « Réservé aux adhérent·es » |
| Connectée, besoin pas encore couvert | bouton principal « Je viens » |
| Connectée, besoin couvert | badge « Couvert » + bouton secondaire « Je viens aussi » (D7) |
| Déjà inscrite, avant le délai | « Tu y es » + « Me retirer » |
| Déjà inscrite, après le délai | « Tu y es » + « Je ne peux plus venir » (l'équipe sera prévenue, P10) |

« Je viens aussi » est volontairement **secondaire** : le bouton principal reste réservé aux
besoins qui manquent de monde, pour que l'œil aille d'abord là.

**Admin du lieu** (`user.is_tenant_admin(connection.tenant)`) : en plus de l'action du tableau,
chaque besoin à venir porte un lien « Inscrire quelqu'un » (§5.10).

- Bloc « Pas dispo cette fois ? » : inscription à la lettre d'information (§5.8), sous la
  grille.
- Rappel « Le collectif n'est ni ton patron ni ton ami… » : reprendre **les mêmes msgid**
  que `pages/V2/partials/evenement_benevoles.html:71-72` (en anglais, déjà traduits),
  plutôt que d'écrire une nouvelle chaîne.

### 5.3 S'inscrire (« Je viens » / « Je viens aussi »)

1. `hx-post` sur `/booking/benevolat/besoin/<pk>/inscrire/`, `hx-target` = la case,
   `hx-swap="outerHTML"`.
2. Vérifications (serializer DRF) : connecté·e, planning publié, besoin pas passé,
   droit d'accès (D3, contrôle d'adhésion recopié de `booking_engine.py:553-568`).
   **Pas** de contrôle du nombre d'inscrits (D7).
3. **Prénom ou nom manquant (D18)** : si `user.first_name` **ou** `user.last_name` est vide
   (`None` ou blanc), pas d'inscription tout de suite. La réponse ouvre une fenêtre (modale
   Bootstrap 5 : `bootstrap.bundle` est chargé par les trois shells, `V2`, `classic` et
   `faire_festival`) :

   > **Comment on t'appelle ?**
   > Ton prénom sera **visible par tout le monde** sur ce planning, même par les personnes
   > sans compte. Ton nom ne sera vu que par l'équipe du lieu. Les deux seront enregistrés
   > dans ton compte : on ne te les redemandera pas.
   > `[ Prénom ]` `[ Nom ]` `[ Enregistrer et venir ]` `[ Annuler ]`

   Seuls les champs vides du compte sont affichés (un compte qui a déjà un prénom ne voit que
   « Nom »). Le formulaire poste sur la **même** URL `inscrire`, avec `prenom` et/ou `nom`.
   Serializer : deux `CharField` facultatifs, nettoyés (`strip`), 1 à 200 caractères
   (`first_name` et `last_name` font 200, `AuthBillet/models.py:134-135`). Un champ vide dans
   le compte **doit** être fourni ; un champ déjà rempli dans le compte est ignoré s'il est
   envoyé (la modale ne réécrit pas un nom existant). Si valide : on remplit les champs
   manquants puis `user.save(update_fields=[...les champs remplis...])`, puis on continue à
   l'étape 4.

   **Côté htmx, un seul mécanisme : le hors bande** (`hx-swap-oob`, déjà utilisé dans le
   projet ; `HX-Retarget` ne l'est nulle part). La réponse contient la case **inchangée** +
   `<div id="benevolat-modale" hx-swap-oob="true">…la modale…</div>`, et l'en-tête
   `HX-Trigger: ouvrirModalePrenom` ; trois lignes de JS appellent
   `bootstrap.Modal.getOrCreateInstance(...).show()`. Après l'envoi du prénom, la réponse
   remplace la case, vide `#benevolat-modale` en hors bande, et la modale se ferme.
   L'utilisateur est en `SHARED_APPS` : ce prénom et ce nom sont aussi ceux des autres lieux.
   C'est voulu, c'est le même compte.
4. `get_or_create` de l'`InscriptionBenevole` (§7).
5. Réponse : le partial **de la case seule** + toast texte (« C'est noté… ») via le
   mécanisme existant `panierToast` (`BaseBillet/views.py:5613-5638` ; l'écouteur est dans
   `BaseBillet/templates/htmx/components/panier_scripts.html:68`, inclus par les trois
   shells), pas un nouvel événement. L'en-tête du jour (couleur,
   compteur) **et** le compteur du planning avec sa jauge (D21) sont rafraîchis par un **swap
   hors bande** (`hx-swap-oob`) dans la même réponse.
6. Email de confirmation (Celery) : date, plage, tâche, description, lien « Mes créneaux ».
   Le lien « Je ne peux plus venir » (§5.9) y est ajouté au chantier 5.

Erreurs (pas le droit, besoin passé) : partial de la case recalculée en **422**, avec le
message. **Aucun shell ne swappe les 422** (`V2/shell.html:200-208`,
`classic/shell.html:194-197`, `faire_festival/shell.html:166-169` n'acceptent que 404/500) : `planning.html` reprend le listener `htmx:beforeOnLoad` posé page par page dans
`booking/views/resource.html:799-805`.

### 5.4 Se retirer

`hx-post` sur `/booking/benevolat/besoin/<pk>/retirer/`. Avant `debut() - delai` : retrait
silencieux. Après : le retrait marche aussi, et un mail part à l'équipe (P10, même mail
qu'en §5.9). Refusé seulement si le besoin est passé (`est_passe()`).
Suppression de l'inscription (P3). Depuis la grille ou depuis « Mes créneaux ». Même
réponse qu'en §5.3 (case + en-tête du jour hors bande).

### 5.5 Mon compte → « Mes créneaux bénévoles »

Nouvelle action `MyAccount.my_volunteering` sur le modèle de `my_bookings`
(`BaseBillet/views.py:1353`). Liste des inscriptions à venir, triées par date, avec
« Me retirer » (avant le délai) ou « Je ne peux plus venir » (après : l'équipe est prévenue, P10).

Entrées à ajouter : les raccourcis de `V2/vues/compte/index.html:185-189` et de
`classic/vues/compte/index.html:82-90`, à côté de « Mes réservations ».
(`account_base.html` n'a pas de nav : `account_tab` n'y sert qu'au lien « Retour à mon compte ».)

### 5.6 Admin (Unfold)

- `TacheBenevoleAdmin` : liste simple.
- `PlanningBenevoleAdmin` : fiche (dont le champ `calendrier`) + `TabularInline` des
  besoins (date, tâche, début, fin, nombre souhaité, inscrit·es en lecture seule). Même
  motif que `WeeklyOpening` + ses `OpeningEntry` (`Administration/admin/resources.py`).
  Un besoin saisi un jour fermé est **enregistré** (P8). L'avertissement est une **colonne
  en lecture seule** de l'inline, « Fermé : Fête nationale » (le `label`, ou le repli),
  calculée par `date_est_fermee`. Pas de `messages.warning` : il faudrait surcharger
  `save_formset`, ce que rien ne fait dans `Administration/`.
- `InscriptionBenevoleAdmin` : liste filtrable par planning et par date, recherche par
  prénom, nom et email (`user__first_name`, `user__last_name`, `user__email`), suppression.
  **Pas de formulaire d'ajout** (`has_add_permission` renvoie `False`) : on inscrit
  quelqu'un depuis la page du planning (§5.10), qui a la recherche par nom. Raison technique :
  `TibilletUser` n'a pas d'admin sur `staff_admin_site`, donc `autocomplete_fields = ["user"]`
  lève `admin.E039`, et une liste déroulante de tous les comptes du lieu est inutilisable.
  Colonne « Inscrit·e par » (`inscrit_par`, vide = soi-même).
- Action « Répéter des besoins » sur la fiche planning : voir §5.7.
- `Administration/admin/dashboard.py` : entrées de menu dans le bloc `module_booking`
  (≈ l.772-818), **plus** les deux dictionnaires par modèle à compléter pour les trois
  nouveaux modèles : aide (≈ l.1316-1321, ex. `"booking.weeklyopening"`) et verbe
  (≈ l.1387-1389, `"gerer"` / `"configurer"`).

### 5.7 Admin : répéter des besoins (le « modèle »)

**Le problème :** chaque semaine, le bar a besoin des mêmes créneaux (ven. 18h–21h et
21h–minuit, sam. idem). On ne veut pas les ressaisir.

**Le principe :** on saisit une fois une **période modèle** (un jour, ou une semaine), puis
on la répète. Pas de nouveau modèle de données : le modèle, ce sont des besoins déjà saisis.

**Le formulaire** (bouton « Répéter des besoins » en haut de la fiche planning,
`actions_detail` Unfold) :

| Champ | Exemple | Règle |
|---|---|---|
| Modèle : du … au … | 2 oct. → 3 oct. | Les besoins du planning dans cette période servent de modèle. Pré-rempli : les 7 premiers jours du planning |
| Répéter tous les | `1` | Entier ≥ 1 |
| … | `semaine(s)` | Choix : `jour(s)` ou `semaine(s)` |
| Nombre de fois | `4` | Entier entre 1 et 52 |

Exemples :
- **« Répéter sur X semaines »** : modèle = ven. 2 → sam. 3 oct., tous les **1 semaine**,
  **4 fois** → mêmes besoins les 9-10, 16-17, 23-24 et 30-31 oct.
- **« Répéter sur X jours »** : modèle = sam. 3 oct. (ménage 10h–12h), tous les **1 jour**,
  **6 fois** → ménage du 4 au 9 oct.
- Un week-end sur deux : tous les **2 semaines**.

**Le calcul :** pour chaque besoin du modèle et pour `k` de 1 à « nombre de fois » :
`nouvelle date = date + k × écart` (écart = N jours, ou N × 7 jours). Tâche, heures et
`nombre_souhaite` sont copiés. **Les inscriptions ne sont jamais copiées.**

**Garde-fous :**
- **Jours fermés (D9)** : une copie qui tombe un jour fermé du `calendrier` du planning
  est **sautée**, pas décalée. L'aperçu la montre avec le `label` de la fermeture
  (« sauté : Fête nationale »), ou le repli « sauté : fermé du 14 au 15 juil. ». Planning sans calendrier : rien n'est sauté.
- **Doublons** : si un besoin identique existe déjà (même planning, tâche, date, heure de
  début, heure de fin), la copie est ignorée. On peut relancer l'action sans risque.
- **Aperçu avant création** : le premier envoi affiche trois listes : à créer, sautés
  (fermeture), ignorés (déjà présents). Le bouton « Confirmer » crée tout, dans une seule
  transaction. Message de retour : « 14 besoins créés, 2 sautés (fermeture), 2 ignorés
  (déjà présents). »

**Technique :** une vue d'admin avec son propre gabarit, branchée par `get_urls()` sur
`PlanningBenevoleAdmin`. C'est un mécanisme déjà utilisé : `module_toggle_modal`
(`Administration/admin_tenant.py:513`), `scanner` (≈ l.3569), `inventaire.py:302`,
`laboutik.py:1175`, `render(request, "admin/module_page.html")` (`dashboard.py:1503`).
Le bouton `actions_detail` (précédent l.361) redirige vers cette URL. Formulaire :
un `forms.Form` admin (permis dans l'admin, précédent `ResourceAddAdmin(ModelForm)`,
`Administration/admin/resources.py:136`). Gabarit `admin/booking/planning_repeter.html`
en styles inline (règle Unfold), sur le modèle de `admin/module_page.html`. Le calcul des dates
est une **fonction pure**
`calculer_repetitions(besoins_modele, ecart_en_jours, nombre_de_fois, periodes_fermees, besoins_existants)`
dans `booking/benevolat.py`, testable sans base : elle renvoie les trois listes de l'aperçu.


### 5.8 Se tenir informé·e : la lettre d'information (D10)

**Le besoin :** on n'est pas dispo sur ce planning, mais on veut savoir quand l'équipe
aura de nouveau besoin de monde.

**Le bloc** (sous la grille, maquette : onglet « Page publique ») :

> **Pas dispo cette fois ?**
> Reçois la lettre d'information du lieu : les prochains coups de main y sont annoncés.
> `[ ton@email.fr ]` `[ Je m'inscris à la lettre d'information ]`

- Connecté·e : le champ est pré-rempli avec l'email du compte (modifiable).
- Affiché **seulement si le Ghost du lieu est configuré** (`GhostConfig.ghost_url` et
  `GhostConfig.ghost_key` renseignés). Attention : la variable existante `newsletter_active`
  (`BaseBillet/views.py:3626`) est vraie aussi avec Brevo seul, alors que
  `send_to_ghost_email` ne parle qu'à Ghost. Ne pas la réutiliser telle quelle.

**Le clic** : `hx-post` sur `/booking/benevolat/<slug>/lettre/`, `hx-target` = le bloc,
`hx-swap="outerHTML"`. Serializer : un `EmailField`. Un seul chemin (D13), le même que la
case « newsletter » des formulaires (`BaseBillet/views.py:659`) :
`send_to_ghost_email.delay(email, nom, etiquettes_en_plus=["Bénévolat"])`. Le nom est
celui du compte si la personne est connectée, vide sinon.

Message à la place du bloc : « C'est noté : ton@email.fr recevra la lettre d'information. »

**L'étiquette « Bénévolat ».** On ajoute un paramètre facultatif à la tâche existante :
`send_to_ghost_email(email, name=None, etiquettes_en_plus=None)`. Les étiquettes actuelles
(`"TiBillet"`, `"import <date>"`, `BaseBillet/tasks.py` ≈ l.1617) sont gardées, et
`"Bénévolat"` s'y ajoute. L'équipe peut alors, dans Ghost, envoyer un numéro aux seuls
membres étiquetés « Bénévolat ». Les autres appels de la tâche ne changent pas.

**Membre Ghost déjà existant.** Aujourd'hui la tâche ne pose les étiquettes qu'à la
**création** (`BaseBillet/tasks.py` ≈ l.1617) ; si l'email est déjà membre (≈ l.1641), elle
ne fait rien. Or beaucoup de bénévoles sont déjà abonné·es (case « newsletter », adhésion).
Donc, dans la branche « membre existant » : si `etiquettes_en_plus` contient une étiquette
absente de `members[0]["labels"]`, faire un
`PUT {ghost_url}/ghost/api/admin/members/{id}/` avec
`{"members": [{"labels": <étiquettes existantes + manquantes>}]}` (mêmes en-têtes).
Sans `etiquettes_en_plus`, rien ne change pour les appels actuels.

**Garde-fous :** pas de plafond de requêtes sur ce point d'entrée aujourd'hui (même constat
que A4 dans `TODO/AUTH-connexion-par-code-achat-connecte.md`). Aucun compte TiBillet n'est
créé pour un email tapé ici : seul un membre Ghost l'est.

### 5.9 Rappel la veille et « Je ne peux plus venir » (D16)

**Le rappel.** Chaque jour, une tâche Celery envoie un mail à chaque personne inscrite à un
besoin **du lendemain** :

> **Demain 18h–21h : tu tiens le bar. Merci !**
> Bar associatif : octobre · samedi 10 oct. · Tenir le bar · 18h–21h
> Consignes : *(la description de la tâche)*
> `[ Je ne peux plus venir ]` · lien vers « Mes créneaux »

- Tâche `rappeler_les_benevoles_du_lendemain` dans `booking/tasks.py`, sur le modèle de
  `membership_renewal_reminder` (`BaseBillet/tasks.py:1691`) : boucle sur les lieux avec
  `tenant_context`, en excluant `public`.
- Programmée dans `TiBillet/celery.py` avec les autres (`add_periodic_task` +
  `crontab`), par un wrapper `@app.task` local comme `cron_purge_stale_onboard_drafts`
  (`celery.py` ≈ l.163-179 : import local + appel direct). Heure
  proposée : **8h UTC** (le matin, pas en pleine nuit).
- « Demain » = `date` du besoin égale à la date de demain **dans le fuseau du lieu**
  (`Configuration.get_solo().get_tzinfo()`), pas en UTC.
- Seulement les inscriptions dont `rappel_envoye_le` est vide ; le champ est rempli juste
  après l'envoi. Relancer la tâche n'envoie donc rien deux fois.

**Le lien « Je ne peux plus venir ».** La personne peut ne pas être connectée sur son
téléphone. Le lien porte donc sa preuve :

1. Lien signé : `/booking/benevolat/desistement/<jeton>/`. Le jeton est
   `signing.dumps(inscription.pk, salt="benevolat-desistement")`, relu par
   `signing.loads(...)`. **Pas de durée de validité dans le jeton** : un `max_age` se donne
   avant de connaître l'inscription. « Expiré » = le besoin est passé (`est_passe()`).
   `BadSignature` → page « Ce lien ne marche plus » (précédent : `AuthBillet/views.py:133-135`).
2. **GET = une page de confirmation, jamais une suppression.** Les antivirus et les
   messageries ouvrent souvent les liens des mails tout seuls : un GET qui supprimerait
   désinscrirait des gens sans qu'ils le sachent. La page affiche le créneau et un bouton
   « Oui, je ne peux plus venir ».
3. **POST = le retrait.** L'inscription est supprimée, **même après le délai de retrait**
   (D16).
4. Si le délai était passé : mail à l'équipe (`Configuration.email`) : « Camille ne
   pourra pas venir demain 18h–21h (Tenir le bar). Il reste 1 personne sur 2. »
5. Jeton invalide, expiré, ou inscription déjà supprimée : page « Ce lien ne marche plus.
   Tes créneaux sont dans Mon compte. » (pas d'erreur 500).

**Le même lien sert dans le mail de confirmation** (§5.3, étape 6), ajouté au chantier 5 :
un seul mécanisme pour se retirer depuis un mail. La page de confirmation est un
formulaire HTML classique : `{% csrf_token %}` obligatoire.

### 5.10 Inscrire quelqu'un à sa place (D23)

**Le besoin :** une personne s'engage au comptoir ou au téléphone, mais ne va pas sur le
site. L'équipe l'inscrit elle-même, pour que la grille reste juste.

**Qui :** un·e admin du lieu (`request.user.is_tenant_admin(connection.tenant)`). Le lien
n'est affiché qu'à elles et eux, **et** chaque vue revérifie le droit côté serveur (403
sinon) : cacher un bouton ne protège rien.

**Le parcours** (tout dans la fenêtre `#benevolat-modale` de §5.3) :

1. Lien « Inscrire quelqu'un » sur un besoin à venir → `hx-get` de
   `/booking/benevolat/besoin/<pk>/inscrire-une-personne/`, qui renvoie la modale en hors
   bande + `HX-Trigger: ouvrirModalePrenom` (même mécanisme que §5.3, pas un second).
   Titre : « Inscrire quelqu'un : Tenir le bar, sam. 10 oct., 18h–21h ».
2. **Recherche** : un champ « Nom, prénom ou email » avec
   `hx-get="…/chercher-une-personne/"`, `hx-trigger="input changed delay:300ms"`,
   `hx-target="#benevolat-resultats"` (`aria-live="polite"`). Côté serveur :
   - le queryset est **`HumanUser.objects`** (`AuthBillet/models.py:416`) : le proxy ne
     renvoie que les comptes humains rattachés au lieu (`client_achat`). Les comptes des
     autres lieux ne sortent jamais, même en tapant leur email exact ;
   - filtre `Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)` ;
   - au moins 2 caractères (sinon : « Tape au moins 2 lettres »), 10 résultats au plus, triés
     par nom puis prénom ;
   - chaque résultat affiche « Prénom Nom · email » et un bouton « Inscrire ». Une personne
     déjà inscrite sur ce besoin affiche « déjà inscrite » sans bouton.
3. **Inscrire une personne trouvée** : `hx-post` sur
   `/booking/benevolat/besoin/<pk>/inscrire-une-personne/` avec `user` (son pk).
   Le serializer **revérifie** que ce pk est dans `HumanUser.objects` : un pk forcé vers le
   compte d'un autre lieu est refusé (même règle que la carte NFC de
   `Administration/admin/laboutik.py:952`).
4. **Personne introuvable** : sous les résultats, « Pas dans la liste ? » ouvre trois
   champs : email, prénom, nom (les trois obligatoires, D18). `hx-post` sur la même URL.
   Le serveur appelle `get_or_create_user(email, send_mail=False)` (`AuthBillet/utils.py:96`),
   qui rattache le compte au lieu (`client_achat`). Prénom et nom ne sont écrits **que s'ils
   sont vides** dans le compte : si l'email existe déjà, on ne réécrit pas le nom d'une
   personne qui l'a choisi elle-même (le compte est partagé entre lieux).
5. **L'inscription** : `get_or_create(besoin=…, user=…, defaults={"inscrit_par": request.user})`
   (§7). Mêmes vérifications que §5.3 (planning publié, besoin pas passé), **sauf le
   contrôle d'adhésion (D3)** : l'équipe décide qui elle inscrit. Pas de modale prénom non plus :
   une personne trouvée sans prénom s'affiche « Bénévole » (P5).
6. **Réponse** : comme §5.3 (la case, l'en-tête du jour et le compteur en hors bande), la
   modale vidée en hors bande, toast « Camille Martin est inscrite ».
7. **Mail à la personne** : le mail de confirmation de §5.3, avec une première phrase
   différente : « L'équipe de <lieu> t'a inscrit·e. Si ce n'est pas bon, retire-toi depuis
   Mon compte. » (plus le lien de désistement au chantier 5). La tâche Celery reçoit un
   paramètre `par_l_equipe=True` : c'est l'appelant qui choisit le texte (cette vue et
   l'API, §6 bis), pas le champ `inscrit_par`, qui peut être vide (clé API sans compte).

**Retirer quelqu'un** : depuis l'admin Unfold (`InscriptionBenevoleAdmin`, suppression),
sans mail (D17). Pas de bouton « retirer » pour l'équipe dans la grille en V1.

## 6. Vues, URLs, gabarits

`booking/views_benevolat.py` — `BenevolatViewSet(viewsets.ViewSet)` :

| Méthode | URL | Rôle |
|---|---|---|
| `retrieve` | `GET /booking/benevolat/<slug>/` | Page du planning |
| `inscrire` | `POST /booking/benevolat/besoin/<pk>/inscrire/` | §5.3 |
| `retirer` | `POST /booking/benevolat/besoin/<pk>/retirer/` | §5.4 |
| `lettre` | `POST /booking/benevolat/<slug>/lettre/` | §5.8 |
| `desistement` | `GET` / `POST /booking/benevolat/desistement/<jeton>/` | §5.9 |
| `inscrire_une_personne` | `GET` / `POST /booking/benevolat/besoin/<pk>/inscrire-une-personne/` | §5.10 : GET = la modale, POST = l'inscription. Admin du lieu seulement |
| `chercher_une_personne` | `GET /booking/benevolat/besoin/<pk>/chercher-une-personne/?q=` | §5.10 : les résultats de la recherche. Admin du lieu seulement |

Branchement par `path()` explicites, **avant** `router.urls` (un `@action` du router
produirait `benevolat/<pk>/inscrire/`, pas `benevolat/besoin/<pk>/…`). Aucune de ces routes
n'entre en collision avec une autre : leurs nombres de segments diffèrent. La lettre est
rattachée au planning (`<slug>/lettre/`) : un planning peut donc s'appeler « lettre ».

```python
urlpatterns = [
    path("benevolat/besoin/<int:pk>/inscrire/", BenevolatViewSet.as_view({"post": "inscrire"}), name="benevolat-inscrire"),
    path("benevolat/besoin/<int:pk>/retirer/", BenevolatViewSet.as_view({"post": "retirer"}), name="benevolat-retirer"),
    path("benevolat/besoin/<int:pk>/inscrire-une-personne/", BenevolatViewSet.as_view({"get": "inscrire_une_personne", "post": "inscrire_une_personne"}), name="benevolat-inscrire-une-personne"),
    path("benevolat/besoin/<int:pk>/chercher-une-personne/", BenevolatViewSet.as_view({"get": "chercher_une_personne"}), name="benevolat-chercher-une-personne"),
    path("benevolat/desistement/<str:jeton>/", BenevolatViewSet.as_view({"get": "desistement", "post": "desistement"}), name="benevolat-desistement"),
    path("benevolat/<slug:slug>/lettre/", BenevolatViewSet.as_view({"post": "lettre"}), name="benevolat-lettre"),
    path("benevolat/<slug:slug>/", BenevolatViewSet.as_view({"get": "retrieve"}), name="benevolat-planning"),
] + router.urls
```

**Piège (étroit) :** `BookingViewSet` est enregistré sur le préfixe vide `r""`. Ses routes
sont `<pk>/resource|book|slot-unavailable|cancel/`. Seul un slug de planning valant
exactement l'un de ces mots serait avalé si les `path()` passaient après le router.
Test d'URL avec le slug `book`.

Accessibilité de la grille : `<caption>`, `<th scope="col">` pour les jours,
`<th scope="row">` pour les tâches ; `aria-label` de « Je viens » avec la tâche, le jour
et la plage (sinon N boutons au même nom) ; la place « libre » porte le texte, pas
seulement un style pointillé ; l'état du jour est écrit, pas seulement coloré (D8) ;
`tabindex="0"` sur le conteneur qui défile horizontalement.

Gabarits (`booking/templates/booking/benevolat/`) : `planning.html` (étend
`booking/booking_base.html`), `partials/besoin.html` (une case, rendue seule par htmx),
`partials/entete_jour.html` (rendu seul en hors bande), `partials/grille.html`,
`partials/jours_mobile.html`, `partials/lettre.html`, `partials/compteur.html` (rendu seul en
hors bande, D21), `partials/inscrire_une_personne.html` (la modale de §5.10),
`partials/resultats_personnes.html`, `desistement.html` (confirmation + « ce lien ne marche plus »), `emails/confirmation.html`, `emails/rappel.html`, `emails/desistement_equipe.html`.
CSS : classes du skin V2 (`.btn--primary`, `.btn--secondary`, `.badge`, `.callout`) et ses
couleurs de marque (`--letchi`, `--chouchou`). `color-mix` : Chrome 111+, Firefox 113+,
Safari 16.2+ ; déjà utilisé dans `V2.css`. Styles propres à la grille dans
un fichier de l'app, jamais dans `www/static/`.

`data-testid` : `benevolat-modale-prenom`, `benevolat-prenom`, `benevolat-nom`, `benevolat-grille`,
`benevolat-compteur`, `benevolat-inscrire-quelquun-<pk>`, `benevolat-recherche-personne`,
`benevolat-resultat-personne-<user_pk>`, `benevolat-creer-personne`, `benevolat-entete-jour-<date>`, `benevolat-lettre-email`,
`benevolat-lettre-inscrire`, `benevolat-besoin-<pk>`,
`benevolat-je-viens-<pk>`, `benevolat-je-viens-aussi-<pk>`, `benevolat-retirer-<pk>`,
`benevolat-mon-creneau-<pk>`, `benevolat-jour-mobile-<date>`, `benevolat-modale-annuler`,
`benevolat-desistement-confirmer`, `benevolat-repeter-apercu`, `benevolat-repeter-confirmer`.

Chaînes traduisibles en français (`_()`), à signaler au mainteneur en fin de chantier.

## 6 bis. API v2 (D24)

Une API complète, pour qu'un outil externe (ou un agent, skill `tibillet-api`) puisse monter
un planning, ses besoins, et inscrire des gens sans passer par l'admin. Mêmes conventions que
le reste d'`api_v2/` : `viewsets.ViewSet` aux méthodes explicites, `SemanticApiKeyPermission`,
réponses en vocabulaire schema.org, listes enveloppées dans `{"results": [...]}`, isolation
par lieu (la clé ne voit que le schéma de son lieu).

### Droit de la clé

Un booléen **`ExternalApiKey.volunteering`** (`verbose_name=_("Bénévolat")`,
`BaseBillet/models.py` ≈ l.5313, migration `BaseBillet`). Un seul droit pour les quatre
routes, comme `page` couvre pages et blocs : dans `api_permissions()` (≈ l.5342),
`"volunteertask"`, `"volunteerplanning"`, `"volunteerneed"` et `"volunteersignup"` valent
tous `self.volunteering`. L'ajouter aux `fields` de l'admin des clés
(`Administration/admin_tenant.py` ≈ l.221-233). Sans ce droit : 403.

### Routes (`api_v2/urls.py`)

| Route | Basename | Type schema.org | Actions |
|---|---|---|---|
| `/api/v2/volunteer-tasks/` | `volunteertask` | `DefinedTerm` | list, create, retrieve, PATCH, DELETE |
| `/api/v2/volunteer-plannings/` | `volunteerplanning` | `EventSeries` | list, create, retrieve, PATCH, DELETE, `POST {id}/repeat/` |
| `/api/v2/volunteer-needs/` | `volunteerneed` | `Event` (`additionalType: "Volunteering"`) | list, create, retrieve, PATCH, DELETE |
| `/api/v2/volunteer-signups/` | `volunteersignup` | `RsvpAction` | list, create, retrieve, DELETE |

`identifier` = la clé primaire entière. Un planning se cherche aussi par son slug
(`/api/v2/volunteer-plannings/bar-octobre/`), comme les pages (uuid **ou** slug).

### Tâche → `DefinedTerm`

```
identifier = pk
name        = name
description = description
```

DELETE d'une tâche utilisée par un besoin : `PROTECT` lève `ProtectedError` → **409** avec le
message « Cette tâche sert encore à N besoins ».

### Planning → `EventSeries`

```
identifier  = pk
name        = name
description = description
url         = "/booking/benevolat/<slug>/"
startDate   = date du premier besoin   (lecture seule, absent si aucun besoin)
endDate     = date du dernier besoin   (lecture seule)
subEvent    = [Event besoin, ...]      (retrieve seulement, pas dans la liste)
additionalProperty = PropertyValue[] :
  slug, published, delaiDesinscriptionHeures,
  requiredMembershipPlans  = [uuid de Product adhésion]  (vide = tout compte connecté, D3)
  closingCalendar          = id du Calendar, ou null    (D9)
  placesCouvertes, placesSouhaitees, renforts, creneauxVides  (lecture seule, D21)
```

En entrée : un `requiredMembershipPlans` qui contient un produit qui n'est pas une adhésion
→ 400. Un `closingCalendar` inconnu → 400. DELETE : supprime besoins et inscriptions
(`CASCADE`), sans mail (D17).

**Répéter** — `POST /api/v2/volunteer-plannings/{id}/repeat/` : la même fonction pure
`calculer_repetitions` que l'admin (§5.7), mêmes règles (écart ≥ 1, 1 à 52 fois, jours fermés
sautés, doublons ignorés, inscriptions jamais copiées).

```json
{
  "modelStartDate": "2026-10-02",
  "modelEndDate": "2026-10-03",
  "repeatEvery": 1,
  "unit": "week",
  "repeatCount": 4,
  "dryRun": true
}
```

`dryRun: true` → **200** avec les trois listes de l'aperçu (`toCreate`, `skippedClosed` avec
le libellé de la fermeture, `ignoredExisting`), rien n'est écrit. `dryRun: false` (défaut)
→ **201**, même corps, tout est créé dans une seule transaction.

### Besoin → `Event`

```
@type          = "Event"
additionalType = "Volunteering"
identifier     = pk
superEvent     = {"@type": "EventSeries", "identifier": <planning>, "name": ...}
about          = {"@type": "DefinedTerm", "identifier": <tâche>, "name": ...}
startDate      = date + heure_debut, dans le fuseau du lieu, avec son décalage
                 ("2026-10-10T18:00:00+02:00") ; journée entière → la date seule ("2026-10-10")
endDate        = date + heure_fin (lendemain si heure_fin <= heure_debut) ; absent si journée
remainingAttendeeCapacity = places_libres()
attendee       = [{"@type": "Person", "givenName": ...}]   (prénoms seulement, P5)
additionalProperty = PropertyValue[] :
  nombreSouhaite (entrée/sortie), nombreInscrits, renforts (lecture seule),
  fermeture = libellé de la ClosedPeriod qui couvre ce jour, ou null (lecture seule, P8)
```

**Entrée des dates.** `startDate` = une date (`"2026-10-03"` → journée entière) ou une date
et une heure. Une heure sans décalage est lue dans le fuseau du lieu ; une heure avec
décalage est convertie dans le fuseau du lieu. Le modèle garde `date`, `heure_debut`,
`heure_fin` sans fuseau (§4, « Affichage des heures »). `endDate` est obligatoire si
`startDate` a une heure, interdit sinon ; sa date doit être le jour même ou le lendemain
(400 sinon). `superEvent` et `about` acceptent l'`identifier` seul.

Liste : filtres `?planning=<id>`, `?task=<id>`, `?dateFrom=`, `?dateTo=`. Les besoins passés
sont inclus (l'API sert l'équipe, pas le public). Un besoin créé un jour fermé est accepté,
avec `fermeture` rempli dans la réponse (P8). DELETE : supprime ses inscriptions, sans mail
(D17).

### Inscription → `RsvpAction`

```
@type        = "RsvpAction"
identifier   = pk
rsvpResponse = "https://schema.org/RsvpResponseYes"
object       = {"@type": "Event", "identifier": <besoin>}
agent        = {"@type": "Person", "email": ..., "givenName": ..., "familyName": ...}
startTime    = created_at
additionalProperty = PropertyValue[] : inscritPar (email, ou null), rappelEnvoyeLe (lecture seule)
```

Ici l'email et le nom sont donnés : la clé appartient à l'équipe du lieu, qui voit déjà ces
informations dans l'admin.

**Création** — c'est l'API de §5.10, mêmes règles :

```json
{
  "object": {"identifier": 42},
  "agent": {"email": "camille@exemple.org", "givenName": "Camille", "familyName": "Martin"}
}
```

- `get_or_create_user(email, send_mail=False)` : le compte est créé s'il n'existe pas, et
  rattaché au lieu. `givenName` et `familyName` ne sont écrits que s'ils sont vides dans le
  compte. S'ils manquent dans le compte **et** dans la requête → 400 (D18).
- Planning publié et besoin pas passé, sinon 400. Pas de contrôle d'adhésion (comme §5.10).
- `get_or_create` avec `inscrit_par = ExternalApiKey.user` : **201** si créée, **200** avec
  l'inscription existante si la personne y était déjà (rejouer l'appel est sans danger).
- Mail de confirmation avec `par_l_equipe=True` (§5.10, étape 7), seulement à la création.

Liste : filtres `?need=<id>`, `?planning=<id>`, `?email=`, `?dateFrom=`, `?dateTo=`.
**DELETE** : retire la personne, à tout moment, **sans mail** (l'équipe agit, comme en admin,
D17). Pas de PATCH : une inscription n'a rien de modifiable.

### Documentation à tenir à jour (même commit)

- `api_v2/openapi-schema.yaml` : les quatre routes, `repeat`, les schémas.
- `api_v2/GUIDELINES.md` : une section « Bénévolat » (droit, routes, mappings, exemples).
- `TECH_DOC/SKILLS/tibillet-api/` : le skill (règle de `api_v2/GUIDELINES.md` : « un skill
  qui ment est pire que pas de skill »).

## 7. Double clic

Sans plafond (D7), deux personnes différentes ne se gênent jamais : pas de verrou.
Le seul cas à gérer est la même personne qui clique deux fois très vite.

```python
# get_or_create crée la ligne dans un point de sauvegarde. Si un second clic
# simultané a déjà créé la même ligne, la contrainte d'unicité lève une
# IntegrityError : get_or_create la rattrape et relit la ligne existante.
inscription, inscription_vient_d_etre_creee = InscriptionBenevole.objects.get_or_create(
    besoin=besoin,
    user=request.user,
)
```

Si `inscription_vient_d_etre_creee` est faux : pas de second email, même réponse (la case).

## 8. Tests

| Quoi | Où |
|---|---|
| Contraintes (heures, `nombre_souhaite ≥ 1`, unicité) ; `debut()` / `fin()` avec fin à minuit | `booking/tests/test_benevolat_models.py` |
| `date_est_fermee` : jour dans une fermeture, jour au bord, fermeture sans fin, planning sans calendrier | idem |
| `taux_de_remplissage` : 0 %, partiel, 100 %, renforts plafonnés à 100 % | idem (fonction pure) |
| Inscription : anonyme refusé, planning réservé sans/avec adhésion, besoin passé (et 18h–21h encore ouvert à 18h30) | `tests/pytest/test_benevolat_inscription.py` |
| Inscription **au-delà** de `nombre_souhaite` acceptée, compteur `3/2` (D7) | idem |
| Double clic : une seule inscription, un seul email | idem |
| Retrait : avant le délai → pas de mail ; après le délai → retrait fait + mail à l'équipe (P10) ; besoin passé → refusé ; pas l'inscription d'un autre | idem |
| Rappel : besoin de demain (fuseau du lieu) → un mail ; relancer la tâche → aucun second mail ; besoin d'après-demain → rien ; tous les lieux parcourus, pas `public` | `tests/pytest/test_benevolat_rappel.py` |
| Désistement : GET ne supprime rien ; POST (avec CSRF) supprime ; après le délai → mail à l'équipe ; jeton faux, besoin passé ou inscription déjà supprimée → page « Ce lien ne marche plus » | idem |
| Les mails de rappel et de confirmation contiennent un lien de désistement signé, et ce lien marche | idem |
| Aucun `LigneArticle` créé par une inscription | idem |
| Prénom `None` ou `""` → « Bénévole », jamais d'email dans le HTML | idem |
| Prénom manquant : 1er POST → modale, aucune inscription ; 2e POST avec `prenom` → `first_name` enregistré + inscription ; `prenom` vide ou blanc → 422 dans la modale | idem |
| Nom manquant (prénom présent) : la modale n'affiche que « Nom » ; POST avec `nom` → `last_name` enregistré + inscription ; un `prenom` envoyé ne réécrit pas le prénom existant | idem |
| Compteur de l'en-tête : « places couvertes », « en renfort », « créneaux encore vides » justes, rafraîchis en hors bande après « Je viens » (D21) | idem |
| Anonyme sur un besoin couvert : badge « Couvert » + « Me connecter pour venir » (D22) | idem |
| Inscrire quelqu'un : non-admin → 403 sur les trois vues ; recherche par prénom, nom, email ; moins de 2 caractères → aucun résultat ; un compte d'un **autre lieu** ne sort jamais, même par email exact ; pk forcé vers ce compte → refusé ; « déjà inscrite » sans bouton | `tests/pytest/test_benevolat_equipe.py` |
| Inscrire quelqu'un : personne trouvée → inscription avec `inscrit_par` ; planning réservé aux adhérent·es → acceptée quand même ; email inconnu → compte créé et rattaché au lieu, sans mail de connexion ; email connu → prénom et nom existants **pas** réécrits ; mail de confirmation « L'équipe t'a inscrit·e » | idem |
| API : clé sans `volunteering` → 403 sur les quatre routes ; CRUD des tâches, plannings (id **et** slug), besoins, inscriptions ; tâche utilisée → 409 | `tests/pytest/test_benevolat_api.py` |
| API : `startDate` date seule → journée ; heure sans décalage = heure locale ; avec décalage → convertie ; `endDate` à minuit → lendemain ; `endDate` à J+2 → 400 ; besoin un jour fermé → `fermeture` rempli | idem |
| API : `repeat` en `dryRun` n'écrit rien ; sans `dryRun` crée tout et renvoie les trois listes ; mêmes résultats que l'admin | idem |
| API : inscription → 201, rejouée → 200 sans second mail ; compte sans nom et `familyName` absent → 400 ; besoin passé → 400 ; DELETE sans mail ; isolation : la clé d'un lieu ne voit pas les plannings d'un autre | idem |
| Modale : s'ouvre au clic, le focus va sur le champ, « Annuler » ne crée rien | `tests/e2e/test_benevolat_flow.py` |
| Admin : « Inscrire quelqu'un » → taper 2 lettres → résultats → « Inscrire » → la case montre le prénom, sans recharger | idem |
| Planning au slug `book` : servi par la vue bénévolat, pas par `BookingViewSet`. Planning au slug `lettre` : sa page s'affiche (GET), et le POST de §5.8 marche | `tests/pytest/test_benevolat_inscription.py` |
| Balise `plannings_benevoles_a_venir` : plannings publiés avec besoin à venir seulement, tri, `nombre_max`, liste vide en schéma `public` ; rendu de la carte (nom, période, places libres) | `tests/pytest/test_benevolat_bloc_accueil.py` |
| Lettre : connecté·e → `send_to_ghost_email` appelée avec le nom du compte et l'étiquette « Bénévolat » ; anonyme → même appel, nom vide ; email invalide → 422 ; Ghost non configuré → bloc absent | `tests/pytest/test_benevolat_lettre.py` |
| `send_to_ghost_email` sans `etiquettes_en_plus` : mêmes étiquettes qu'avant (non-régression) | idem |
| `send_to_ghost_email` avec `etiquettes_en_plus` : membre nouveau → `labels` contient « Bénévolat » ; membre existant sans l'étiquette → un `PUT` ; membre qui l'a déjà → aucun `PUT` (Ghost mocké) | idem |
| `calculer_repetitions` : jours, semaines, écart de 2, jours fermés sautés (avec leur `label`, ou le repli si vide), doublons ignorés, inscriptions non copiées | `booking/tests/test_benevolat_repetition.py` (fonction pure) + un test admin (aperçu puis confirmation) |
| Besoin saisi à la main un jour fermé : enregistré, colonne « Fermé : … » affichée dans l'inline | test admin |
| Clic « Je viens » → la case change sans recharger, l'en-tête du jour change de couleur, toast ; « Me retirer » la rend libre | `tests/e2e/test_benevolat_flow.py` |
| Refus (planning réservé) → la case 422 est bien swappée (listener §5.3) | idem |
| Vue mobile (375 px) : liste par jour, pas de défilement horizontal de la page | idem |

Chaque test vu **échouer** sur une mutation volontaire avant d'être livré.

## 9. Découpage proposé

| Chantier | Contenu |
|---|---|
| 1 | Modèles + migration + admin (tâches, plannings avec calendrier, besoins inline, inscriptions) |
| 2 | Page publique (grille, mobile, couleurs des jours, compteur D21), inscription avec modale prénom et nom, retrait, toasts, email de confirmation (sans le lien de désistement) |
| 3 | « Mes créneaux » + bloc CMS « Coups de main » sur l'accueil (§5.1) + bloc lettre d'information (§5.8) + inscription par l'équipe (§5.10) |
| 4 | Action admin « Répéter des besoins » (§5.7) |
| 5 | Rappel de la veille + lien « Je ne peux plus venir », ajouté aux deux mails (§5.9) |
| 6 | API v2 (§6 bis) + droit de clé + migration `BaseBillet` + OpenAPI, GUIDELINES et skill `tibillet-api`. Après les chantiers 2 (mail de confirmation) et 4 (`calculer_repetitions`) |

Chaque chantier : son fichier `CHANGELOG/YYYY-MM-DD-slug.md`.

## 10. Questions ouvertes

Aucune. Questions tranchées le 2026-09-23 (D11 à D19), propositions P1 à P10 validées le
2026-09-24, D18 revue et D21 à D24 ajoutées le 2026-10-12.

Spec liée : `TODO/USERS-etiquettes.md` (D12), écrite le 2026-09-24, non commencée.

**Les ajouts du 2026-10-12 (nom, §5.10, §6 bis) n'ont pas encore eu de relecture Fable.**
