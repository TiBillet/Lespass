# Playwright E2E Tests for Lespass

Ce dossier contient les tests end-to-end (E2E) utilisant Playwright pour reproduire et valider les opérations du script `demo_data.py`.

## Structure du projet

```
tests/playwright/
├── README.md                      # Ce fichier
├── package.json                   # Dépendances Node.js et scripts npm
├── playwright.config.ts           # Configuration Playwright
├── demo_data/
│   └── demo_data_operations.md   # Documentation des opérations à reproduire
└── tests/
    ├── 01-login.spec.ts          # Test du flow de connexion
    └── utils/
        └── env.ts                 # Helper pour les variables d'environnement
```

## Prérequis

- Node.js (version 18 ou supérieure recommandée)
- yarn
- Le fichier `.env` configuré à la racine du projet Lespass
- Le serveur de développement Lespass en cours d'exécution

## Installation

1. Naviguer vers le dossier playwright :
```bash
cd /home/jonas/TiBillet/dev/Lespass/tests/playwright
```

2. Installer les dépendances :
```bash
yarn install
```

3. Installer les navigateurs Playwright :
```bash
yarn playwright install
```

## Configuration

Les tests utilisent les variables d'environnement du fichier `.env` situé à la racine du projet :
- `ADMIN_EMAIL` : Email de l'administrateur
- `DOMAIN` : Domaine de base (ex: tibillet.localhost)
- `SUB` : Sous-domaine du premier tenant (ex: lespass)
- `TEST` : Mode test (1 pour actif)

Le fichier `playwright.config.ts` charge automatiquement ces variables.

## Exécution des tests

### Lancer tous les tests (mode headless)
```bash
yarn test
```

### Lancer les tests avec interface graphique (headed mode)
```bash
yarn test:headed
```

### Lancer les tests en mode debug
```bash
yarn test:debug
```

### Lancer les tests en mode UI interactif
```bash
yarn test:ui
```

### Lancer les tests sur un navigateur spécifique
```bash
yarn test:chromium
yarn test:firefox
yarn test:webkit
```

### Lancer les tests avec sortie console uniquement (sans serveur HTML)
Ces commandes affichent les résultats directement dans le terminal, sans ouvrir de serveur pour le rapport HTML :
```bash
yarn test:console              # Tous les tests avec sortie console
yarn test:firefox:console      # Tests Firefox avec sortie console
yarn test:chromium:console     # Tests Chromium avec sortie console
```

**Avantages de la sortie console :**
- Résultats lisibles immédiatement dans le terminal
- Pas besoin d'ouvrir un navigateur pour voir le rapport
- Idéal pour les environnements CI/CD et l'automatisation
- Affichage détaillé des étapes, assertions et erreurs

### Voir le rapport HTML
```bash
yarn report
```

### Générer du code de test avec Codegen
```bash
yarn codegen
```

## Tests disponibles

### 01-login.spec.ts
Test du flow de connexion complet (première étape de la configuration générale) :
- Navigation vers la page d'accueil
- Clic sur le bouton "Connexion" / "Log in"
- Remplissage de l'email administrateur
- Soumission du formulaire de connexion
- Clic sur le lien TEST MODE pour simuler la connexion par email
- Navigation vers la page /my_account
- Vérification que le panneau d'administration est visible (droits admin)
- Validation du format d'email (test séparé)

### 02-admin-configuration.spec.ts
Test de la configuration générale de l'organisation (Section 2 de demo_data_operations.md) :
- Connexion en tant qu'administrateur
- Navigation vers le panneau d'administration (/admin/)
- Accès à la page de configuration
- Vérification et remplissage des champs de configuration :
  - Nom de l'organisation
  - Description courte
  - Description longue
  - Téléphone
  - Email
  - Site web
- Sauvegarde de la configuration
- Vérification que la configuration est visible sur la page d'accueil

## Développement de nouveaux tests

Pour créer un nouveau test :

1. Créer un fichier dans `tests/` avec l'extension `.spec.ts`
2. Importer les dépendances nécessaires :
   ```typescript
   import { test, expect } from '@playwright/test';
   import { env } from './utils/env';
   ```
3. Utiliser `test.describe()` pour grouper les tests
4. Utiliser `test.step()` pour organiser les étapes de test
5. Utiliser les assertions Playwright pour vérifier les comportements

Exemple :
```typescript
import { test, expect } from '@playwright/test';
import { env } from './utils/env';

test.describe('Ma fonctionnalité', () => {
  test('devrait faire quelque chose', async ({ page }) => {
    await test.step('Étape 1', async () => {
      await page.goto('/');
      // ... assertions
    });
  });
});
```

## Variables d'environnement disponibles

Le module `tests/utils/env.ts` fournit un accès type-safe aux variables :
- `env.ADMIN_EMAIL` : Email de l'admin
- `env.DOMAIN` : Domaine
- `env.SUB` : Sous-domaine
- `env.BASE_URL` : URL complète (https://SUB.DOMAIN)
- `env.TEST` : Mode test (boolean)
- `env.DEBUG` : Mode debug (boolean)
- `env.STRIPE_TEST` : Mode test Stripe (boolean)

## Roadmap

D'après le document `demo_data/demo_data_operations.md`, les prochains tests à implémenter sont :

1. ✅ Section 1 : Initialisation et configuration des tenants (via `demo_data_minimal.py`)
2. ✅ Section 2 : Authentification et vérification des droits admin (login flow complet)
3. ✅ Section 3 : Configuration générale de l'organisation (champs principaux : nom, descriptions, contact)
   - ⏳ Création des adresses postales
   - ⏳ Configuration de Formbricks
   - ⏳ Liaison avec Fedow
4. ⏳ Section 4 : Création des options générales
5. ⏳ Section 5 : Produits d'adhésion (Memberships)
6. ⏳ Section 6 : Produit de badgeuse (Co-working)
7. ⏳ Section 7 : Création des tags d'événements
8. ⏳ Section 8 : Événements
9. ⏳ Section 9 : Intégration Formbricks (optionnelle)

## Ressources

- [Documentation Playwright](https://playwright.dev/)
- [API Reference Playwright](https://playwright.dev/docs/api/class-playwright)
- [Best Practices](https://playwright.dev/docs/best-practices)

## Troubleshooting

### Les tests échouent avec des erreurs HTTPS
- Vérifier que `ignoreHTTPSErrors: true` est bien configuré dans `playwright.config.ts`

### Les tests ne trouvent pas les éléments
- Utiliser `yarn test:headed` pour voir visuellement ce qui se passe
- Utiliser `yarn test:debug` pour débugger pas à pas
- Vérifier que le serveur de développement est bien lancé

### Les variables d'environnement ne sont pas chargées
- Vérifier que le fichier `.env` existe à la racine du projet
- Vérifier que les variables sont bien définies dans le fichier
- Relancer les tests après modification du `.env`
