# Documentation de référence — API SIBIL pour TiBillet

> Reconstituée depuis :
> - Tutoriel Déclarant SIBIL (Ministère de la Culture, octobre 2019)
> - FAQ SIBIL officielle (culture.gouv.fr)
> - Description des champs open data SIBIL (data.culture.gouv.fr + data.gouv.fr)
> - Retours terrain éditeurs (Festik, Forum Billetterie 2018)
> - Spécification Swagger provisoire : `https://api.culture.gouv.fr/swagger/?url=https://api.culture.gouv.fr/services/sibil/sibil_v2.yml`
>
> **⚠️ La spec technique complète `SIBIL-SFD-002-Spécifications Editeur_v2.4` est à accès restreint.**
> Elle est transmise par le Ministère aux éditeurs sur demande à : **sibil.dgca@culture.gouv.fr**
> Estimation d'intégration API : 2 à 3 jours de développement (source : Forum Billetterie 2018, CapGemini)

---

## 1. Vue d'ensemble du système

SIBIL (Système d'Information BILletterie) est une obligation légale issue de l'article 48
de la loi n°2016-925 du 7 juillet 2016 (loi LCAP), encadrée par le décret n°2017-926 du 9 mai 2017.

**URL de production :** `https://sibil.culture.gouv.fr`
**URL API de base :** `https://api.culture.gouv.fr/services/sibil/`
**Contact éditeur :** sibil.dgca@culture.gouv.fr

**Qui est concerné :** tout entrepreneur de spectacles vivants détenteur d'une licence,
responsable de la billetterie — y compris les structures associatives, les organisateurs occasionnels
et les structures publiques.

---

## 2. Authentification

L'authentification se fait via **JWT (JSON Web Token)**.

### Étape 1 — Créer un compte secondaire "SIB" (une seule fois)

Le responsable de billetterie doit créer, dans son espace SIBIL, un compte secondaire
de type `SIB` (Système d'Information de Billetterie) :

1. Se connecter à `https://sibil.culture.gouv.fr`
2. Aller dans : Menu → Gestion des utilisateurs → Créer un utilisateur → Type : **SIB**
3. Saisir un identifiant machine et générer un mot de passe
4. Conserver ces deux valeurs : elles servent à générer le JWT

### Étape 2 — Obtenir le JWT à chaque session

```http
POST /api/authenticate
Content-Type: application/json

{
  "username": "mon_identifiant_sib",
  "password": "mon_mot_de_passe_sib"
}
```

**Réponse attendue :**
```json
{
  "id_token": "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ..."
}
```

Ce jeton JWT est ensuite passé dans toutes les requêtes via le header :
```http
Authorization: Bearer <id_token>
```

---

## 3. Les 3 familles d'endpoints de l'API SIBIL

```
┌─────────────────────────────────────────────────────────────┐
│  Famille 1 : Lecture des référentiels                        │
│  → Rechercher spectacle / lieu / festival existants          │
├─────────────────────────────────────────────────────────────┤
│  Famille 2 : Proposition de nouveaux référentiels            │
│  → Proposer un nouveau spectacle / lieu / festival           │
├─────────────────────────────────────────────────────────────┤
│  Famille 3 : Gestion des déclarations de représentations     │
│  → CRUD sur les représentations (créer, lire, modifier,      │
│    supprimer)                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Famille 1 — Lecture des référentiels

### 4.1 Rechercher un lieu existant

```http
GET /api/lieux?search=<nom_du_lieu>
Authorization: Bearer <id_token>
```

**Réponse (liste de lieux correspondants) :**
```json
[
  {
    "id": 12345,
    "nom": "La Carène",
    "siret": "12345678901234",
    "adresse": "1 boulevard de la Résistance",
    "code_postal": "29200",
    "ville": "Brest",
    "type_lieu": "SALLE_CONCERT_AUDITORIUM_OPERA_ZENITH",
    "statut": "VALIDE"
  }
]
```

### 4.2 Rechercher un spectacle existant

```http
GET /api/spectacles?search=<nom_du_spectacle>&domaine=<code_domaine>
Authorization: Bearer <id_token>
```

**Réponse :**
```json
[
  {
    "id": 67890,
    "nom": "L'Effet Papillon",
    "domaine": "THEATRE",
    "critere1": "L'Effet Papillon",
    "critere2": "Jean Dupont",
    "critere3": "Compagnie des Arts",
    "critere4": null,
    "jeune_public": false,
    "statut": "VALIDE"
  }
]
```

### 4.3 Rechercher un festival existant

```http
GET /api/festivals?search=<nom_du_festival>
Authorization: Bearer <id_token>
```

**Réponse :**
```json
[
  {
    "id": 111,
    "nom": "Fest-Noz de Cornouaille",
    "code_postal": "29000",
    "ville": "Quimper",
    "domaine": "MUSIQUE_TRADITIONNELLE",
    "statut": "VALIDE"
  }
]
```

---

## 5. Famille 2 — Proposer de nouveaux référentiels

Quand un lieu / spectacle / festival n'existe pas dans SIBIL, on peut en proposer un.
L'entrée est créée avec le statut `PROPOSE` (validation possible par l'admin SIBIL).
Ce statut **n'empêche pas** d'enregistrer la déclaration.

### 5.1 Proposer un nouveau spectacle

```http
POST /api/spectacles
Authorization: Bearer <id_token>
Content-Type: application/json

{
  "domaine": "POP_ROCK_REGGAE",
  "critere1": "Titre de l'œuvre",
  "critere2": "Nom de l'artiste ou groupe",
  "critere3": "Nom du producteur",
  "critere4": null,
  "jeune_public": false
}
```

**Critères par domaine de spectacle :**

| Domaine | Critère 1 (obligatoire) | Critère 2 (obligatoire) | Critère 3 (optionnel) | Critère 4 (optionnel) |
|---------|------------------------|------------------------|----------------------|----------------------|
| THEATRE | Titre de l'œuvre | Auteur | Metteur en scène | Compagnie |
| OPERA / THEATRE_LYRIQUE | Titre de l'œuvre | Compositeur | Chef d'orchestre | Compagnie |
| MUSIQUE_CLASSIQUE | Titre de l'œuvre | Compositeur | Interprète | Orchestre |
| CHANSON_VARIETES | Titre de l'œuvre | Artiste / Groupe | Producteur | — |
| POP_ROCK_REGGAE | Titre de l'œuvre | Artiste / Groupe | Producteur | — |
| JAZZ_BLUES | Titre de l'œuvre | Artiste / Groupe | — | — |
| MUSIQUES_URBAINES | Titre de l'œuvre | Artiste / Groupe | Producteur | — |
| MUSIQUE_ELECTRONIQUE | Titre de l'œuvre | Artiste / Groupe | — | — |
| MUSIQUE_TRADITIONNELLE | Titre de l'œuvre | Artiste / Groupe | — | — |
| MUSIQUES_DU_MONDE | Titre de l'œuvre | Artiste / Groupe | — | — |
| DANSE_DE_CREATION | Titre de l'œuvre | Chorégraphe | Compagnie | — |
| DANSE_CLASSIQUE_BAROQUE | Titre de l'œuvre | Chorégraphe | Compagnie | — |
| DANSES_URBAINES | Titre de l'œuvre | Artiste / Groupe | — | — |
| CIRQUE_DE_CREATION | Titre de l'œuvre | Metteur en scène | Compagnie | — |
| ARTS_DE_LA_RUE | Titre de l'œuvre | Metteur en scène | Compagnie | — |
| HUMOUR_SKETCH | Titre de l'œuvre | Artiste | Producteur | — |
| COMEDIE_MUSICALE | Titre de l'œuvre | Compositeur | Metteur en scène | — |
| PLURIDISCIPLINAIRE_AUTRE | Titre de l'œuvre | Artiste / Compagnie | — | — |

### 5.2 Proposer un nouveau lieu

```http
POST /api/lieux
Authorization: Bearer <id_token>
Content-Type: application/json

{
  "siret": "12345678901234",
  "nom": "Espace Culturel TiBillet",
  "type_lieu": "ESPACE_POLYVALENT",
  "adresse": "12 rue de la Coopération",
  "code_postal": "97400",
  "ville": "Saint-Denis"
}
```

**Valeurs possibles pour `type_lieu` :**

| Code interne | Libellé affiché |
|---|---|
| `THEATRE` | Théâtre |
| `ESPACE_POLYVALENT` | Espace / Polyvalent |
| `CASINO_DISCOTHEQUE_HOTEL_CAFE_RESTAURANT` | Casino / Discothèque / Hôtel / Café / Restaurant |
| `SALLE_CONCERT_AUDITORIUM_OPERA_ZENITH` | Salle de Concert / Auditorium / Opéra / Zénith |
| `CABARET_MUSIC_HALL` | Cabaret / Music Hall |
| `PLEIN_AIR_PARC_LOISIRS_ATTRACTION` | Plein Air / Parc de loisirs, d'attraction |
| `STRUCTURE_ITINERANTE_DEMONTABLE_CHAPITEAU` | Structure Itinérante et/ou démontable / Chapiteau |
| `LIEU_DE_CULTE` | Lieu de culte |
| `LIEU_DE_SANTE` | Lieu de santé (hôpital, EHPAD…) |
| `AUTRE` | Autre |

### 5.3 Proposer un nouveau festival

```http
POST /api/festivals
Authorization: Bearer <id_token>
Content-Type: application/json

{
  "nom": "Festival TiBillet en Fête",
  "code_postal": "97400",
  "ville": "Saint-Denis",
  "domaine": "MUSIQUES_DU_MONDE"
}
```

---

## 6. Famille 3 — Gestion des déclarations de représentations

C'est le cœur de l'intégration. Chaque représentation (ou série de représentations)
constitue une déclaration SIBIL.

### 6.1 Créer une déclaration de représentation

```http
POST /api/representations
Authorization: Bearer <id_token>
Content-Type: application/json
```

#### Corps de la requête — schéma complet

```json
{
  // ── SECTION DESCRIPTION ──────────────────────────────────────

  "est_festival": false,
  // true si la représentation s'inscrit dans un cadre festivalier

  "festival_id": null,
  // ID du festival dans le référentiel SIBIL (si est_festival = true)
  // OR : fournir les champs festival_* pour en proposer un nouveau

  "festival_nom": null,
  "festival_code_postal": null,
  "festival_ville": null,
  "festival_domaine": null,

  "spectacle_id": 67890,
  // ID du spectacle dans le référentiel SIBIL
  // OR : fournir les champs spectacle_* pour en proposer un nouveau

  "spectacle_nom": null,
  "spectacle_domaine": null,
  "spectacle_critere1": null,
  "spectacle_critere2": null,
  "spectacle_critere3": null,
  "spectacle_critere4": null,

  "jeune_public": false,
  // Obligatoire. true si la représentation est destinée au jeune public

  "domaine_representation": "POP_ROCK_REGGAE",
  // Obligatoire sauf si est_festival = true
  // Voir liste complète des domaines ci-dessous

  // ── SECTION LIEU ─────────────────────────────────────────────

  "lieu_id": 12345,
  // ID du lieu dans le référentiel SIBIL
  // OR : fournir les champs lieu_* pour en proposer un nouveau

  "lieu_nom": null,
  "lieu_siret": null,
  "lieu_type": null,
  "lieu_adresse": null,
  "lieu_code_postal": null,
  "lieu_ville": null,

  // ── SECTION DATE ─────────────────────────────────────────────

  "est_serie_de_representations": false,
  // false = représentation unique, true = série de représentations

  // Si est_serie_de_representations = false :
  "date_representation": "2024-06-15T21:00:00",
  // Format ISO 8601, obligatoire

  // Si est_serie_de_representations = true :
  "date_debut_serie": null,
  // Format ISO 8601
  "date_fin_serie": null,
  // Format ISO 8601. ATTENTION : ne peut pas dépasser la fin du trimestre en cours
  "nombre_de_representations_dans_la_serie": null,
  // Entier > 1, obligatoire si série

  // ── SECTION BILLETTERIE ──────────────────────────────────────

  "total_billets_billetterie": 320,
  // Nombre TOTAL de billets émis toutes catégories confondues
  // ⚠️ Ce champ n'est PAS la somme des sous-catégories ci-dessous
  // Il représente la capacité/jauge totale de la représentation

  "nombre_billets_plein_tarif": 180,
  // Billets vendus au tarif normal (toutes catégories de plein tarif)

  "recette_plein_tarif_ttc": 3240.00,
  // Recette en euros TTC des billets plein tarif

  "nombre_billets_abonnements_forfaits_adhesions": 85,
  // Billets via abonnements, forfaits, Pass, adhésions

  "recette_abonnements_forfaits_adhesions_ttc": 850.00,
  // Recette en euros TTC de ces billets

  "nombre_billets_exoneres_ou_gratuits": 55,
  // Billets émis gratuitement (invitations, personnels, presse…)
  // ⚠️ Les tarifs RÉDUITS ne sont PAS dans ce champ
  // Les tarifs réduits sont comptés dans "total_billets_billetterie"
  // et dans "nombre_billets_plein_tarif" côté SIBIL

  "total_recette_ttc": 4090.00,
  // Recette TTC totale de la représentation
  // = recette_plein_tarif_ttc + recette_abonnements_forfaits_adhesions_ttc
  // (+ toute autre recette payante non catégorisée)

  // Prix moyen calculé automatiquement par SIBIL :
  // prix_moyen = total_recette_ttc / nombre_billets_payants_total
  // Ne pas envoyer ce champ, SIBIL le calcule seul

  // ── MÉTADONNÉES ──────────────────────────────────────────────

  "est_coproduction": false,
  // true si la représentation implique plusieurs déclarants
  // (coproduction ou coréalisation)

  "statut": "BROUILLON"
  // "BROUILLON" = visible mais non soumis (modifiable)
  // "VALIDE"    = soumis, en attente de clôture trimestre
  // "ANNULE"    = représentation annulée (icône croix blanche/noir dans l'UI)
}
```

### 6.2 Règles de validation côté SIBIL

SIBIL valide automatiquement ces contrôles à l'enregistrement :

```
CONTRÔLE 1 :
  nombre_billets_plein_tarif
  + nombre_billets_abonnements_forfaits_adhesions
  + nombre_billets_exoneres_ou_gratuits
  ≤ total_billets_billetterie
  → Si violé : déclaration enregistrée comme INVALIDE

CONTRÔLE 2 :
  recette_plein_tarif_ttc
  + recette_abonnements_forfaits_adhesions_ttc
  ≤ total_recette_ttc
  → Si violé : déclaration enregistrée comme INVALIDE

CONTRÔLE 3 :
  prix_moyen_total (calculé) ≤ prix_moyen_plein_tarif (calculé)
  → Si violé : déclaration enregistrée comme INVALIDE
```

Une déclaration `INVALIDE` est **rejetée** au passage en batch de fin de trimestre.
Une déclaration `BROUILLON` est **ignorée** par le batch (pas de clôture automatique).

### 6.3 Lire une déclaration existante

```http
GET /api/representations/<id_declaration>
Authorization: Bearer <id_token>
```

### 6.4 Modifier une déclaration (statut BROUILLON ou VALIDE seulement)

```http
PUT /api/representations/<id_declaration>
Authorization: Bearer <id_token>
Content-Type: application/json

{ ...mêmes champs que POST... }
```

⚠️ Une déclaration au statut `CLOTURE` ne peut plus être modifiée par l'éditeur.
Seul l'administrateur SIBIL peut la modifier.

### 6.5 Supprimer une déclaration (statut BROUILLON ou VALIDE seulement)

```http
DELETE /api/representations/<id_declaration>
Authorization: Bearer <id_token>
```

---

## 7. Format CSV alternatif (import par dépôt de fichier)

SIBIL accepte aussi un import CSV. Ce format est utile pour des déclarations en masse
ou pour les structures sans système de billetterie automatisé.

### 7.1 Structure du fichier CSV

La **première colonne** `Type_Donnee` détermine le type de chaque ligne :

| Valeur `Type_Donnee` | Rôle de la ligne |
|---|---|
| `festival` | Proposer un nouveau festival dans le référentiel |
| `spectacle` | Proposer un nouveau spectacle dans le référentiel |
| `lieu` | Proposer un nouveau lieu dans le référentiel |
| `declaration` | Créer une déclaration de représentation |

### 7.2 Colonnes du fichier CSV (ordre obligatoire)

```
Type_Donnee | ID_Declaration | ID_Spectacle | ID_Festival | ID_Lieu
Domaine_Representation | Critere1_Spectacle | Critere2_Spectacle | Critere3_Spectacle | Critere4_Spectacle
Nom_Festival | CP_Festival | Ville_Festival | Domaine_Festival
Nom_Lieu | Denomination_Usuelle_Lieu | SIRET_Lieu | Type_Lieu_Code | Adresse_Lieu | CP_Lieu | Ville_Lieu
Jeune_Public | Est_Festival | Est_Serie
Date_Representation | Heure_Representation
Date_Debut_Serie | Date_Fin_Serie | Nombre_Representations_Serie
Total_Billets_Billetterie | Nombre_Billets_Plein_Tarif | Recette_Plein_Tarif_TTC
Nombre_Billets_Abonnements | Recette_Abonnements_TTC
Nombre_Billets_Exoneres | Total_Recette_TTC
Est_Coproduction
```

### 7.3 Exemple de ligne CSV — type `declaration`

```csv
Type_Donnee,ID_Declaration,ID_Spectacle,ID_Festival,ID_Lieu,...,Date_Representation,Total_Billets_Billetterie,...,Total_Recette_TTC
declaration,,67890,,12345,...,2024-06-15T21:00:00,320,...,4090.00
```

**Règle :** si `ID_Spectacle` / `ID_Festival` / `ID_Lieu` sont fournis (non vides),
ils ont **priorité** sur tous les champs texte correspondants.

Si les IDs sont vides, SIBIL crée les référentiels à partir des champs texte.

**Mettre à jour une déclaration existante :** conserver l'`ID_Declaration`.
**Créer une nouvelle déclaration :** laisser `ID_Declaration` vide.

---

## 8. Domaines de représentation — nomenclature complète SIBIL

| Code SIBIL | Libellé |
|---|---|
| `THEATRE` | Théâtre |
| `CONTE` | Conte |
| `MARIONNETTES` | Marionnettes |
| `MIME` | Mime |
| `CIRQUE_DE_CREATION` | Cirque de création |
| `CIRQUE_DE_TRADITION` | Cirque de tradition |
| `ARTS_DE_LA_RUE` | Arts de la Rue |
| `HUMOUR_SKETCH` | Humour / Sketch / One-Man Show / Imitation |
| `COMEDIE_MUSICALE` | Comédie musicale / Spectacle musical / Théâtre musical |
| `CABARET_MUSIC_HALL` | Cabaret / Music-Hall |
| `OPERA_THEATRE_LYRIQUE` | Opéra / Théâtre lyrique |
| `MUSIQUE_CLASSIQUE` | Musique classique, musique ancienne |
| `MUSIQUES_CONTEMPORAINES` | Musiques contemporaines |
| `CHANSON_VARIETES` | Chanson / Variétés |
| `JAZZ_BLUES` | Jazz / Blues / Soul / Groove / Musiques improvisées |
| `POP_ROCK_REGGAE` | Pop / Rock / Reggae et genres assimilés |
| `MUSIQUES_URBAINES` | Musiques urbaines (Rap, Hip hop, Slam, Beat Box) |
| `MUSIQUE_ELECTRONIQUE` | Musique électronique |
| `MUSIQUE_TRADITIONNELLE` | Musique traditionnelle |
| `MUSIQUES_DU_MONDE` | Musiques du Monde |
| `DANSE_DE_CREATION` | Danse de Création |
| `DANSE_TRADITIONNELLE` | Danse traditionnelle |
| `DANSES_URBAINES` | Danses Urbaines / Hip hop |
| `DANSE_JAZZ` | Danse Jazz |
| `DANSE_CLASSIQUE_BAROQUE` | Danse Classique / Baroque |
| `DANSES_DU_MONDE` | Danses du Monde |
| `PLURIDISCIPLINAIRE_AUTRE` | Pluridisciplinaire / Autre (spectacle sur glace, historique, aquatique, magie illusionniste, etc.) |

---

## 9. Calendrier de déclaration et gestion des relances

```
Trimestre T1 : 1er janvier   → 31 mars
Trimestre T2 : 1er avril     → 30 juin
Trimestre T3 : 1er juillet   → 30 septembre
Trimestre T4 : 1er octobre   → 31 décembre

Délai de dépôt : avant le 10 du 1er mois du trimestre SUIVANT
  - T1 → avant le 10 avril
  - T2 → avant le 10 juillet
  - T3 → avant le 10 octobre
  - T4 → avant le 10 janvier

Batch de clôture : exécuté en début de trimestre T+1
  → passe les déclarations VALIDE en statut CLOTURE
  → rejette les déclarations INVALIDE (statut REJETE)
  → ignore les déclarations BROUILLON

Relances automatiques :
  → Relance 1 par email après le 10 du mois
  → Relance 2 par email si toujours rien
  → Rapport de non-déclaration au Ministère si aucune réponse

Inactivité totale sur un trimestre :
  → Déposer un justificatif d'inactivité sur le portail SIBIL
  → Le déclarant n'est alors pas relancé
```

**Important (FAQ SIBIL) :**
- Les billets émis à titre gratuit pour une représentation payante sont déclarés dans `nombre_billets_exoneres_ou_gratuits`
- Les tarifs réduits n'ont pas de champ dédié ; ils sont comptabilisés dans `total_billets_billetterie` et `nombre_billets_plein_tarif`
- Un Pass / abonnement multi-séances se déclare dans `nombre_billets_abonnements_forfaits_adhesions`
- Une représentation sans émission de billets (entrée libre sans billet) n'est **pas** déclarée
- Une représentation annulée peut être déclarée avec le statut `ANNULE` (non obligatoire)

---

## 10. Mapping TiBillet → SIBIL

Correspondance entre les modèles Django TiBillet et les champs SIBIL :

```python
# Mapping conceptuel — à adapter aux vrais noms de champs TiBillet

MAPPING_TIBILLET_VERS_SIBIL = {

    # ── IDENTIFICATION DU SPECTACLE ──────────────────────────────

    # Champ TiBillet            → Champ SIBIL
    "event.name"                : "spectacle_nom / critere1",
    "event.categorie"           : "domaine_representation",  # à mapper via DOMAINES_SIBIL
    "event.is_young_audience"   : "jeune_public",
    "event.festival"            : "est_festival",
    "event.festival_name"       : "festival_nom",

    # ── LIEU ────────────────────────────────────────────────────

    "configuration.structure.siret" : "lieu_siret",
    "configuration.structure.name"  : "lieu_nom",
    "configuration.structure.type"  : "lieu_type",  # à mapper via TYPES_LIEU_SIBIL
    "configuration.structure.address" : "lieu_adresse",
    "configuration.structure.zip"   : "lieu_code_postal",
    "configuration.structure.city"  : "lieu_ville",

    # ── DATE ────────────────────────────────────────────────────

    "event.datetime"            : "date_representation",
    # Si série : event.date_start / event.date_end + nb représentations

    # ── BILLETTERIE ─────────────────────────────────────────────

    # Billets scannés (contrôle d'accès LaBoutik)
    "ticket.count_total_emis"   : "total_billets_billetterie",

    # Billets plein tarif (tarifs non réduits, non abonnements)
    "ticket.count_plein_tarif"  : "nombre_billets_plein_tarif",
    "ticket.recette_plein_tarif": "recette_plein_tarif_ttc",

    # Abonnements / Pass membres TiBillet / adhésions
    "ticket.count_adhesion"     : "nombre_billets_abonnements_forfaits_adhesions",
    "ticket.recette_adhesion"   : "recette_abonnements_forfaits_adhesions_ttc",

    # Invitations / gratuits
    "ticket.count_gratuit"      : "nombre_billets_exoneres_ou_gratuits",

    # Recette totale TTC (= hors cashless, uniquement billetterie)
    "ticket.recette_totale_ttc" : "total_recette_ttc",
}

# Attention : les tarifs RÉDUITS TiBillet doivent être inclus dans :
#   - total_billets_billetterie (le total global)
#   - nombre_billets_plein_tarif (côté SIBIL, "plein tarif" = tout billet payant non-abonnement)
# Les tarifs réduits ne forment PAS une catégorie SIBIL distincte.
```

---

## 11. Champs présents dans les données open data SIBIL

Les données publiées sur data.culture.gouv.fr représentent les données **agrégées et anonymisées**
(les champs financiers ont été exclus par la CADA en 2023).

Champs publics disponibles dans le jeu de données open data :

```
- annee                          : Année de la représentation
- trimestre                      : Trimestre (1, 2, 3, 4)
- id_declaration                 : Identifiant de la déclaration (anonymisé)
- domaine_representation         : Code du domaine SIBIL
- libelle_domaine_representation : Libellé du domaine
- est_festival                   : Oui / Non
- nom_festival                   : Nom du festival (si applicable)
- jeune_public                   : Oui / Non
- type_lieu                      : Code type de lieu SIBIL
- libelle_type_lieu              : Libellé type de lieu
- code_postal_lieu               : Code postal du lieu
- commune_lieu                   : Commune du lieu
- departement_lieu               : Département du lieu
- region_lieu                    : Région du lieu
- date_representation            : Date de la représentation
- est_serie                      : Oui / Non (série de représentations)
- nombre_representations         : Nombre de représentations (si série)

# Champs EXCLUS de la publication (secret des affaires, avis CADA 2023) :
# - total_billets_billetterie
# - total_recette_ttc
# - prix_moyen_total_billetterie
# - nombre_billets_plein_tarif
# - recette_plein_tarif
# - prix_moyen_plein_tarif
# - nombre_billets_abonnements_forfaits_adhesions
# - nombre_billets_exoneres_ou_gratuits
```

---

## 12. Prochaines étapes pour TiBillet

### Priorité 1 — Obtenir la spec officielle

Envoyer un email à `sibil.dgca@culture.gouv.fr` en demandant :
- Le document `SIBIL-SFD-002-Spécifications Editeur v2.4`
- L'accès à un environnement de test / sandbox SIBIL
- La confirmation des URLs d'API en production

### Priorité 2 — Modèle Django à créer : `SibilDeclaration`

```python
# Modèle Django suggéré (FALC-style, lisible, verbeux)

class SibilDeclaration(models.Model):
    """
    Une déclaration SIBIL correspond à une représentation (ou série de représentations)
    déclarée au Ministère de la Culture.
    Chaque instance est liée à un événement TiBillet.
    """

    # Clé primaire SIBIL (nulle jusqu'à l'envoi réussi à l'API)
    identifiant_sibil = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="ID retourné par SIBIL après envoi réussi"
    )

    # Lien vers l'événement TiBillet source
    evenement = models.ForeignKey(
        "Event",  # adapter au vrai nom du modèle TiBillet
        on_delete=models.PROTECT,
        related_name="declarations_sibil"
    )

    # Statut de la déclaration
    STATUT_BROUILLON = "BROUILLON"
    STATUT_VALIDE = "VALIDE"
    STATUT_CLOTURE = "CLOTURE"
    STATUT_REJETE = "REJETE"
    STATUT_ANNULE = "ANNULE"
    CHOIX_STATUT = [
        (STATUT_BROUILLON, "Brouillon — non encore soumis à SIBIL"),
        (STATUT_VALIDE, "Valide — soumis, en attente de clôture"),
        (STATUT_CLOTURE, "Clôturé — accepté par SIBIL"),
        (STATUT_REJETE, "Rejeté — erreur de validation SIBIL"),
        (STATUT_ANNULE, "Annulé — représentation annulée"),
    ]
    statut = models.CharField(
        max_length=20,
        choices=CHOIX_STATUT,
        default=STATUT_BROUILLON
    )

    # Trimestre de déclaration
    annee_declaration = models.IntegerField()
    trimestre_declaration = models.IntegerField(choices=[(1,"T1"),(2,"T2"),(3,"T3"),(4,"T4")])

    # IDs référentiels SIBIL (null si non encore créé dans SIBIL)
    identifiant_spectacle_sibil = models.IntegerField(null=True, blank=True)
    identifiant_lieu_sibil = models.IntegerField(null=True, blank=True)
    identifiant_festival_sibil = models.IntegerField(null=True, blank=True)

    # Description
    est_dans_un_festival = models.BooleanField(default=False)
    est_pour_le_jeune_public = models.BooleanField(default=False)
    domaine_representation_code_sibil = models.CharField(max_length=50)

    # Billetterie (les valeurs réelles à envoyer à SIBIL)
    total_billets_emis = models.IntegerField(default=0)
    nombre_billets_plein_tarif = models.IntegerField(default=0)
    recette_plein_tarif_ttc = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    nombre_billets_abonnements_et_pass = models.IntegerField(default=0)
    recette_abonnements_et_pass_ttc = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    nombre_billets_gratuits_et_invitations = models.IntegerField(default=0)
    recette_totale_ttc = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Horodatage
    date_creation = models.DateTimeField(auto_now_add=True)
    date_derniere_modification = models.DateTimeField(auto_now=True)
    date_envoi_sibil = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Déclaration SIBIL"
        verbose_name_plural = "Déclarations SIBIL"
        ordering = ["-annee_declaration", "-trimestre_declaration"]

    def __str__(self):
        return f"SIBIL {self.annee_declaration}/T{self.trimestre_declaration} — {self.evenement}"
```

### Priorité 3 — Endpoint Django pour générer le CSV SIBIL par trimestre

L'organisateur clique sur "Générer déclaration SIBIL T2 2024" → TiBillet produit le CSV
prêt à importer dans le portail SIBIL (ou à envoyer via l'API).

---

*Document produit par TiBillet — Coopérative de billetterie open source (AGPLv3)*
*Sources : Ministère de la Culture, data.culture.gouv.fr, data.gouv.fr, Forum Billetterie 2018*
