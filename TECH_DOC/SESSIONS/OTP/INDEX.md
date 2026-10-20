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
| 01 | Service OTP DRY stateless + helper session HTTP | ✅ Implémenté (2026-05-19). Helper session (`OtpSession`) supprimé le 2026-10-20 | [SPEC.md](SPEC.md) | [../EVENT_WIZARD/PLAN.md](../EVENT_WIZARD/PLAN.md) (session S1) |

> **Statut d'usage (2026-10-20)** — chantier AUTH, non commité :
> - `OtpSession` (`AuthBillet/otp_session.py`) est **supprimée**, avec ses 15 tests.
>   Les étapes `step0_verify` / `step0_resend` du wizard n'existent plus depuis le 2026-05-21.
> - La **connexion par code** utilise les fonctions pures de `otp_service.py`. Elle vit dans
>   `AuthBillet/connexion_par_code.py` (code en cache, plafonds) et dans le **guichet commun**
>   à tous les lieux (`AuthBillet/sso.py`, `AuthBillet/views_sso.py`, routes `/sso/…`).
>   Détail : [`../TODO/AUTH-connexion-par-code-achat-connecte.md`](../TODO/AUTH-connexion-par-code-achat-connecte.md).
> - L'empreinte du code est un HMAC-SHA256 avec la clé secrète (`salted_hmac`), plus un SHA-256 simple.
> - L'**onboarding garde son propre OTP** (`onboard/services.py`, `generate_otp` / `verify_otp`,
>   champs de `WaitingConfiguration`). Sa migration reste à faire : CHANTIER-03, toujours ouvert.

## Chantiers envisagés (non datés)

| Idée | Description |
|---|---|
| ~~CHANTIER-02 — Login OTP~~ | **Fait** par le chantier AUTH (2026-10-20) : code en cache Django (memcached), guichet commun. Voir la note ci-dessus. |
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
| Empreinte `salted_hmac` (HMAC-SHA256, clé secrète) + `hmac.compare_digest` | Constant-time, jamais de code en clair. SHA-256 simple remplacé le 2026-10-20 (un million de codes : une copie du cache suffisait) | Chantier 01, chantier AUTH (D10) |
| Templates email génériques paramétrés par `libelle_action` | Un seul couple `.html` / `.txt` pour tous les usages | Chantier 01 |
| Onboard reste indépendant tant qu'il marche | Migration optionnelle, future, jamais bloquante | Chantier 01 |
