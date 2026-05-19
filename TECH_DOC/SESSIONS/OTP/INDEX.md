# OTP — Hub permanent

**Date d'ouverture :** 2026-05-19

Ce hub regroupe tous les chantiers liés au **service OTP (One-Time Password) réutilisable** du projet Lespass.

## Périmètre fonctionnel

Le service OTP vit dans `AuthBillet/` et fournit une primitive d'authentification **stateless** : génération de codes 6 chiffres, hash, vérification constant-time, envoi email. L'appelant choisit où stocker le hash et l'expiration (session HTTP, modèle DB, cache Redis...).

Le service est conçu pour servir plusieurs cas d'usage :
- **Wizard public de proposition d'évènement** (premier consommateur, chantier 01)
- **Futur login OTP** (sans mot de passe, code par email à chaque connexion)
- **Futur SSO / OIDC** (étape de vérification email avant émission du token)
- **Migration onboard** (remplacer son OTP custom basé sur `WaitingConfiguration`)

## Suivi des chantiers

| # | Chantier | Statut | Spec | Plan |
|---|---|---|---|---|
| 01 | Service OTP DRY stateless + helper session HTTP | Plan rédigé, prêt à exécuter | [SPEC.md](SPEC.md) | [../EVENT_WIZARD/PLAN.md](../EVENT_WIZARD/PLAN.md) (session S1) |

## Chantiers envisagés (non datés)

| Idée | Description |
|---|---|
| CHANTIER-02 — Login OTP | Remplacer le formulaire de connexion classique par un flow OTP email. Réutilise le service. Stockage : `User.otp_hash` + `User.otp_expires_at` ou cache Redis. |
| CHANTIER-03 — Migration onboard | Remplacer la logique OTP custom de `onboard/services.py` (basée sur `WaitingConfiguration.otp_*` champs) par des appels au service. Trois lignes à changer. |
| CHANTIER-04 — Branchement SSO/OIDC | Étape de vérification email avant émission de l'access token, pour les flows OIDC où l'utilisateur n'a pas encore confirmé son adresse. |
| CHANTIER-05 — TOTP (RFC 6238) | Extension du service à des codes time-based pour 2FA via app authenticator (Google Authenticator, Authy). Réutilise les templates email pour les codes de récupération. |

## Comment ajouter un chantier futur

1. Créer `CHANTIER-NN-<slug>.md` à la racine du hub (slug kebab-case, ex: `CHANTIER-02-login-otp.md`).
2. Ajouter une ligne dans le tableau "Suivi des chantiers".
3. Si non trivial, dérouler un plan via `writing-plans` (fichiers `PLAN-SX-*.md`).

## Liens utiles

- Premier consommateur : [EVENT_WIZARD](../EVENT_WIZARD/INDEX.md) (chantier 01 utilise le service)
- App référence pour le pattern OTP actuel (à migrer) : `onboard/services.py` + `WaitingConfiguration` (schema `meta`)
- Module auth principal : `AuthBillet/` (SHARED_APPS — accessible depuis tout schema)
- Conventions de code : `GUIDELINES.md` (FALC) + skill `djc`

## Décisions structurantes globales (héritées des chantiers)

| Sujet | Décision | Source |
|---|---|---|
| Service stateless, l'appelant décide du stockage | Permet usage en session HTTP, modèle DB ou cache | Chantier 01 |
| Localisation `AuthBillet/` | SHARED_APPS donc accessible partout (tenants + meta) | Chantier 01 |
| Hash SHA-256 + `hmac.compare_digest` | Constant-time, jamais de code en clair en base/session | Chantier 01 |
| Templates email génériques paramétrés par `libelle_action` | Un seul couple `.html` / `.txt` pour tous les usages | Chantier 01 |
| Onboard reste indépendant tant qu'il marche | Migration optionnelle, future, jamais bloquante | Chantier 01 |
