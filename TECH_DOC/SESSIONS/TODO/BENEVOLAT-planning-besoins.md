# BÉNÉVOLAT — Planning des besoins en bénévoles (façon Framadate)

> **Status :** spec du 2026-09-23. **Chantier 1 fait le 2026-10-13** (modèles, migration, admin :
> `CHANGELOG/2026-10-13-benevolat-chantier-1-modeles-admin.md`). **Chantier 2 fait le 2026-10-16**
> (page publique, inscription, retrait : `CHANGELOG/2026-10-16-benevolat-chantier-2-page-publique.md`).
> **Chantier 3 fait le 2026-10-16**, avec les corrections d'une relecture Opus des chantiers 1 et 2
> (`CHANGELOG/2026-10-16-benevolat-chantier-3-compte-accueil-lettre.md`). **Chantier 4 fait le 2026-10-16**
> (« Répéter des besoins » : `CHANGELOG/2026-10-16-benevolat-chantier-4-repeter.md`), puis le module « Bénévolat »
> du tableau de bord (P7 revue). **Chantier 5 fait le 2026-10-16** (rappel, lien de désistement, inscription
> par l'équipe : `CHANGELOG/2026-10-16-benevolat-chantier-5-rappel-equipe.md`). **Chantier 6 fait le 2026-10-16**
> (API v2 allégée : `CHANGELOG/2026-10-16-benevolat-chantier-6-api-v2.md`). **Les six chantiers sont faits.**
> **Évolutions décidées le 2026-10-17 (D28 à D34, §11) : chantiers 7 (pagination par semaine) et 8
> (semaine type, page « Besoins », volumes). Relues par Fable le 2026-10-17, corrections intégrées.**
> **Chantier 7 fait le 2026-10-17** (une semaine à la fois :
> `CHANGELOG/2026-10-17-benevolat-chantier-7-pagination-semaine.md`). **Chantier 8 fait le 2026-10-17**
> (semaine type, page « Besoins », index : `CHANGELOG/2026-10-17-benevolat-chantier-8-semaine-type.md`).
> Relue le même jour par un agent Fable (exactitude face au code, inventaire, sur-ingénierie).
> Ses corrections sont intégrées. Les décisions D6 à D19 et P1 à P10 ont eu une **seconde relecture
> Fable** le 2026-09-24 (exactitude, pièges techniques, contradictions) ; ses corrections sont intégrées.
> Les ajouts du 2026-10-12 ont eu une **troisième relecture Fable** le 2026-10-13 ; ses corrections
> sont intégrées (D25 à D27, ancrages remis à jour).
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
| D24 | API v2 | **API v2 allégée** (revue le 2026-10-16) : les quatre modèles et l'inscription d'une personne. Ni répétition (l'admin le fait), ni filtres email/dates des inscriptions, ni écriture du calendrier de fermetures et des adhésions requises (lecture seule) (§6 bis). (2026-10-12, allégée le 2026-10-16) |
| D25 | Identifiant | **Clé primaire `uuid`** sur les quatre modèles, comme `Event` et `Product`. C'est l'`identifier` de l'API v2 (`api_v2/GUIDELINES.md` : `identifier = uuid` partout), et c'est ce que signe le lien de désistement : un uuid ne désigne rien dans un autre lieu, alors qu'un entier y désignerait l'inscription de quelqu'un d'autre (§5.9). (relecture 2026-10-13) |
| D26 | Fenêtre | **`<dialog>` natif**, comme la maquette, pas une modale Bootstrap : vider une modale Bootstrap ouverte laisse son voile (`.modal-backdrop`) sur la page ; le `::backdrop` d'un `<dialog>` part avec lui. (relecture 2026-10-13) |
| D27 | Inscription par l'équipe | **Au chantier 5**, avec le lien de désistement : un compte créé par l'équipe est inactif (`get_or_create_user`, `is_active = set_active`), sans mot de passe. Sans lien signé dans le mail, la personne n'a aucun moyen de se retirer. (relecture 2026-10-13) |
| D28 | Pagination | **La page publique montre une semaine à la fois** (lundi → dimanche), avec « semaine précédente / suivante » (§11.1). Le compteur de l'en-tête reste celui du planning entier. (2026-10-17) |
| D29 | Semaine type | **Option « B »** : un planning est « Ponctuel » (besoins datés, comme aujourd'hui) ou « Chaque semaine » (une **semaine type** de lignes « jour + tâche + heures + nombre »). En mode hebdomadaire, le système **crée les besoins réels** sur un horizon de N semaines, à l'enregistrement puis chaque nuit (§11.2). Option « A » écartée (besoins calculés à la volée, comme `booking`) : exceptions, inscriptions sans point d'ancrage stable, et tout l'existant (URL, lien signé, API, rappel) repose sur un besoin réel. (2026-10-17) |
| D30 | Modifier la semaine type | **Ne touche que les besoins futurs sans inscrit qui suivent encore leur ligne.** Les besoins qui ont des inscrits ne bougent jamais ; l'admin le dit (« N besoins avec des inscrits n'ont pas été modifiés »). Un besoin supprimé à la main n'est jamais recréé. **Un besoin modifié à la main devient une exception** : il est détaché de sa ligne et ne la suit plus (relecture Fable, 2026-10-17) (§11.2). (2026-10-17) |
| D31 | Où vit la semaine type | **Dans la fiche du planning** (lignes), pas un objet séparé partagé comme `WeeklyOpening` : une semaine type sert un seul planning. Les besoins sortent de la fiche vers une page d'admin « Besoins ». (2026-10-17) |
| D32 | Nom | **« Semaine type »** (`LigneDeSemaineType`), pas « calendrier » : dans `booking`, `Calendar` désigne les fermetures, déjà reliées au planning. (2026-10-17) |
| D33 | Volumes et archivage | **Rien n'est supprimé** : le passé est caché par les filtres (« À venir » par défaut), un index `(planning, date)` sert toutes les requêtes. Ordre de grandeur : ~500 besoins par an et par planning hebdomadaire, dans le schéma du lieu (§11.3). (2026-10-17) |
| D34 | « Répéter » | **Gardé pour les plannings ponctuels**, masqué pour les plannings hebdomadaires (la semaine type le remplace). (2026-10-17) |

### 2.2 Proposées par cette spec, validées par le mainteneur (2026-09-24)

| # | Sujet | Proposition | Pourquoi |
|---|---|---|---|
| P1 | Concurrence | **Aucun verrou.** Pas de plafond (D7), donc pas de course sur une « dernière place ». | Ni `select_for_update`, ni isolation SERIALIZABLE : il n'y a rien à protéger. |
| P2 | Double clic | `InscriptionBenevole.objects.get_or_create(besoin=…, user=…)` + `UniqueConstraint(besoin, user)`. | `get_or_create` rattrape lui-même l'`IntegrityError` d'un double clic simultané et relit la ligne (§7). |
| P3 | Se retirer | **Suppression** de la ligne `InscriptionBenevole`. Pas de statut. Supprimer un besoin en admin supprime ses inscriptions (`CASCADE`), sans prévenir (D17). | Le plus simple. Pas de compta ni de remboursement derrière. |
| P4 | Un clic, pas de formulaire | « Je viens » inscrit directement (comme Framadate), toast texte seul. | Pas d'écran de confirmation. Pour se défaire : « Me retirer », déjà présent dans la case. |
| P5 | Prénom affiché | `user.first_name`. Grâce à D18, presque toujours rempli. Repli si vide quand même (compte modifié après coup) : `None` **ou** `""` → « Bénévole » (`first_name` est `null=True`, `AuthBillet/models.py:134`). Jamais l'email, jamais le nom de famille. | D2 rend le prénom public : on n'expose rien de plus. |
| P6 | Besoins passés | Un besoin est passé quand sa **fin** est passée (`fin() <= now`). Masqués côté public. Un planning dont tous les besoins sont passés disparaît du bloc d'accueil. | La page reste courte. L'admin garde tout. Un besoin 18h–21h reste visible jusqu'à 21h. |
| P7 | Module | **Revu le 2026-10-16 par le mainteneur : un module à part, `Configuration.module_benevolat`** (défaut `False`, migration `BaseBillet/0231`), avec sa carte « Bénévolat » dans le tableau de bord (groupe « Espace en ligne ») et son bloc dans la barre latérale (plannings, tâches, inscriptions). Il conditionne aussi le raccourci « Mes créneaux » de « Mon compte » et l'entrée « Bénévolat » du menu du site (`main_nav`, `BaseBillet/views.py`), qui mène à `/booking/benevolat/` : la liste des plannings à venir, avec les cartes du bloc d'accueil (ajout du 2026-10-17). Comme `/booking/`, les vues publiques ne vérifient pas le module : seuls les menus sont conditionnés. | Le mainteneur veut l'allumer et le tester comme les autres modules. |
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
| L'onglet « Mon compte » : sur le modèle de `MyAccount.my_bookings` (`BaseBillet/views.py:1639`) | |
| L'email en tâche Celery : sur le modèle de `booking/tasks.py` | |

## 4. Modèle de données (`booking/models.py`)

```
PlanningBenevole ──< BesoinBenevole >── TacheBenevole
   │   │                  │
   │   │                  └──< InscriptionBenevole >── TibilletUser
   │   └──> Calendar (booking, existant, facultatif) ──< ClosedPeriod
   └──< >── Product (adhésions requises, facultatif)
```

**Clé primaire (D25)** : les quatre modèles ont
`uuid = UUIDField(primary_key=True, default=uuid4, editable=False)`. Piège connu : avec un
défaut, `self.pk` est rempli avant la première sauvegarde ; tester `self._state.adding`, jamais
`if not self.pk`. Tous les champs ont un `verbose_name` (`tests/pytest/test_admin_verbose_name.py`).

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
| `slug` | `SlugField(unique)` | URL publique. `clean()` refuse `besoin` et `desistement` : ce sont des segments des routes de §6 |
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
| `heure_fin` | `TimeField(null, blank)` | Si `heure_fin < heure_debut` : se termine le lendemain (21:00 → 00:00). `heure_fin == heure_debut` est refusé par `clean()` (24 h : presque toujours une faute de frappe ; pour la journée, heures vides) |
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

**Affichage des heures.** `TIME_ZONE` vaut `UTC` par défaut (`TiBillet/settings.py:593`, lu dans l'environnement) et le projet
n'active jamais le fuseau du lieu (`timezone.activate`). Un gabarit qui rendrait `debut()` ou
`fin()` avec `|date` afficherait l'heure UTC. Règle : **les gabarits et les mails affichent
`date`, `heure_debut`, `heure_fin`** (champs sans fuseau, saisis en heure locale).
`debut()` et `fin()` ne servent qu'aux comparaisons.

### `InscriptionBenevole`

| Champ | Type | Note |
|---|---|---|
| `besoin` | FK `BesoinBenevole`, `CASCADE`, `related_name="inscriptions"` | |
| `user` | FK `AUTH_USER_MODEL`, `PROTECT` | |
| `created_at` | `DateTimeField(auto_now_add)` | Ordre d'affichage des prénoms : les premiers inscrits d'abord (« Toi » toujours en tête) |
| `rappel_envoye_le` | `DateTimeField(null, blank)` | Rempli quand le rappel de la veille part. Empêche un second envoi (§5.9). Vidé quand le besoin change de jour ou d'heures (`BesoinBenevole.save`) : la nouvelle date a son rappel |
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
    `pages/{V2,classic}/partials/bloc_liste.html`, qui inclut un gabarit commun aux skins
    (`booking/benevolat/partials/cartes_accueil.html`, styles `bv-` de `benevolat.css`, chargés
    par le gabarit lui-même).
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
  `aria-live="polite"` et il est rafraîchi avec toute la zone du planning (§5.3).
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
| Déjà inscrite, après le délai | « Tu y es » + « Je ne peux plus venir » (l'équipe sera prévenue, P10 : écrit en clair sous le bouton, et le clic demande confirmation) |

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

1. `hx-post` sur `/booking/benevolat/besoin/<pk>/inscrire/`, `hx-target` = **la zone du
   planning** (`#benevolat-planning` : compteur, grille, jours mobiles), `hx-swap="outerHTML"`.
   **Pourquoi la zone et pas la case** (décidé au chantier 2) : chaque besoin est affiché deux
   fois (grille desktop et liste mobile), et l'en-tête du jour, la puce du jour et le compteur
   changent aussi. Re-rendre la zone garde tout juste en une réponse. Le site charge
   **htmx 1.9.12**, qui gère mal un `<th>` en hors bande. La position du défilement horizontal
   de la grille est gardée par quelques lignes de JS (`planning.html`).
2. Vérifications (serializer DRF) : connecté·e, planning publié, besoin pas passé,
   droit d'accès (D3, contrôle d'adhésion recopié de `booking_engine.py:553-568`, **sans les
   adhésions annulées** `CANCELED` / `ADMIN_CANCELED`, même si leur date de fin est à venir).
   Ces contrôles demandent la base : ils sont dans la vue, le serializer ne valide que la saisie.
   **Pas** de contrôle du nombre d'inscrits (D7).
3. **Prénom ou nom manquant (D18)** : si `user.first_name` **ou** `user.last_name` est vide
   (`None` ou blanc), pas d'inscription tout de suite. La réponse ouvre une fenêtre
   (`<dialog>` natif, D26, comme la maquette `BENEVOLAT-maquette.html:491`) :

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

   **Côté htmx : `HX-Retarget`** (déjà utilisé dans `laboutik/views.py`). La réponse est le
   contenu de la fenêtre, avec `HX-Retarget: #benevolat-modale-contenu`,
   `HX-Reswap: innerHTML` et `HX-Trigger-After-Settle: ouvrirModaleBenevolat` ; trois lignes de
   JS appellent `showModal()`, qui met lui-même le curseur dans le premier champ. Le
   formulaire porte un champ caché `fenetre_nom=1`. Après l'envoi, la réponse remplace la
   zone et porte `HX-Trigger-After-Settle: fermerModaleBenevolat` (`close()`). Une erreur de
   saisie renvoie la fenêtre en 422, avec ses messages. La fenêtre n'est **jamais vidée
   pendant qu'elle est ouverte** : on la ferme, puis le prochain contenu la remplace.
   L'utilisateur est en `SHARED_APPS` : ce prénom et ce nom sont aussi ceux des autres lieux.
   C'est voulu, c'est le même compte.
4. `get_or_create` de l'`InscriptionBenevole` (§7).
5. Réponse : **la zone du planning** + toast texte (« C'est noté… ») via le
   toast générique existant `appToast` (écouteur dans
   `BaseBillet/templates/htmx/components/panier_scripts.html:84`, « utilisable par n'importe
   quelle vue », inclus par les trois shells), pas un nouvel événement. L'en-tête du jour et le
   compteur avec sa jauge (D21) font partie de la zone.
6. Email de confirmation (Celery, après le commit : `transaction.on_commit`) : date, plage,
   tâche, consignes, lien vers le planning. Le lien « Mes créneaux » remplace ou complète ce
   lien au chantier 3.
   Le lien « Je ne peux plus venir » (§5.9) y est ajouté au chantier 5.

Erreurs (pas le droit, besoin passé) : la zone recalculée en **422**, avec un toast d'erreur et le
message. **Aucun shell ne swappe les 422** (`pages/templates/pages/<skin>/shell.html`,
écouteur `htmx:beforeSwap` ≈ l.172-182 : 404/500 seulement, vers `body`) : `planning.html`
reprend le listener `htmx:beforeOnLoad` posé page par page dans
`booking/templates/booking/views/resource.html:804-812`.

### 5.4 Se retirer

`hx-post` sur `/booking/benevolat/besoin/<pk>/retirer/`. Avant `debut() - delai` : retrait
silencieux. Après : le retrait marche aussi, et un mail part à l'équipe (P10, même mail
qu'en §5.9) **seulement si l'inscription datait d'avant le délai** (`created_at < debut() - délai`) :
l'équipe ne comptait pas sur un renfort de dernière minute, et ça empêche une boucle de mails
« Je viens » / « Je ne peux plus venir ». Refusé seulement si le besoin est passé (`est_passe()`).
Suppression de l'inscription (P3). Depuis la grille ou depuis « Mes créneaux ». Même
réponse qu'en §5.3 (la zone du planning + toast).

### 5.5 Mon compte → « Mes créneaux bénévoles »

Nouvelle action `MyAccount.my_volunteering` sur le modèle de `my_bookings`
(`BaseBillet/views.py:1639`). Liste des inscriptions à venir, triées par date, avec
« Me retirer » (avant le délai) ou « Je ne peux plus venir » (après : l'équipe est prévenue, P10).
Seulement les plannings publiés. Le bouton poste sur la vue `retirer` avec `depuis=mes_creneaux` :
la réponse est vide et remplace la ligne (elle disparaît), avec le toast. La liste est un gabarit
commun aux skins (`booking/benevolat/partials/mes_creneaux.html`).

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
  (≈ l.892-942), **plus** les deux dictionnaires par modèle à compléter pour les trois
  nouveaux modèles : aide (≈ l.1460-1465, ex. `"booking.weeklyopening"`) et verbe
  (≈ l.1532-1537, `"gerer"` / `"configurer"`).

### 5.7 Admin : répéter des besoins (le « modèle »)

**Le problème :** chaque semaine, le bar a besoin des mêmes créneaux (ven. 18h–21h et
21h–minuit, sam. idem). On ne veut pas les ressaisir.

**Le principe :** on saisit une fois une **période modèle** (un jour, ou une semaine), puis
on la répète. Pas de nouveau modèle de données : le modèle, ce sont des besoins déjà saisis.

**Le formulaire** (bouton « Répéter des besoins » en haut de la fiche planning,
`actions_detail` Unfold) :

| Champ | Exemple | Règle |
|---|---|---|
| Modèle : du … au … | 2 oct. → 3 oct. | Les besoins du planning dans cette période servent de modèle. Pré-rempli : les 7 premiers jours du planning. 31 jours au plus |
| Répéter tous les | `1` | Entier de 1 à 52 |
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
(`Administration/admin_tenant.py:585`), `scanner` (≈ l.3569), `inventaire.py:302`,
`laboutik.py:1175`, `render(request, "admin/module_page.html")` (`dashboard.py:1503`).
Le bouton `actions_detail` (précédent l.361) redirige vers cette URL. Formulaire :
un `forms.Form` admin (permis dans l'admin, précédent `ResourceAddAdmin(ModelForm)`,
`Administration/admin/resources.py:136`). Gabarit `admin/booking/planning_repeter.html`
en styles inline (règle Unfold), sur le modèle de `admin/module_page.html`. Le calcul des dates
est une **fonction pure**
`calculer_repetitions(besoins_modele, ecart_en_jours, nombre_de_fois, periodes_fermees, besoins_existants)`
dans `booking/benevolat.py`, testable sans base : elle renvoie les trois listes de l'aperçu.
`besoins_existants` est un ensemble de clés `cle_d_un_besoin(tache_id, date, heure_debut, heure_fin)` ;
les fermetures passent par `periode_fermee_qui_couvre` et `libelle_d_une_fermeture`
(`booking/models.py`, sans base). Fait au chantier 4 : vue `PlanningBenevoleAdmin.repeter`
(`<object_id>/repeter/`), bouton `actions_detail` « Répéter des besoins » ; la confirmation
recalcule l'aperçu avant de créer (la base a pu changer).


### 5.8 Se tenir informé·e : la lettre d'information (D10)

**Le besoin :** on n'est pas dispo sur ce planning, mais on veut savoir quand l'équipe
aura de nouveau besoin de monde.

**Le bloc** (sous la grille, maquette : onglet « Page publique ») :

> **Pas dispo cette fois ?**
> Reçois la lettre d'information du lieu : les prochains coups de main y sont annoncés.
> `[ ton@email.fr ]` `[ Je m'inscris à la lettre d'information ]`

- Connecté·e : le champ est pré-rempli avec l'email du compte (modifiable).
- Affiché **seulement si le Ghost du lieu est configuré** : `bool(ghost_url) and
  bool(ghost_key)`. `ghost_key` est chiffrée (`get_api_key()`) : on teste sa présence, on ne
  la déchiffre pas. Attention : la variable existante `newsletter_active`
  (`BaseBillet/views.py` ≈ l.4436) est vraie aussi avec Brevo seul, alors que
  `send_to_ghost_email` ne parle qu'à Ghost. Ne pas la réutiliser telle quelle.

**Le clic** : `hx-post` sur `/booking/benevolat/<slug>/lettre/` (jeton CSRF vérifié par la vue, `jeton_csrf_valide` : POST anonyme), `hx-target` = le bloc,
`hx-swap="outerHTML"`. Serializer : un `EmailField`. Un seul chemin (D13), le même que la
case « newsletter » des formulaires (`BaseBillet/views.py` ≈ l.712-727) :
`send_to_ghost_email.delay(email, nom, etiquettes_en_plus=["Bénévolat"])`. Le nom est
celui du compte si la personne est connectée, vide sinon.

Message à la place du bloc : « C'est noté : ton@email.fr recevra la lettre d'information. »

**L'étiquette « Bénévolat ».** On ajoute un paramètre facultatif à la tâche existante :
`send_to_ghost_email(email, name=None, etiquettes_en_plus=None)`. Les étiquettes actuelles
(`"TiBillet"`, `"import <date>"`, `BaseBillet/tasks.py` ≈ l.1922 ; la tâche est l.1867) sont gardées, et
`"Bénévolat"` s'y ajoute. L'équipe peut alors, dans Ghost, envoyer un numéro aux seuls
membres étiquetés « Bénévolat ». Les autres appels de la tâche ne changent pas.

**Membre Ghost déjà existant.** Aujourd'hui la tâche ne pose les étiquettes qu'à la
**création** (`BaseBillet/tasks.py` ≈ l.1922) ; si l'email est déjà membre, elle
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
  `membership_renewal_reminder` (`BaseBillet/tasks.py` ≈ l.2000) : boucle sur les lieux avec
  `tenant_context`, en excluant `public` **et** les emplacements vides
  (`.exclude(categorie=Client.WAITING_CONFIG)`, comme elle).
- Programmée dans `TiBillet/celery.py` avec les autres (`add_periodic_task` +
  `crontab`), par un wrapper `@app.task` local comme `cron_purge_stale_onboard_drafts`
  (`celery.py` ≈ l.163-179 : import local + appel direct). Heure
  proposée : **8h UTC** (le matin, pas en pleine nuit).
- « Demain » = `date` du besoin égale à la date de demain **dans le fuseau du lieu**
  (`Configuration.get_solo().get_tzinfo()`), pas en UTC.
- Un besoin « Journée » a sa propre phrase : « Demain : tu tiens le bar. Merci ! » (pas de plage).
- Seulement les inscriptions dont `rappel_envoye_le` est vide ; le champ est rempli juste
  après l'envoi. Relancer la tâche n'envoie donc rien deux fois.

**Le lien « Je ne peux plus venir ».** La personne peut ne pas être connectée sur son
téléphone. Le lien porte donc sa preuve :

1. Lien signé : `/booking/benevolat/desistement/<jeton>/`. Le jeton est
   `signing.dumps(str(inscription.uuid), salt="benevolat-desistement")`, relu par
   `signing.loads(...)`. **Toujours l'uuid, jamais un entier (D25)** : la `SECRET_KEY` est
   commune à tous les lieux ; un entier signé, rejoué sur un autre lieu, y désignerait
   l'inscription de quelqu'un d'autre. Un uuid n'y désigne rien. **Pas de durée de validité dans le jeton** : un `max_age` se donne
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
5. Jeton invalide, expiré, d'un autre lieu, ou inscription déjà supprimée : page « Ce lien ne marche plus.
   Tes créneaux sont dans Mon compte. » (pas d'erreur 500).

**Le même lien sert dans le mail de confirmation** (§5.3, étape 6), ajouté au chantier 5 :
un seul mécanisme pour se retirer depuis un mail. La page de confirmation est un
formulaire HTML classique : `{% csrf_token %}` obligatoire. **Piège** : les vues DRF sont
exemptées du CSRF, et `SessionAuthentication` ne le revérifie que pour une personne connectée.
Le POST anonyme du désistement le vérifie donc lui-même (`jeton_csrf_valide`, le `CSRFCheck` de
DRF). Le retrait et l'alerte à l'équipe passent par une seule fonction,
`retirer_une_inscription` (`booking/benevolat.py`), partagée avec « Me retirer ».

### 5.10 Inscrire quelqu'un à sa place (D23)

**Le besoin :** une personne s'engage au comptoir ou au téléphone, mais ne va pas sur le
site. L'équipe l'inscrit elle-même, pour que la grille reste juste.

**Quand :** au chantier 5 (D27), avec le lien de désistement signé.

**Qui :** un·e admin du lieu, avec la règle de l'admin du projet :
`TenantAdminPermissionWithRequest(request)` (superuser, ou admin du lieu actif et humain). Le lien
n'est affiché qu'à elles et eux, **et** chaque vue revérifie le droit côté serveur (403
sinon) : cacher un bouton ne protège rien.

**Le parcours** (tout dans la fenêtre `#benevolat-modale` de §5.3) :

1. Lien « Inscrire quelqu'un » sur un besoin à venir → `hx-get` de
   `/booking/benevolat/besoin/<pk>/inscrire-une-personne/`, qui renvoie la fenêtre en hors
   bande + `HX-Trigger: ouvrirModaleBenevolat` (même mécanisme que §5.3, pas un second).
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
   - chaque résultat affiche « Prénom Nom · email » et un bouton « Inscrire », qui demande
     confirmation (`hx-confirm`, nom et email) : le clic envoie un mail à un tiers. Dans la
     fenêtre (`<dialog>`, top layer), la confirmation SweetAlert du shell V2 serait dessinée
     dessous : la fenêtre arrête `htmx:confirm`, et htmx utilise la boîte native. Une personne
     déjà inscrite sur ce besoin affiche « déjà inscrite » sans bouton.
3. **Inscrire une personne trouvée** : `hx-post` sur
   `/booking/benevolat/besoin/<pk>/inscrire-une-personne/` avec `user` (son pk).
   Le serializer **revérifie** que ce pk est dans `HumanUser.objects` : un pk forcé vers le
   compte d'un autre lieu est refusé (même règle que la carte NFC de
   `Administration/admin/laboutik.py:952`).
4. **Personne introuvable** : sous les résultats, « Pas dans la liste ? » ouvre trois
   champs : email, prénom, nom (les trois obligatoires, D18). `hx-post` sur la même URL.
   Le serveur appelle `get_or_create_user(email, send_mail=False)` (`AuthBillet/utils.py:96`),
   qui rattache le compte au lieu (`client_achat`). Elle renvoie **`None`** si l'email est
   marqué en erreur (`user.email_error`, `AuthBillet/utils.py:143-145`) : 422 dans la
   fenêtre, « Cet email ne fonctionne pas » (précédent : `BaseBillet/views.py` ≈ l.715-720).
   Prénom et nom ne sont écrits **que s'ils
   sont vides** dans le compte : si l'email existe déjà, on ne réécrit pas le nom d'une
   personne qui l'a choisi elle-même (le compte est partagé entre lieux).
   Un compte créé ici est **inactif** et sans mot de passe : c'est le lien de désistement
   signé du mail (étape 7) qui lui permet de se retirer.
   **Limite assumée**, comme D13 : un·e admin peut rattacher n'importe quel email au lieu
   et lui faire envoyer le mail de confirmation. Conséquence assumée (relecture du
   2026-10-16) : si ce compte existe déjà dans un autre lieu, l'équipe voit le prénom et le
   nom qu'il porte (toast, recherche, API) — comme pour toute personne rattachée au lieu.
5. **L'inscription** : `get_or_create(besoin=…, user=…, defaults={"inscrit_par": request.user})`
   (§7). Mêmes vérifications que §5.3 (planning publié, besoin pas passé), **sauf le
   contrôle d'adhésion (D3)** : l'équipe décide qui elle inscrit. Pas de modale prénom non plus :
   une personne trouvée sans prénom s'affiche « Bénévole » (P5).
6. **Réponse** : comme §5.3 (la zone du planning), la fenêtre fermée
   (`fermerModaleBenevolat`), toast « Camille Martin est inscrite ».
7. **Mail à la personne** : le mail de confirmation de §5.3, avec une première phrase
   différente : « L'équipe de <lieu> t'a inscrit·e. Si ce n'est pas bon, dis-le en un
   clic : » suivi du lien « Je ne peux plus venir » (§5.9). La tâche Celery reçoit un
   paramètre `par_l_equipe=True` : c'est l'appelant qui choisit le texte (cette vue et
   l'API, §6 bis), pas le champ `inscrit_par`, qui peut être vide (clé API sans compte).

**Retirer quelqu'un** : depuis l'admin Unfold (`InscriptionBenevoleAdmin`, suppression),
sans mail (D17). Pas de bouton « retirer » pour l'équipe dans la grille en V1.

## 6. Vues, URLs, gabarits

`booking/views_benevolat.py` — `BenevolatViewSet(viewsets.ViewSet)`, avec
`permission_classes = [AllowAny]` et un **contrôle explicite dans chaque action** : `lettre`
et `desistement` acceptent un anonyme (D13, §5.9) ; `inscrire` et `retirer` exigent une
session ; `inscrire_une_personne` et `chercher_une_personne` exigent un·e admin du lieu (403
sinon). Pas l'`IsAuthenticatedOrReadOnly` de `BookingViewSet` (`booking/views.py:54`), qui
bloquerait les POST anonymes.

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
produirait `benevolat/<pk>/inscrire/`, pas `benevolat/besoin/<pk>/…`). Les besoins sont
désignés par leur uuid (D25, `<uuid:pk>`).
**Collision possible** : `desistement/<jeton>/` et `<slug>/lettre/` ont le même nombre de
segments. Deux protections : `<slug>/lettre/` passe **avant** `desistement/<jeton>/` (un
jeton signé contient toujours `:`, il ne peut pas valoir `lettre`), et `clean()` du planning
refuse les slugs `besoin` et `desistement` (§4). Un planning peut s'appeler « lettre ».

```python
urlpatterns = [
    path("benevolat/besoin/<uuid:pk>/inscrire/", BenevolatViewSet.as_view({"post": "inscrire"}), name="benevolat-inscrire"),
    path("benevolat/besoin/<uuid:pk>/retirer/", BenevolatViewSet.as_view({"post": "retirer"}), name="benevolat-retirer"),
    path("benevolat/besoin/<uuid:pk>/inscrire-une-personne/", BenevolatViewSet.as_view({"get": "inscrire_une_personne", "post": "inscrire_une_personne"}), name="benevolat-inscrire-une-personne"),
    path("benevolat/besoin/<uuid:pk>/chercher-une-personne/", BenevolatViewSet.as_view({"get": "chercher_une_personne"}), name="benevolat-chercher-une-personne"),
    path("benevolat/<slug:slug>/lettre/", BenevolatViewSet.as_view({"post": "lettre"}), name="benevolat-lettre"),
    path("benevolat/desistement/<str:jeton>/", BenevolatViewSet.as_view({"get": "desistement", "post": "desistement"}), name="benevolat-desistement"),
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
`booking/booking_base.html`), `partials/zone.html` (compteur + grille + jours mobiles, rendue
seule par chaque action htmx), `partials/besoin.html` (une case, incluse deux fois : grille et
mobile, d'où le suffixe `mobile-` des `data-testid` côté mobile), `partials/grille.html`,
`partials/jours_mobile.html`, `partials/compteur.html` (D21), `partials/fenetre_nom.html` (D18),
`partials/lettre.html`, `partials/inscrire_une_personne.html` (la fenêtre de §5.10),
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
| `/api/v2/volunteer-plannings/` | `volunteerplanning` | `EventSeries` | list, create, retrieve, PATCH, DELETE |
| `/api/v2/volunteer-needs/` | `volunteerneed` | `Event` (`additionalType: "Volunteering"`) | list, create, retrieve, PATCH, DELETE |
| `/api/v2/volunteer-signups/` | `volunteersignup` | `RsvpAction` | list, create, retrieve, DELETE |

`identifier` = l'uuid (D25), comme partout dans `api_v2/`. Un planning se cherche aussi par son slug
(`/api/v2/volunteer-plannings/bar-octobre/`), comme les pages (uuid **ou** slug).

### Tâche → `DefinedTerm`

```
identifier = uuid
name        = name
description = description
```

DELETE d'une tâche utilisée par un besoin : `PROTECT` lève `ProtectedError` → **409** avec le
message « Cette tâche sert encore à N besoins ».

### Planning → `EventSeries`

```
identifier  = uuid
name        = name
description = description
url         = "/booking/benevolat/<slug>/"
startDate   = date du premier besoin   (lecture seule, absent si aucun besoin)
endDate     = date du dernier besoin   (lecture seule)
subEvent    = [Event besoin, ...]      (retrieve seulement, pas dans la liste)
additionalProperty = PropertyValue[] :
  slug, published, delaiDesinscriptionHeures,
  requiredMembershipPlans  = [uuid de Product adhésion]  (lecture seule ; vide = tout compte connecté, D3)
  closingCalendar          = id du Calendar, ou null    (lecture seule ; D9, Calendar garde sa clé entière)
  placesCouvertes, placesSouhaitees, renforts, creneauxVides  (lecture seule, D21)
```

En entrée (création, PATCH) : `name`, `description`, et dans `additionalProperty` : `slug`,
`published`, `delaiDesinscriptionHeures`. Les adhésions requises et le calendrier de fermetures
se règlent dans l'admin (API allégée, D24). Un slug réservé (`besoin`, `desistement`) → 400.
DELETE : supprime besoins et inscriptions (`CASCADE`), sans mail (D17).

### Besoin → `Event`

```
@type          = "Event"
additionalType = "Volunteering"
identifier     = uuid
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

Liste : filtres `?planning=<uuid>`, `?task=<uuid>`, `?dateFrom=`, `?dateTo=`. Les besoins passés
sont inclus (l'API sert l'équipe, pas le public). Un besoin créé un jour fermé est accepté,
avec `fermeture` rempli dans la réponse (P8). DELETE : supprime ses inscriptions, sans mail
(D17).

### Inscription → `RsvpAction`

```
@type        = "RsvpAction"
identifier   = uuid
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
  "object": {"identifier": "6f1c…-uuid-du-besoin"},
  "agent": {"email": "camille@exemple.org", "givenName": "Camille", "familyName": "Martin"}
}
```

- `get_or_create_user(email, send_mail=False)` : le compte est créé s'il n'existe pas, et
  rattaché au lieu. Elle renvoie `None` pour un email marqué en erreur → 400. `givenName` et `familyName` ne sont écrits que s'ils sont vides dans le
  compte. S'ils manquent dans le compte **et** dans la requête → 400 (D18).
- Planning publié et besoin pas passé, sinon 400. Pas de contrôle d'adhésion (comme §5.10).
- `get_or_create` avec `inscrit_par = ExternalApiKey.user` : **201** si créée, **200** avec
  l'inscription existante si la personne y était déjà (rejouer l'appel est sans danger).
- Mail de confirmation avec `par_l_equipe=True` (§5.10, étape 7), seulement à la création.

Liste : filtres `?need=<uuid>`, `?planning=<uuid>`.
**DELETE** : retire la personne, à tout moment, **sans mail** (l'équipe agit, comme en admin,
D17). Pas de PATCH : une inscription n'a rien de modifiable.

### Documentation à tenir à jour (même commit)

- `api_v2/openapi-schema.yaml` : les quatre routes, les schémas.
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
| Désistement : un jeton émis par un **autre lieu**, rejoué ici → « Ce lien ne marche plus », rien de supprimé (D25) | idem |
| Rappel : un lieu `WAITING_CONFIG` n'est pas parcouru ; besoin « Journée » → phrase sans plage | idem |
| Les mails de rappel et de confirmation contiennent un lien de désistement signé, et ce lien marche | idem |
| Aucun `LigneArticle` créé par une inscription | idem |
| Prénom `None` ou `""` → « Bénévole », jamais d'email dans le HTML | idem |
| Prénom manquant : 1er POST → modale, aucune inscription ; 2e POST avec `prenom` → `first_name` enregistré + inscription ; `prenom` vide ou blanc → 422 dans la modale | idem |
| Nom manquant (prénom présent) : la modale n'affiche que « Nom » ; POST avec `nom` → `last_name` enregistré + inscription ; un `prenom` envoyé ne réécrit pas le prénom existant | idem |
| Compteur de l'en-tête : « places couvertes », « en renfort », « créneaux encore vides » justes, rafraîchis avec la zone après « Je viens » (D21) | idem |
| Anonyme sur un besoin couvert : badge « Couvert » + « Me connecter pour venir » (D22) | idem |
| Inscrire quelqu'un : anonyme et non-admin → 403 sur les trois vues ; recherche par prénom, nom, email ; moins de 2 caractères → aucun résultat ; un compte d'un **autre lieu** ne sort jamais, même par email exact ; pk forcé vers ce compte → refusé ; « déjà inscrite » sans bouton | `tests/pytest/test_benevolat_equipe.py` |
| Inscrire quelqu'un : personne trouvée → inscription avec `inscrit_par` ; planning réservé aux adhérent·es → acceptée quand même ; email inconnu → compte créé et rattaché au lieu, sans mail de connexion ; email connu → prénom et nom existants **pas** réécrits ; email en erreur (`get_or_create_user` → `None`) → 422 ; mail de confirmation « L'équipe t'a inscrit·e » avec le lien de désistement. Compte d'un autre lieu : fabriqué comme dans `tests/pytest/test_carte_cashless_admin.py` | idem |
| API : clé sans `volunteering` → 403 sur les quatre routes ; CRUD des tâches, plannings (id **et** slug), besoins, inscriptions ; tâche utilisée → 409 | `tests/pytest/test_benevolat_api.py` |
| API : `startDate` date seule → journée ; heure sans décalage = heure locale ; avec décalage → convertie ; `endDate` à minuit → lendemain ; `endDate` à J+2 → 400 ; besoin un jour fermé → `fermeture` rempli | idem |
| API : inscription → 201, rejouée → 200 sans second mail ; compte sans nom et `familyName` absent → 400 ; besoin passé → 400 ; DELETE sans mail ; isolation : la clé d'un lieu ne voit pas les plannings d'un autre | idem |
| Modale : s'ouvre au clic, le focus va sur le champ, « Annuler » ne crée rien | `tests/e2e/test_benevolat_flow.py` |
| Admin : « Inscrire quelqu'un » → taper 2 lettres → résultats → « Inscrire » → la case montre le prénom, sans recharger | idem |
| Planning au slug `book` : servi par la vue bénévolat, pas par `BookingViewSet`. Planning au slug `lettre` : sa page s'affiche (GET), et le POST de §5.8 marche. Slugs `besoin` et `desistement` refusés par `clean()` | `tests/pytest/test_benevolat_inscription.py` |
| Balise `plannings_benevoles_a_venir` : plannings publiés avec besoin à venir seulement, tri, `nombre_max`, liste vide en schéma `public` ; rendu de la carte (nom, période, places libres) | `tests/pytest/test_benevolat_chantier3.py` |
| Lettre : connecté·e → `send_to_ghost_email` appelée avec le nom du compte et l'étiquette « Bénévolat » ; anonyme → même appel, nom vide ; email invalide → 422 ; Ghost non configuré → bloc absent | `tests/pytest/test_benevolat_chantier3.py` |
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
| 2 | Page publique (grille, mobile, couleurs des jours, compteur D21), inscription avec fenêtre prénom et nom, retrait, toasts, email de confirmation (sans le lien de désistement) |
| 3 | « Mes créneaux » + bloc CMS « Coups de main » sur l'accueil (§5.1) + bloc lettre d'information (§5.8) |
| 4 | Action admin « Répéter des besoins » (§5.7) |
| 5 | Rappel de la veille + lien « Je ne peux plus venir », ajouté aux deux mails (§5.9) + inscription par l'équipe (§5.10, D27) |
| 6 | API v2 allégée (§6 bis) + droit de clé + migration `BaseBillet` + OpenAPI, GUIDELINES et skill `tibillet-api`. Après le chantier 5 (lien de désistement dans le mail « l'équipe t'a inscrit·e ») |
| 7 | Pagination par semaine de la page publique (§11.1, D28) |
| 8 | Semaine type, création automatique des besoins, page d'admin « Besoins », filtres et index (§11.2, §11.3, D29 à D34). Après le chantier 7 : un planning hebdomadaire sans fin a besoin de la pagination |

Chaque chantier : son fichier `CHANGELOG/YYYY-MM-DD-slug.md`.

## 10. Questions ouvertes

Aucune. Questions tranchées le 2026-09-23 (D11 à D19), propositions P1 à P10 validées le
2026-09-24, D18 revue et D21 à D24 ajoutées le 2026-10-12, D25 à D27 issues de la relecture
du 2026-10-13.

L'API (D24) a été allégée le 2026-10-16 par le mainteneur, sur proposition de la relecture :
sans `repeat`, sans filtres `?email=`/`?dateFrom=`/`?dateTo=` des inscriptions, sans écriture de
`closingCalendar` ni de `requiredMembershipPlans`.

**Question ouverte (2026-10-17) — conservation des données personnelles (RGPD).** Rien n'est
supprimé (D33). Faut-il, au-delà de N ans, supprimer les inscriptions (lien vers la personne)
en gardant le besoin et le nombre de venues ? Pas urgent ; à trancher avant un usage massif.

Spec liée : `TODO/USERS-etiquettes.md` (D12), écrite le 2026-09-24, non commencée.

## 11. Évolutions du 2026-10-17 : pagination, semaine type, volumes

### 11.1 Pagination par semaine (chantier 7, D28)

- La page `/booking/benevolat/<slug>/` montre **une semaine** : du lundi au dimanche, colonnes
  = les jours de cette semaine qui ont au moins un besoin (desktop), même chose pour la liste
  et la barre de jours mobiles.
- Adresse : `?semaine=AAAA-MM-JJ`. Toute date est ramenée au lundi de sa semaine. Absente,
  illisible ou avant la semaine en cours → **la semaine du prochain besoin à venir** (ou la
  semaine en cours s'il n'y en a aucun). Le passé n'est jamais affiché (P6).
- Navigation : « ← Semaine précédente » (absente sur la semaine en cours) et « Semaine
  suivante → » (absente s'il n'y a plus aucun besoin après la semaine), avec le titre
  « 20 – 26 octobre ». Liens `href` avec `?semaine=` (marche sans JS) **et** `hx-get` de la
  zone avec `hx-push-url` (adresse partageable). La vue `retrieve` rend la zone seule pour une
  requête htmx qui cible `#benevolat-planning`.
- **Après une action sur un besoin** (« Je viens », « Me retirer », « Inscrire quelqu'un ») :
  la zone montre **la semaine de ce besoin**. Pas de paramètre à faire voyager.
- Le **compteur** de l'en-tête (D21) reste calculé sur tous les besoins à venir du planning.
- `construire_le_planning(planning, user, user_est_admin, semaine)` : charge toujours tous les
  besoins à venir (compteur global), puis découpe la semaine. `_reponse_zone` reçoit la semaine
  du besoin (`inscrire`, `retirer`, `inscrire_une_personne`) ; une semaine déjà passée (422
  « créneau passé ») retombe sur la semaine par défaut.
- Zone seule si `request.headers.get("HX-Target") == "benevolat-planning"`, sinon la page
  entière. Retour arrière après `hx-push-url` : htmx restaure son instantané, ou refait un GET
  `HX-History-Restore-Request` sans `HX-Target` → page entière. C'est voulu.
- Un besoin du dimanche 21 h → 0 h vu le lundi à 0 h 30 est compté (compteur) mais tombe dans
  une semaine passée : invisible. Accepté.
- **Fuseau lu une seule fois** : `debut()` / `fin()` appellent `Configuration.get_solo()` à
  chaque besoin (un aller-retour Redis chacun). `besoins_a_venir` lit le fuseau une fois et le
  passe (`fin(fuseau_du_lieu=…)`, comme `Booking.start_datetime_local`). Utile dès le chantier 7,
  indispensable au 8 (jusqu'à 26 semaines ouvertes).
- Tests : semaine par défaut, `?semaine=` un dimanche → son lundi, valeur illisible, semaine
  passée refusée, boutons présents/absents, action → semaine du besoin, 422 sur un besoin passé,
  compteur global, `HX-Target` différent → page entière, nombre de requêtes SQL **et** d'appels
  au cache constant (10 ou 300 besoins), E2E « semaine suivante » sans rechargement puis
  retour arrière.

### 11.2 Semaine type (chantier 8, D29 à D32, D34)

**Modèle.**

`PlanningBenevole`, champs ajoutés :

| Champ | Type | Note |
|---|---|---|
| `type_de_planning` | `CharField` choix `PONCTUEL` (défaut) / `HEBDOMADAIRE` | Les plannings existants restent ponctuels : aucune migration de données |
| `date_de_debut` | `DateField(null, blank)` | Hebdomadaire : premier jour où des besoins sont créés. Obligatoire dans ce mode (`clean`) |
| `date_de_fin` | `DateField(null, blank)` | Vide = sans fin |
| `horizon_en_semaines` | `PositiveSmallIntegerField(default=8)` | 1 à 26 : combien de semaines d'avance sont ouvertes aux inscriptions |
| `besoins_crees_jusqu_au` | `DateField(null, blank)` | Interne, lecture seule. Ce qui est avant cette date n'est jamais recréé |

`LigneDeSemaineType` (nouveau) : `uuid` (pk), `planning` (FK, `CASCADE`, `related_name="semaine_type"`),
`jour_de_la_semaine` (0 = lundi … 6 = dimanche), `tache` (FK, `PROTECT`), `heure_debut` /
`heure_fin` (vides = journée ; mêmes contraintes que `BesoinBenevole`), `nombre_souhaite` (≥ 1).

`BesoinBenevole`, champ ajouté : `ligne_de_semaine_type` (FK `LigneDeSemaineType`, `null`,
`SET_NULL`) — le besoin a été créé par cette ligne. Sert à appliquer une modification de la
ligne à ses besoins (D30).

**Création des besoins.**

- Fonction pure `besoins_de_la_semaine_type(lignes, du, au, periodes_fermees, besoins_existants)`
  dans `booking/benevolat.py`, sur le modèle de `calculer_repetitions` (§5.7) : une copie par
  ligne et par jour correspondant entre `du` et `au` ; jours fermés sautés ; doublons
  (`cle_d_un_besoin`) ignorés.
- `creer_les_besoins_de_la_semaine_type(planning)` : fenêtre `du` = le plus tard entre
  `date_de_debut`, aujourd'hui (fuseau du lieu) et le lendemain de `besoins_crees_jusqu_au` ;
  `au` = le plus tôt entre `date_de_fin` et aujourd'hui + `horizon_en_semaines`. Création dans
  une transaction (`bulk_create`), puis `besoins_crees_jusqu_au = au`.
- Appelée **à l'enregistrement de la fiche** (après les lignes : `save_related` de l'admin) et
  **chaque nuit** par une tâche Celery (tous les lieux, hors `public` et `WAITING_CONFIG`,
  comme le rappel ; 3 h UTC).
- **Concurrence** : l'enregistrement de l'admin et la tâche de nuit peuvent tomber en même
  temps (3 h UTC = 7 h à La Réunion). La fonction verrouille le planning
  (`PlanningBenevole.objects.select_for_update().get(pk=…)` dans `transaction.atomic()`) avant
  de lire `besoins_crees_jusqu_au` : la seconde attend la première et ne trouve plus rien à
  créer. Pas de `UniqueConstraint` : Django 4.2 n'a pas `nulls_distinct`, et les heures vides
  (journée) la rendraient inopérante.
- `besoins_crees_jusqu_au = max(ancienne valeur, au)` : il ne recule jamais (sinon une date de
  fin avancée puis reculée recréerait des besoins supprimés à la main). Fenêtre vide (`du > au`) :
  rien à faire.
- **Un besoin supprimé à la main n'est jamais recréé** : sa date est avant
  `besoins_crees_jusqu_au`.
- Un doublon ignoré à la création (un besoin identique saisi à la main) reste manuel : il ne
  suit pas la ligne.
- Fuseau : « aujourd'hui » = la date du lieu (un lieu en UTC+4 à 22 h UTC est déjà au
  lendemain). Les jours de la semaine : `date.weekday()`, 0 = lundi.

**Modifier la semaine type (D30).** À l'enregistrement de la fiche, dans `save_related` de
`PlanningBenevoleAdmin` **avant** `super().save_related` : pour une ligne supprimée, Django la
supprime au `super()` et `ligne_de_semaine_type` passe à vide (`SET_NULL`) ; ses besoins ne se
retrouvent plus ensuite. On collecte donc d'abord, pour chaque ligne supprimée ou modifiée, ses
besoins futurs sans inscrit. Un besoin « déplacé » se reconnaît à
`besoin.date.weekday() != ligne.jour_de_la_semaine`, ce qui traite d'un même geste une ligne
modifiée et changée de jour.

- **Ligne modifiée** (tâche, heures, nombre) : ses besoins futurs **sans inscrit** prennent
  les nouvelles valeurs ; ceux qui ont des inscrits ne bougent pas.
- **Ligne supprimée** : ses besoins futurs sans inscrit sont supprimés ; ceux qui ont des
  inscrits restent (`ligne_de_semaine_type` devient vide).
- **Nouvelle ligne, ou ligne qui change de jour** : ses besoins sont créés d'aujourd'hui à
  `besoins_crees_jusqu_au` (doublons ignorés) ; pour un changement de jour, les anciens futurs
  sans inscrit sont supprimés.
- **`date_de_fin` avancée / `date_de_debut` reculée** : les besoins futurs sans inscrit hors
  de la nouvelle période sont supprimés.
- **`date_de_debut` avancée** (mise plus tôt) : les jours entre le nouveau et l'ancien premier
  jour sont créés (jusqu'à `besoins_crees_jusqu_au`). Sans cette étape, ils seraient perdus :
  la création normale ne repasse jamais avant `besoins_crees_jusqu_au` (relecture Fable du code,
  2026-10-17).
- Message de l'admin : « N besoins créés, M mis à jour, P supprimés. K besoins avec des
  inscrits n'ont pas été modifiés : voir la page Besoins. » (lien filtré).
- Passage hebdomadaire → ponctuel : plus aucune création ; les besoins restent. Ponctuel →
  hebdomadaire : création à partir d'aujourd'hui.
- Une fermeture ajoutée après coup ne supprime rien (P9).
- **Exception manuelle** : un besoin modifié à la main (page « Besoins », inline ponctuelle,
  `PATCH` de l'API) et qui ne correspond plus à sa ligne est détaché
  (`ligne_de_semaine_type = None`, dans `BesoinBenevole.save()`, qui couvre tous ces chemins) :
  il devient manuel et la ligne ne l'écrase jamais. Les mises à jour faites par la ligne
  passent par `queryset.update()`, qui n'appelle pas `save()`.
- Un `POST /api/v2/volunteer-needs/` sur un planning hebdomadaire crée un besoin **manuel**
  (sans ligne) : même règle qu'en admin.

**Admin.**

- **Fiche planning** : `type_de_planning` ; en mode hebdomadaire (`conditional_fields`
  Unfold) `date_de_debut`, `date_de_fin`, `horizon_en_semaines` et la ligne en lecture seule
  « Besoins créés jusqu'au … ». Inlines selon le mode (`get_inlines`) : **hebdomadaire** → les
  lignes de la semaine type ; **ponctuel** → les besoins **à venir** seulement (l'inline actuelle,
  queryset filtré). Dans les deux cas, un lien « Voir tous les besoins de ce planning ». Les
  inlines suivent le type **enregistré** : à la création et juste après un changement de type,
  une aide dit « Enregistrez, puis saisissez la semaine type ». Jamais les deux inlines à la fois.
- « Répéter des besoins » : affiché pour les plannings ponctuels seulement (D34), **et refusé
  côté serveur** (`PermissionDenied`) pour un planning hebdomadaire : la vue reste joignable par
  son adresse.
- **Nouvelle page « Besoins »** (`BesoinBenevoleAdmin`), entrée de menu dans le bloc du module :
  colonnes jour, plage, tâche, planning, inscrit·es (`x/y`), fermeture ; filtre **« À venir »
  par défaut** sur le modèle d'`EventDateFilter` (`Administration/admin_tenant.py` ≈ l.4147 :
  `choices()` renomme le premier choix, `queryset()` filtre quand `value()` est vide, et
  « Tous » a sa propre valeur), planning, tâche, « avec / sans inscrit·es » ;
  `date_hierarchy = "date"` ; préchargements (`select_related`, nombre d'inscrits annoté) ;
  pagination standard (100). Ajout et modification permis (exceptions).
- Le message de l'admin pointe vers la page « Besoins » filtrée par planning (pas de filtre
  par ligne). Pas de filtre « En cours / Terminés » sur la liste des plannings, ni de
  recherche texte sur la page « Besoins » : inutiles aux volumes d'un lieu (relecture).
- Carte du bloc d'accueil : un planning hebdomadaire affiche « chaque semaine » au lieu de
  « du … au … » (qui glisserait chaque nuit avec l'horizon).
- Migration : `booking/0004_…` (ne pas fusionner dans `0003_benevolat`).

**Ce qui ne change pas.** Page publique, inscriptions, mails, lien signé, rappel, « Mes
créneaux » et API : ils travaillent sur des besoins réels. La semaine type n'est pas dans
l'API (allégée, D24) : à ajouter seulement si un outil en a besoin.

### 11.3 Volumes (D33)

- Une table de besoins **par lieu** (schéma). Ordre de grandeur : ~10 besoins par semaine
  pour un bar ouvert deux soirs, soit ~500 par an et par planning hebdomadaire. L'horizon borne
  l'avenir ; seul le passé s'accumule.
- Index `models.Index(fields=["planning", "date"])` sur `BesoinBenevole` : toutes les requêtes
  filtrent par planning et par date (« depuis hier », semaine affichée, page « Besoins »).
- Rien n'est supprimé en V1 : l'historique (qui est venu, quels créneaux sont restés vides)
  a de la valeur. Durée de conservation des données personnelles : question ouverte (§10).

### 11.4 Tests (chantier 8)

| Quoi | Où |
|---|---|
| `besoins_de_la_semaine_type` : un mois de semaines, jours fermés sautés, doublons ignorés, ligne de nuit (21:00 → 00:00), passage d'année | `booking/tests/test_benevolat_semaine_type.py` (fonction pure) |
| Fenêtre de création : `date_de_debut` future, `date_de_fin` atteinte, horizon, `besoins_crees_jusqu_au` avancé ; relancer ne crée rien | idem |
| Besoin supprimé à la main jamais recréé ; tâche de nuit sur plusieurs lieux (pas `public` ni `WAITING_CONFIG`) | idem |
| Modifier / supprimer une ligne : futurs sans inscrit modifiés / supprimés, avec inscrits intacts, message de l'admin | idem + test admin |
| Page « Besoins » : filtre « À venir » par défaut, filtres, nombre de requêtes constant (10 ou 300 besoins) | test admin |
| « Répéter » masqué **et refusé côté serveur** en mode hebdomadaire | test admin |
| Deux créations simultanées sur la même fenêtre (verrou) → aucun doublon ; `besoins_crees_jusqu_au` ne recule pas | `booking/tests/test_benevolat_semaine_type.py` |
| Ligne supprimée : sans inscrit supprimés, avec inscrits gardés et détachés ; ligne modifiée **et** changée de jour en un seul enregistrement | idem + test admin |
| Exception manuelle détachée, puis la ligne change : l'exception reste | test admin |
| `clean()` : `date_de_debut` obligatoire en hebdo, `date_de_fin >= date_de_debut`, horizon 1 à 26, mêmes règles d'heures que les besoins | idem |
| Lieu en UTC+4 à 22 h UTC : la fenêtre part du lendemain | idem |
| API : `POST volunteer-needs` sur un planning hebdo → besoin manuel | `tests/pytest/test_benevolat_api.py` |

