---
apply: always
---

# 🧪 Guide des Tests - Lespass (TiBillet) / Tests Guide

Bienvenue dans le dossier des tests du projet Lespass !
*Welcome to the test folder of the Lespass project!*

Ce document explique comment vérifier que l'application fonctionne bien.
Il est écrit pour être facile à comprendre, même si vous débutez.
*This document explains how to check if the app works correctly. It is easy to read, even for beginners.*

---

## 🛠️ Deux types de tests / Two types of tests

Nous avons deux façons de tester l'application :
*We have two ways to test the application:*

1. **Tests API (Backend)** : On teste les données et les serveurs (Rapide).
   *On utilise `pytest`.*
2. **Tests Bout-en-bout (Frontend/E2E)** : On simule un utilisateur sur un navigateur (Chrome/Firefox).
   *On utilise `playwright`.*

---

## 🚀 1. Tests API (Backend) - Pytest

Ces tests vérifient que le serveur répond correctement aux demandes de données.
*These tests check that the server responds correctly to data requests.*

### Comment les lancer ? / How to run them?

Vous devez être à la racine du projet (là où il y a le fichier `pyproject.toml`).
*Run these from the project root:*

```bash
# Lancer tous les tests API direct depuis l'hote, pas besoin d'entrer dans le conteneur
# Run all API tests
uv run pytest tests/pytest/

# Lancer uniquement les tests d'integration API v2
# Run only API v2 integration tests
uv run pytest -m integration tests/pytest/
```

### Ce qu'ils testent / What they check:

- La création et la suppression d'événements.
- La gestion des adresses postales.
- La création et la lecture des reservations (schema.org/Reservation).
- La création et la lecture des adhésions (schema.org/ProgramMembership).

### TEST A FAIRE (Terminés / Completed) :

- Lister les ventes
- Lister les reservations et les billets
- Lister les adhésions

---

## 🎭 2. Tests Navigateur (Frontend) - Playwright

Ces tests ouvrent un vrai navigateur et cliquent sur les boutons comme un humain.
*These tests open a real browser and click buttons like a human would.*

### Prérequis / Prerequisites

Il faut avoir installé les outils Node.js (Yarn).
*You need Node.js tools (Yarn) installed.*

```bash
cd tests/playwright
yarn install
yarn playwright install
```

### Comment les lancer ? / How to run them?

Allez dans le dossier `tests/playwright` :
*Go to the `tests/playwright` folder:*

```bash
# Lancer tous les tests (recommandé)
# Run all tests (recommended)
yarn test:chromium:console --workers=1

# Voir ce qui se passe en temps réel (Mode "Headed")
# See what happens in real time
DEBUG=pw:api yarn playwright test --project=chromium --headed --workers=1 tests/01-login.spec.ts

# Pour lancer avec tout des logs verbeux :
DEBUG=pw:api yarn playwright test --project=chromium --workers=1 tests/25-product-duplication-complex.spec.ts
```

Note:
- Some E2E tests create Products/Events via API v2 before running.
- The API key is generated at test startup (Playwright `global-setup`) and injected in `process.env.API_KEY`.
- API v2 can now set `membershipRequiredProduct` and recurring fields on offers.
- API v2 now supports creating Reservations and Memberships (schema.org) for test setup.
 
Note API (pytest):
- Les tests utilisent `verify=False` pour HTTPS local. Les warnings TLS sont filtres via `pytest.ini`.

### Ce qu'ils testent / What they check:

Les tests sont numérotés dans l'ordre logique :
*Tests are numbered in logical order:*

1. `01-login.spec.ts` : Vérifie que l'on peut se connecter.
2. `02-admin-configuration.spec.ts` : Vérifie que l'on peut changer le nom de l'asso.
3. `03-memberships.spec.ts` : Crée une adhésion simple.
4. `04-membership-recurring.spec.ts` : Crée une adhésion avec paiement tous les mois.
5. `05-membership-validation.spec.ts` : Crée une adhésion qui demande l'accord d'un admin.
6. `06-membership-amap.spec.ts` : Crée un panier légume (AMAP) avec options.
7. `07-fix-solidaire-manual-validation.spec.ts` : Modifie un tarif existant.
8. `08-membership-ssa-with-forms.spec.ts` : Crée un produit complexe avec un questionnaire.
9. `09-anonymous-events.spec.ts` : Réservation d'événements gratuit et payant (Anonyme) + Vérification DB.
10. `10-anonymous-event-dynamic-form.spec.ts` : Réservation payante avec formulaire dynamique + Vérification DB.
11. `11-anonymous-membership.spec.ts` : Achat d'adhésion standard + Vérification DB.
12. `12-anonymous-membership-dynamic-form.spec.ts` : Achat d'adhésion avec formulaire dynamique + Vérification DB.
13. `13-ssa-membership-tokens.spec.ts` : Adhésion SSA, paiement Stripe et vérification des jetons (MonaLocalim) dans la
    tirelire et en DB.
14. `14-membership-manual-validation.spec.ts` : Demande d'adhésion soumise à validation, puis approbation par
    l'administrateur dans le panel admin.
15. `15-membership-free-price.spec.ts` : Achat d'adhésion à prix libre et vérification du montant sur Stripe.
16. `16-user-account-summary.spec.ts` : Vérification que toutes les adhésions et réservations d'un utilisateur sont bien
    listées dans son compte.
17. `17-membership-free-price-multi.spec.ts` : Achat d'adhésion sur un produit à plusieurs prix libres (vérification de
    la non-collision des montants et de la réinitialisation des champs).
18. `18-reservation-validations.spec.ts` : Vérifie les erreurs de formulaire sur réservation (email, prix libre, champs
    dynamiques, code promo).
19. `19-reservation-limits.spec.ts` : Vérifie stock épuisé, max par utilisateur, et tarif réservé aux adhésions.
20. `20-membership-validations.spec.ts` : Vérifie les erreurs de formulaire d'adhésion (email, prix libre, champs
    dynamiques).
21. `21-membership-account-states.spec.ts` : Vérifie "déjà actif" et "expiré + renew" dans le compte.
22. `22-membership-recurring-cancel.spec.ts` : Vérifie l'affichage du bouton d'annulation récurrente et le message d'erreur.
23. `23-crowds-participation.spec.ts` : Vérifie le flux de participation aux projets Crowds (pro-bono, règles, durée).
24. `24-crowds-summary.spec.ts` : Vérifie l'affichage du résumé financier et temporel dans Crowds.

### TODO E2E a couvrir / TODO E2E to cover

Ces points sont des comportements visibles dans les pages "reservation" et "adhesion".
*These are behaviors visible in "reservation" and "membership" pages.*

- Reservation: page "reservation_ok" (email valide vs email non valide).  
  *Reservation: "reservation_ok" page (valid email vs unconfirmed email).*
- Reservation: event complet (sold out).  
  *Reservation: sold out event.*
- Reservation: flow Formbricks pour event.  
  *Reservation: Formbricks flow for event.*
- Reservation: annulation d'une reservation et d'un ticket depuis "Mon compte".  
  *Reservation: cancel a reservation and a ticket from "My account".*
- Reservation: affichage et ouverture des tickets dans "Mon compte".  
  *Reservation: display and open tickets in "My account".*

- Adhesion: prix libre multiple -> affiche/masque champ montant, erreurs.  
  *Membership: multiple free prices -> show/hide amount field, errors.*
- Adhesion: prix hors stock et max_per_user atteint (message).  
  *Membership: out of stock and max_per_user reached (message).*
- Adhesion: flow Formbricks.  
  *Membership: Formbricks flow.*
- Adhesion: validation manuelle -> page "pending_manual_validation".  
  *Membership: manual validation -> "pending_manual_validation" page.*
- Adhesion: statut recurrent (actif / annule) dans "Mon compte" avec annulation reussie.  
  *Membership: recurring status (active / canceled) with successful cancel.*
- Adhesion: page "embed" et redirection vers tenant federation.  
  *Membership: embed page and federated tenant redirect.*
- Adhesion: retours Stripe (valid / pending / error).  
  *Membership: Stripe returns (valid / pending / error).*

### Vérification en Base de Données (DB) / Database Verification

Pour garantir que les tests ne sont pas de simples "façades" visuelles, nous utilisons une commande Django personnalisée
appelée depuis les tests Playwright via Docker :
*To ensure tests are not just visual "façades", we use a custom Django command called from Playwright tests via Docker:*

```bash
docker exec lespass_django uv run manage.py verify_test_data --type reservation --email <EMAIL>
```

Cette commande permet de confirmer que les données (réservations, adhésions, formulaires) sont correctement enregistrées
dans la base de données PostgreSQL du conteneur.

### Setup DB pour les tests / DB setup for tests

Pour préparer des cas specifiques (stock, max par utilisateur, adhesion obligatoire), on utilise un script de setup :
*To prepare specific cases (stock, max per user, membership required), we use a setup script:*

```bash
docker exec -w /DjangoFiles -e PYTHONPATH=/DjangoFiles lespass_django \
  uv run tests/scripts/setup_test_data.py --action create_ticket \
  --event "<EVENT>" --product "<PRODUCT>" --price "<PRICE>" --email "<EMAIL>" --qty 1
```

### TEST A FAIRE (Terminés / Completed) :

#### Anonyme ( utilise l'email jturbeaux+<uuid8 aleatoire>@pm.me ) :

- ✅ reserver un evenement gratuit (Disco Caravane), message "merci de valider votre email" vérifié + DB.
- ✅ reserver un evenement payant (What the Funk), paiement Stripe 4242 vérifié + DB.
- ✅ reserver un evenement payant avec un formulaire dynamique + DB.
- ✅ prendre une adhésion et payer sur stripe avec la carte bancaire 4242 + DB.
- ✅ prendre une ahdésion avec un formulaire dynamique et payer sur stripe avec la carte bancaire 4242 + DB.
- ✅ prendre une adhésion caisse sociale alimentaire et payer sur stripe avec la carte bancaire 4242, se connecter et
  vérifier qu'on a bien reçu les token dans la partie mon compte / ma tirelire + DB.
- ✅ prendre une adhésion a validation manuelle, se connecter en tant qu'admin et accepter l'adhésion + DB.
- ✅ prendre une ahdésion a prix libre, vérifier que le tarif sur stripe est bien le prix libre.
- ✅ prendre une ahdésion a prix libre, vérifier que le tarif sur stripe est bien le prix libre, payer + DB.
- ✅ prendre une adhésion sur un produit multi-prix libre, vérifier que les montants ne se mélangent pas et que les
  champs se réinitialisent.
- ✅ se connecter, aller sur mon compte et vérifier que toute les adhésions et les reservations sont présentes.

Sur stripe, on peut payer avec la carte 4242 4242 4242 4242, nom : Douglas Adams, date : 12/42 et code 424
les events sont sur /events
vas y de façon incrémentielle et doucement, d'abord, réalise des curl pour comprendre la structure des pages. ensuite
fabrique le test.



---

## 📝 Règles d'or pour écrire des tests / Golden rules for writing tests

Si vous devez ajouter un test, suivez ces conseils :
*If you need to add a test, follow these tips:*

1. **Soyez Atomique** : Un test doit faire une seule chose précise.
   *One test = one specific action.*
2. **Soyez Verbeux** : Donnez des noms de fonctions longs et clairs.
   *Use long and clear function names.*
3. **Bilingue** : Écrivez les commentaires en Français et en Anglais.
   *Write comments in both French and English.*
4. **FALC** : Utilisez des mots simples pour que tout le monde comprenne.
   *Use simple words (Easy-to-read format).*
5. **Script post test** : Si vous avez besoin d'un script python pour vérifier la base de donnée après avoir fait un
   test E2E ou créer un objet au préalable, utilisez le dossier script en nommant verify_<nom du test>.py ou
   post_<nom du test>.py. Puis, lancez le avec docker exec lespass_django uv run manage.py tests/script/<nom du script>.py.
   *If you need a python script to verify the database after a test E2E, use the script folder and name it verify
   _<test name>.py.*

---

## 📊 État actuel des tests / Current status

| Type             | Succès / Passed | Échecs / Failed | Note            |
|:-----------------|:----------------|:----------------|:----------------|
| API (Pytest)     | ✅ 10            | 0               | Tout est vert ! |
| E2E (Playwright) | ✅ 16            | 0               | Tout est vert ! |

---

*Ce document est un commun numérique. Prenez-en soin !*
*This document is a digital common. Take care of it!*
