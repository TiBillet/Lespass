# Onboarding — recensement Tiers-Lieux + restructuration des étapes

**Date :** 2026-06-07
**Migration :** Oui

## Ce qui a été fait
Le wizard `/onboard/` passe de 6 à 7 étapes :
`Identité → Vérification email → **Votre lieu** (nouveau) → **Adresse** (optionnelle) → Présentation → Évènements → Lancement`.

- **Identité** : ne demande plus le nom du lieu ni le domaine (juste prénom/nom/email/CGU).
- **Votre lieu** (nouveau) : recherche Tiers-Lieux (débounce + spinner) + nom + **slug DNS éditable
  (pré-rempli du nom) + .coop/.re**. « Utiliser ce lieu » pré-remplit le nom et garde l'adresse.
- **Adresse** : optionnelle, carte pré-remplie depuis la fiche TL, bouton « Je ne renseigne pas d'adresse ».

Spec/code : voir CHANGELOG (entrée « Recensement Tiers-Lieux + restructuration des étapes »).

### ⚠️ Migration
`docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations MetaBillet`
puis `migrate_schemas`. (Changement de `choices` sur `current_step` — pas de SQL.)

## Tests à réaliser (manuel, sur `https://tibillet.localhost/onboard/identity/`)

### Test 1 — Identité allégée
1. Page 1 : vérifier qu'il n'y a **plus** de « Nom du collectif/lieu » ni « Nom de domaine ».
2. Remplir prénom/nom/email (×2)/CGU → Continuer → page OTP (Étape 2/7).

### Test 2 — OTP (dev) → Votre lieu
1. En dev (`DEBUG=True`), saisir n'importe quel code 6 chiffres → Vérifier.
2. **Attendu** : Étape 3/7 « Votre lieu ».

### Test 3 — Recherche Tiers-Lieux + domaine
1. Taper « raffinerie » dans la recherche → fiche « La Raffinerie » (spinner pendant l'appel).
2. Cliquer « Utiliser ce lieu » → le nom se remplit, le slug devient « la-raffinerie »,
   l'aperçu « la-raffinerie.tibillet.coop ».
3. Modifier le slug à la main / basculer .re → l'aperçu suit.
4. Continuer → Étape 4/7 « Adresse ».

### Test 4 — Adresse optionnelle
1. **Attendu** : carte pré-remplie depuis la fiche (marqueur + champs rue/CP/ville).
2. Cliquer « Je ne renseigne pas d'adresse » → Étape 5/7 « Présentation » (adresse passée).
3. Variante : placer un marqueur puis « Continuer » → adresse enregistrée.

### Test 5 — Nom déjà pris
1. À l'étape « Votre lieu », saisir un nom de tenant existant (ex « LESPASS ») → 422 sur le nom.

## Tests automatiques
```bash
docker exec lespass_django poetry run pytest onboard/tests/ -q
```
(58 passés + 2 skipped ; 3 tests adaptés au nouveau flux.)

## Compatibilité
- Le brouillon `WaitingConfiguration` est créé avec `organisation=""` à l'identité, complété à
  l'étape « Votre lieu ». Le launch (création tenant) reçoit nom + slug + domaine comme avant.
- L'adresse est déjà `null=True` sur le modèle : la rendre optionnelle ne casse rien.
