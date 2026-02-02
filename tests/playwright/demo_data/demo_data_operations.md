# Documentation des opérations du script demo_data.py

Ce document liste toutes les opérations réalisées par le script de commande Django `demo_data.py` situé dans `Administration/management/commands/demo_data.py`.

L'objectif de cette documentation est de servir de base pour la création de tests E2E avec Playwright qui reproduiront ces mêmes opérations via un navigateur.

---

## Vue d'ensemble

Le script `demo_data.py` est une commande Django qui crée un jeu de données de démonstration complet pour l'application TiBillet/Lespass. Il initialise deux tenants (locataires multi-tenant) avec une configuration complète incluant des produits, des adhésions, des événements, et des intégrations externes.

---

## 1. Initialisation et configuration des tenants

**⚠️ NOTE IMPORTANTE** : Cette section continue d'être générée via la commande Django `demo_data_minimal.py`.
Toutes les autres sections (2 à 8) seront réalisées via des scripts Playwright E2E.

### 1.1 Récupération et modification du tenant principal
- **Action** : Récupère le tenant existant via la variable d'environnement `SUB`
- **Opération** : Renomme le tenant en "Le Tiers-Lustre"
- **Modèle** : `Client`

### 1.2 Création d'un second tenant pour la fédération
- **Action** : Crée ou récupère un tenant nommé "Chantefrein"
- **Configuration** :
  - `schema_name` : slug du nom (chantefrein)
  - `name` : "Chantefrein"
  - `on_trial` : False
  - `categorie` : `Client.SALLE_SPECTACLE`
- **Domaine** : Crée un domaine `chantefrein.{DOMAIN}` (is_primary=True)
- **Utilisateur** : Associe l'administrateur (via `ADMIN_EMAIL`) au tenant et s'assure qu'il est admin des deux tenants
- **Modèles** : `Client`, `Domain`, `TibilletUser`

---

## 2. Configuration générale (pour chaque tenant)

Les opérations suivantes sont effectuées pour les deux tenants (Le Tiers-Lustre et Chantefrein).

### 2.1 Configuration de l'organisation
- **Modèle** : `Configuration` (singleton via `get_solo()`)
- **Champs configurés** :
  - `organisation` : Nom du tenant
  - `short_description` : Description courte de l'instance de démonstration
  - `long_description` : Description longue avec détails sur les fonctionnalités
  - `tva_number` : Numéro de TVA généré (fake.bban()[:20])
  - `siren` : Numéro SIREN généré (fake.siret()[:20])
  - `phone` : Numéro de téléphone généré
  - `email` : Email de l'administrateur (via `ADMIN_EMAIL`)
  - `stripe_mode_test` : True
  - `stripe_connect_account_test` : Compte Stripe de test (via variable d'environnement)
  - `stripe_payouts_enabled` : True
  - `site_web` : "https://tibillet.org"
  - `legal_documents` : "https://tibillet.org/cgucgv"
  - `twitter` : "https://twitter.com/tibillet"
  - `facebook` : "https://facebook.com/tibillet"
  - `instagram` : "https://instagram.com/tibillet"

### 2.2 Création des adresses postales

#### Adresse principale (Manapany)
- **Modèle** : `PostalAddress`
- **Champs** :
  - `name` : "Manapany"
  - `street_address` : Adresse générée
  - `address_locality` : Ville générée
  - `address_region` : Région générée
  - `postal_code` : '69100'
  - `address_country` : 'FR'
  - `latitude` : 43.90545495459708
  - `longitude` : 7.532343890994476
  - `comment` : "Bus 42 et métro : Arrêt D. Adams. Merci d'eteindre votre moteur d'improbabilité infinie."
  - `is_main` : True
- **Liaison** : Associée à la configuration (`config.postal_address`)

#### Adresse secondaire (Libre Roya)
- **Modèle** : `PostalAddress`
- **Champs** :
  - `name` : "Libre Roya"
  - `street_address` : Adresse générée
  - `address_locality` : Ville générée
  - `address_region` : Région générée
  - `postal_code` : Code postal généré
  - `address_country` : 'France'
  - `latitude` : -21.37271167192088
  - `longitude` : 55.58819666101755
  - `comment` : "Parking sur le col des Aravis. Boisson offerte si vous venez à velo. Paix et prospérité."
  - `is_main` : False

### 2.3 Configuration de Formbricks
- **Modèle** : `FormbricksConfig` (singleton)
- **Action** : Configure la clé API si `TEST_FORMBRICKS_API` est définie dans l'environnement
- **Méthode** : `set_api_key()`

### 2.4 Liaison avec Fedow
- **Action** : Initialise la connexion Fedow via `FedowAPI()`
- **Effet** : Crée automatiquement un lieu côté Fedow si non existant
- **Vérification** : Assertion que `FedowConfig.get_solo().can_fedow()` retourne True

---

## 3. Création des options générales

Ces options sont utilisées comme cases à cocher ou boutons radio dans les formulaires de produits.

### 3.1 Options créées
- **Modèle** : `OptionGenerale`
- **Liste des options** :
  1. **"Membre actif.ve"** - Description : "Je souhaite m'investir à donf !"
  2. **"Végétarien·ne"** - Description : "Je suis végé"
  3. **"Intolérance au gluten"** - Sans description
  4. **"Livraison à l'asso"** - Sans description
  5. **"Livraison à la maison"** - Sans description
  6. **"Terrasse"** - Description : "Une table en terrasse"
  7. **"Salle"** - Description : "Une table à l'intérieur"

---

## 4. Produits d'adhésion (Memberships)

### 4.1 Adhésion principale au collectif

#### Produit
- **Nom** : "Adhésion ({nom_tenant})"
- **Description courte** : "Adhérez au collectif {nom_tenant}"
- **Description longue** : "Vous pouvez prendre une adhésion en une seule fois, ou payer tous les mois."
- **Catégorie** : `Product.ADHESION`
- **Options** : Option checkbox "Membre actif.ve" ajoutée

#### Tarifs
1. **Annuelle**
   - Prix : 20€
   - Paiement récurrent : Non
   - Type : `Price.YEAR`

2. **Mensuelle**
   - Prix : 2€
   - Paiement récurrent : Oui
   - Type : `Price.MONTH`

3. **Prix libre**
   - Prix : 1€ (minimum)
   - Prix libre : Oui
   - Type : `Price.YEAR`

### 4.2 Adhésion avec tarifs récurrents multiples

#### Produit
- **Nom** : "Adhésion récurrente ({nom_tenant})"
- **Description courte** : "Adhésion avec paiements récurrents"
- **Description longue** : "Adhésion récurrente avec des tarifs journaliers, hebdomadaires, mensuels et annuels."
- **Catégorie** : `Product.ADHESION`
- **Options** : Option checkbox "Membre actif.ve" ajoutée

#### Tarifs
1. **Journalière**
   - Prix : 2€
   - Paiement récurrent : Oui
   - Type : `Price.DAY`

2. **Hebdomadaire**
   - Prix : 10€
   - Paiement récurrent : Oui
   - Type : `Price.WEEK`

3. **Mensuelle**
   - Prix : 20€
   - Paiement récurrent : Oui
   - Type : `Price.MONTH`

4. **Annuelle**
   - Prix : 150€
   - Paiement récurrent : Oui
   - Type : `Price.YEAR`

### 4.3 Adhésion avec validation sélective

#### Produit
- **Nom** : "Adhésion à validation sélective ({nom_tenant})"
- **Description courte** : "Tarif solidaire soumis à validation manuelle"
- **Description longue** : "Le tarif solidaire nécessite une validation manuelle. Le plein tarif est accepté automatiquement."
- **Catégorie** : `Product.ADHESION`
- **Options** : Option checkbox "Membre actif.ve" ajoutée

#### Tarifs
1. **Solidaire** (nécessite validation manuelle)
   - Prix : 2€
   - Paiement récurrent : Non
   - Type : `Price.YEAR`
   - Validation manuelle : Oui

2. **Plein tarif** (acceptation automatique)
   - Prix : 30€
   - Paiement récurrent : Non
   - Type : `Price.YEAR`
   - Validation manuelle : Non

### 4.4 Panier AMAP

#### Produit
- **Nom** : "Panier AMAP ({nom_tenant})"
- **Description courte** : "Adhésion au panier de l'AMAP partenaire {nom_tenant}"
- **Description longue** : "Association pour le maintien d'une agriculture paysanne. Recevez un panier chaque semaine."
- **Catégorie** : `Product.ADHESION`
- **Options radio** : "Livraison à l'asso" et "Livraison à la maison"

#### Tarifs
1. **Annuelle**
   - Prix : 400€
   - Paiement récurrent : Non
   - Type : `Price.YEAR`

2. **Mensuelle**
   - Prix : 40€
   - Paiement récurrent : Oui
   - Type : `Price.MONTH`

### 4.5 Caisse de sécurité sociale alimentaire (SSA)

**Note** : Créé uniquement pour le tenant "Le Tiers-Lustre"

#### Création de l'asset Fedow
- **Action** : Crée un token asset via Fedow
- **Paramètres** :
  - `name` : "CLAF-Outil"
  - `currency_code` : "CSA"
  - `category` : `AssetFedowPublic.TOKEN_LOCAL_FIAT`

#### Produit
- **Nom** : "Caisse de sécurité sociale alimentaire"
- **Description courte** : "Payez selon vos moyens, recevez selon vos besoins !"
- **Description longue** : "Payez ce que vous pouvez : l'adhésion à la SSA vous donne droit à 150€ sur votre carte à dépenser dans tout les lieux participants. Une validation par un.e administrateur.ice est nécéssaire. Engagement demandé de 3 mois minimum."
- **Catégorie** : `Product.ADHESION`

#### Tarif
- **Nom** : "Mensuelle"
- **Description** : "Adhésion pour 3 mois. Paiement mensuel récurent."
- **Prix** : 50€
- **Prix libre** : Oui
- **Paiement récurrent** : Oui
- **Itérations** : 3
- **Type** : `Price.CAL_MONTH`
- **Récompense Fedow** :
  - Activée : Oui
  - Asset : Token CSA créé précédemment
  - Montant : 150

#### Formulaire dynamique
Champs personnalisés ajoutés au produit SSA :

1. **"Pseudonyme"**
   - Type : `SHORT_TEXT`
   - Obligatoire : Oui
   - Ordre : 1
   - Aide : "Affiché à la communauté ; vous pouvez utiliser un pseudonyme."

2. **"À propos de vous"**
   - Type : `LONG_TEXT`
   - Obligatoire : Non
   - Ordre : 2
   - Aide : "Nous aide à mieux vous connaître."

3. **"Style préféré"**
   - Type : `SINGLE_SELECT`
   - Options : ["Rock", "Jazz", "Musiques du monde", "Electro"]
   - Obligatoire : Oui
   - Ordre : 3
   - Aide : "Choisissez-en un."

4. **"Centres d'intérêt que vous souhaitez partager"**
   - Type : `MULTI_SELECT`
   - Options : ["Cuisine", "Jardinage", "Musique", "Technologie", "Art", "Sport"]
   - Obligatoire : Non
   - Ordre : 4
   - Aide : "Sélectionnez autant d'options que vous le souhaitez."

---

## 5. Produit de badgeuse (Co-working)

### Produit
- **Nom** : "Badgeuse co-working ({nom_tenant})"
- **Description courte** : "Accès à l'espace de co-working."
- **Description longue** : "Merci de pointer à chaque entrée ET sortie même pour un passage rapide. Les adhérent·es bénéficient de 3h gratuites par semaine."
- **Catégorie** : `Product.BADGE`

### Tarif
- **Nom** : "Passage"
- **Description** : "Pointage d'un passage"
- **Prix** : 0€
- **Paiement récurrent** : Non

---

## 6. Création des tags d'événements

- **Modèle** : `Tag`
- **Tags créés** :
  1. **Rock** - Couleur : #3B71CA
  2. **Jazz** - Couleur : #14A44D
  3. **World** - Couleur : #DC4C64
  4. **Gratuit** - Couleur : #E4A11B
  5. **Entrée libre** - Couleur : #FBFBFB
  6. **chantiers** - Couleur : #54B4D3
  7. **Prix libre** - (créé plus tard, pas de couleur spécifiée)
  8. **Formulaire démo** - Couleur : #9C27B0
  9. **Formulaire** - Couleur : #9C27B0 (si Formbricks activé)

---

## 7. Événements

### 7.1 Scène ouverte : Entrée libre

#### Événement
- **Nom** : "Scène ouverte : Entrée libre"
- **Date** : future_datetime('+7d') + 360 jours
- **Description courte** : "Scène ouverte Rock !"
- **Description longue** : "Un évènement gratuit, ouvert à tous.tes sans réservation. Seul les artistes annoncés et les descriptions sont affichés."
- **Catégorie** : `Event.CONCERT`
- **Adresse** : postal_address (Manapany)
- **Tags** : Rock, Gratuit, Entrée libre
- **Produits** : Aucun (entrée libre sans réservation)

### 7.2 Disco Caravane : Gratuit avec réservation

#### Produit de réservation gratuite
- **Nom** : "Réservation gratuite"
- **Description** : "Réservation gratuite"
- **Catégorie** : `Product.FREERES`
- **Nominatif** : Non

#### Événement
- **Nom** : "Disco Caravane : Gratuit avec réservation"
- **Date** : future_datetime('+7d') + 360 jours
- **Jauge max** : 200
- **Max par utilisateur** : 4
- **Description courte** : "Attention, places limitées, pensez à réserver !"
- **Description longue** : "Un évènement gratuit, avec une jauge maximale de 200 personnes et un nombre de billets limité à 4 par réservation. Billets non nominatifs. Ça fait pas mal pour une caravane hein ?"
- **Catégorie** : `Event.CONCERT`
- **Adresse** : postal_address (Manapany)
- **Tags** : Jazz, Gratuit
- **Produits** : Réservation gratuite

### 7.3 Concert caritatif : Entrée à prix libre

#### Produit de réservation à prix libre
- **Nom** : "Réservation à prix libre"
- **Description** : "Réservation à prix libre"
- **Catégorie** : `Product.BILLET`
- **Nominatif** : Non

#### Tarif
- **Nom** : "Prix libre"
- **Prix** : 1€ (minimum)
- **Prix libre** : Oui
- **Description** : "Prix libre"

#### Événement
- **Nom** : "Concert caritatif : Entrée a prix libre"
- **Date** : future_datetime('+7d') + 360 jours
- **Jauge max** : 200
- **Max par utilisateur** : 4
- **Description courte** : "Attention, places limitées, pensez à réserver !"
- **Description longue** : "Un évènement à prix libre, avec une jauge maximale de 200 personnes et un nombre de billets limité à 1 par réservation. Billets non nominatifs."
- **Catégorie** : `Event.CONCERT`
- **Adresse** : postal_address_2 (Libre Roya)
- **Tags** : Jazz, Prix libre
- **Produits** : Réservation à prix libre

### 7.4 What the Funk ? Spectacle payant

#### Produit billet nominatif
- **Nom** : "Billet"
- **Description** : "Billet"
- **Catégorie** : `Product.BILLET`
- **Nominatif** : Oui

#### Tarifs
1. **Plein tarif**
   - Prix : 20€

2. **Tarif adhérent**
   - Prix : 10€
   - Adhésion obligatoire : Adhésion au collectif (adhesion_asso)

#### Événement
- **Nom** : "What the Funk ? Spectacle payant"
- **Date** : future_datetime('+7d') + 360 jours
- **Jauge max** : 600
- **Max par utilisateur** : 10
- **Description courte** : "Spectacle payant avec tarif préférentiel pour les adhérents à l'association."
- **Description longue** : "Jauge maximale de 600 personnes et nombre de billets limité à 10 par réservation. Billets nominatifs."
- **Catégorie** : `Event.CONCERT`
- **Adresse** : Pas d'adresse spécifiée
- **Tags** : World
- **Produits** : Billet

### 7.5 Soirée découverte avec formulaire

#### Produit avec formulaire dynamique
- **Nom** : "Billet démo avec formulaire ({nom_tenant})"
- **Description courte** : "Billet avec formulaire personnalisé (démo Offcanvas)"
- **Catégorie** : `Product.BILLET`
- **Nominatif** : Non

#### Tarif
- **Nom** : "Tarif unique"
- **Prix** : 12€
- **Paiement récurrent** : Non

#### Champs de formulaire
1. **"Votre pseudo pour la soirée"**
   - Type : `SHORT_TEXT`
   - Obligatoire : Oui
   - Ordre : 1
   - Aide : "Sera affiché sur la liste d'invités."

2. **"Message pour l'organisateur·rice"**
   - Type : `LONG_TEXT`
   - Obligatoire : Non
   - Ordre : 2
   - Aide : "Optionnel (≈300 caractères)."

3. **"Boisson préférée"**
   - Type : `SINGLE_SELECT`
   - Options : ["Eau", "Jus", "Soda", "Bière sans alcool"]
   - Obligatoire : Oui
   - Ordre : 3
   - Aide : "Un seul choix possible."

4. **"Ateliers auxquels participer"**
   - Type : `MULTI_SELECT`
   - Options : ["Chant", "Danse", "Percussions", "Lumières", "Son"]
   - Obligatoire : Non
   - Ordre : 4
   - Aide : "Choisissez autant d'options que vous voulez."

#### Événement
- **Nom** : "Soirée découverte avec formulaire"
- **Date** : future_datetime('+9d') + 360 jours
- **Jauge max** : 120
- **Max par utilisateur** : 4
- **Description courte** : "Réservation avec formulaire supplémentaire (tous types d'inputs)"
- **Description longue** : "Cet événement affiche un formulaire dynamique dans l'offcanvas de réservation : texte court, texte long, sélecteur simple et multiple."
- **Catégorie** : `Event.CONCERT`
- **Adresse** : postal_address (Manapany)
- **Tags** : Formulaire démo
- **Produits** : Billet démo avec formulaire

### 7.6 Chantier participatif avec sous-événements

#### Événement parent
- **Nom** : "Chantier participatif : besoin de volontaires"
- **Date** : future_datetime('+14d') + 360 jours
- **Description courte** : "Venez participer à nos chantiers collectifs !"
- **Description longue** : "Nous avons besoin de volontaires pour différentes actions de chantier participatif. Inscrivez-vous aux différentes sessions selon vos disponibilités et compétences."
- **Catégorie** : `Event.CHANTIER`
- **Adresse** : postal_address (Manapany)
- **Jauge max** : 30
- **Max par utilisateur** : 1
- **Tags** : chantiers, Gratuit

#### Sous-événement 1 : Jardinage
- **Nom** : "Jardinage et plantation"
- **Date** : future_datetime('+15d') + 360 jours
- **Description courte** : "Aménagement du jardin partagé"
- **Description longue** : "Venez nous aider à planter, désherber et aménager notre jardin partagé. Apportez vos gants et votre bonne humeur !"
- **Catégorie** : `Event.ACTION`
- **Jauge max** : 10
- **Max par utilisateur** : 1
- **Parent** : event_chantier_participatif
- **Tags** : chantiers

#### Sous-événement 2 : Peinture
- **Nom** : "Peinture et décoration"
- **Date** : future_datetime('+16d') + 360 jours
- **Description courte** : "Rafraîchissement des murs et décorations"
- **Description longue** : "Session de peinture pour rafraîchir les murs du local. Nous fournirons le matériel, venez avec des vêtements adaptés."
- **Catégorie** : `Event.ACTION`
- **Jauge max** : 8
- **Max par utilisateur** : 1
- **Parent** : event_chantier_participatif
- **Tags** : chantiers

#### Sous-événement 3 : Bricolage
- **Nom** : "Bricolage et réparations"
- **Date** : future_datetime('+17d') + 360 jours
- **Description courte** : "Petits travaux de bricolage"
- **Description longue** : "Nous avons besoin de personnes pour effectuer divers travaux de bricolage : réparation de mobilier, installation d'étagères, etc. Si vous avez des compétences en bricolage, rejoignez-nous !"
- **Catégorie** : `Event.ACTION`
- **Jauge max** : 5
- **Max par utilisateur** : 1
- **Parent** : event_chantier_participatif
- **Tags** : chantiers

---

## 8. Intégration Formbricks (optionnelle)

**Condition** : Créé uniquement si les variables d'environnement `TEST_FORMBRICKS_ADH_FORM` et `TEST_FORMBRICKS_EVENT_FORM` sont définies.

### 8.1 Événement avec formulaire Formbricks

#### Produit
- **Nom** : "Billet avec formulaire Formbricks"
- **Description courte** : "Démonstration d'un billet avec formulaire personnalisé"
- **Description longue** : "Ce produit est une démonstration de l'intégration avec Formbricks. Après l'achat, un formulaire personnalisé sera présenté pour recueillir des informations supplémentaires."
- **Catégorie** : `Product.BILLET`
- **Nominatif** : Oui

#### Tarif
- **Nom** : "Tarif standard"
- **Description** : "Tarif standard avec formulaire"
- **Prix** : 15€

#### Formulaire Formbricks
- **Modèle** : `FormbricksForms`
- **environmentId** : Valeur de `TEST_FORMBRICKS_EVENT_FORM`
- **trigger_name** : "event_booking"
- **Produit** : Billet avec formulaire Formbricks

#### Événement
- **Nom** : "Atelier participatif avec formulaire personnalisé"
- **Date** : future_datetime('+10d') + 360 jours
- **Jauge max** : 30
- **Max par utilisateur** : 2
- **Description courte** : "Démonstration d'un événement avec formulaire Formbricks"
- **Description longue** : "Cet événement est une démonstration de l'intégration avec Formbricks. Après la réservation, un formulaire personnalisé sera présenté pour recueillir des informations supplémentaires sur vos préférences et besoins."
- **Catégorie** : `Event.CONFERENCE`
- **Adresse** : postal_address (Manapany)
- **Tags** : Formulaire
- **Produits** : Billet avec formulaire Formbricks

### 8.2 Adhésion avec formulaire Formbricks

#### Produit
- **Nom** : "Adhésion avec formulaire personnalisé"
- **Description courte** : "Démonstration d'une adhésion avec formulaire Formbricks"
- **Description longue** : "Cette adhésion est une démonstration de l'intégration avec Formbricks. Après l'achat, un formulaire personnalisé sera présenté pour recueillir des informations supplémentaires sur le nouvel adhérent."
- **Catégorie** : `Product.ADHESION`

#### Tarifs
1. **Annuelle**
   - Prix : 25€
   - Paiement récurrent : Non
   - Type : `Price.YEAR`

2. **Mensuelle**
   - Prix : 3€
   - Paiement récurrent : Oui
   - Type : `Price.MONTH`

#### Formulaire Formbricks
- **Modèle** : `FormbricksForms`
- **environmentId** : Valeur de `TEST_FORMBRICKS_ADH_FORM`
- **trigger_name** : "membership_registration"
- **Produit** : Adhésion avec formulaire personnalisé

---

## Résumé des modèles utilisés

- **Client** : Gestion des tenants
- **Domain** : Domaines associés aux tenants
- **TibilletUser** : Utilisateurs administrateurs
- **Configuration** : Configuration générale du tenant
- **PostalAddress** : Adresses postales
- **FormbricksConfig** : Configuration Formbricks
- **FedowConfig** : Configuration Fedow
- **AssetFedowPublic** : Assets Fedow
- **OptionGenerale** : Options pour les produits
- **Product** : Produits (adhésions, billets, badges)
- **Price** : Tarifs des produits
- **ProductFormField** : Champs de formulaire personnalisés
- **Event** : Événements
- **Tag** : Tags pour les événements
- **FormbricksForms** : Formulaires Formbricks

---

## Variables d'environnement utilisées

- **SUB** : Nom du schema du tenant principal
- **DOMAIN** : Domaine de base pour les tenants
- **ADMIN_EMAIL** : Email de l'administrateur
- **TEST_STRIPE_CONNECT_ACCOUNT** : Compte Stripe Connect de test
- **TEST_FORMBRICKS_API** : Clé API Formbricks (optionnel)
- **TEST_FORMBRICKS_EVENT_FORM** : ID du formulaire Formbricks pour événements (optionnel)
- **TEST_FORMBRICKS_ADH_FORM** : ID du formulaire Formbricks pour adhésions (optionnel)

---

## Notes pour les tests E2E Playwright

Pour reproduire ces opérations via un navigateur avec Playwright, les tests devront :

1. **Se connecter en tant qu'administrateur**
2. **Accéder aux interfaces d'administration** pour créer/modifier :
   - Configuration générale
   - Adresses postales
   - Options générales
   - Produits et tarifs
   - Événements et tags
   - Formulaires personnalisés
3. **Vérifier la création correcte** des éléments via les interfaces publiques
4. **Tester les flux utilisateur** :
   - Réservation d'événements gratuits
   - Réservation d'événements payants
   - Souscription à des adhésions
   - Remplissage de formulaires dynamiques
   - Sélection d'options (radio/checkbox)
   - Badgeage

Les tests devront être organisés par fonctionnalité et reproduire fidèlement le comportement du script pour garantir que l'application fonctionne correctement dans un contexte réel d'utilisation via navigateur.
