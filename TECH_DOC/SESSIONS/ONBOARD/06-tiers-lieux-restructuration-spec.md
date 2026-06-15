# ONBOARD — 06 · Intégration Tiers-Lieux + restructuration des étapes

**Date :** 2026-06-05
**App :** onboard (+ MetaBillet.WaitingConfiguration, BaseBillet.services.tiers_lieux)
**Statut :** implémenté, vérifié end-to-end (Chrome), tests onboard 58 OK
**API externe :** https://api.tiers-lieux.fr/ (recensement national)

---

## 1. Objectif

Faciliter la création d'un espace (onboarding d'un nouveau tenant) en s'appuyant sur le
recensement national Tiers-Lieux, et fiabiliser le parcours :

- l'identité ne demande plus le nom du lieu ni le domaine ;
- une nouvelle étape « Votre lieu » récupère le nom (recensement ou saisie) + le domaine ;
- l'adresse devient optionnelle.

---

## 2. Nouveau flux (7 étapes)

```
1. Identité       prénom, nom, email, CGU                 (— nom du lieu, — domaine)
2. Vérification   OTP email
3. Votre lieu     recherche Tiers-Lieux → nom + slug DNS éditable (.coop/.re)   [NOUVELLE]
4. Adresse        ex-« Votre lieu », OPTIONNELLE, pré-remplie depuis l'étape 3
5. Présentation   accroche + description + logo
6. Évènements     (masquée du parcours par défaut)
7. Lancement      création du tenant
```

`STEP_ORDER` (templatetag) et `STEP_TO_URL_NAME` (views) incluent désormais `venue` entre
`verify` et `place`.

---

## 3. Décisions (validées avec le mainteneur)

| # | Point | Décision |
|---|---|---|
| 1 | Nom du lieu | Saisi à l'étape « Votre lieu » (recensement ou manuel). Le brouillon est créé à l'identité avec `organisation=""`, complété à venue |
| 2 | Domaine | Slug **éditable pré-rempli depuis le nom** (live JS) + suffixe **.coop / .re**, sur l'étape « Votre lieu », sous le nom |
| 3 | Position | La recherche vient **après** la vérification email (OTP) |
| 4 | Adresse | Optionnelle : bouton « Je ne renseigne pas d'adresse » ; champs déjà `null=True` sur le modèle |
| 5 | Recherche par email | Impossible (l'API Tiers-Lieux ne cherche pas par email) → recherche par nom/ville/CP |

---

## 4. Architecture

### Service partagé (réutilisé du wizard event)
`BaseBillet/services/tiers_lieux.py` : `rechercher_tiers_lieux(terme, limite)` — timeout 4 s,
`try/except → []`, cache 1 h, normalisation vers champs PostalAddress. **Ne lève jamais.**

### Modèle
`MetaBillet.WaitingConfiguration` : `STEP_VENUE = "venue"` ajouté à `STEP_CHOICES` (libellé
`STEP_PLACE` → « Address »). Champs réutilisés : `organisation`, `slug`, `dns_choice`, `adress`/
`postal_code`/`city`/`latitude`/`longitude` (déjà nullable).

### Vues (`OnboardViewSet`, `@action`)
- `venue` (GET/POST) : garde OTP (`_get_confirmed_wc_or_redirect`). POST → `OnboardVenueSerializer`
  → `update(organisation, slug, dns_choice, current_step=PLACE)` + session `onboard_venue_prefill`
  (dict de la fiche choisie : `latitude`, `longitude`, `street_address`, `postal_code`,
  `address_locality`, `adresse_recherche`) → redirect place.
- `venue_search` (GET) : `rechercher_tiers_lieux(q)` (si `len(q)≥3`) → partial `venue_tierslieux.html`.
- `place` : détecte « passer » (`skip_address`) ou absence de position GPS → avance sans adresse ;
  sinon valide. GET passe `onboard_venue_prefill` au widget : si la fiche a un GPS, le widget pose
  le marqueur + remplit les champs **directement** (sans Nominatim) ; sinon `adresse_recherche`
  sert de repli pour la recherche Nominatim.
- `identity` : crée le brouillon avec `organisation=""`, `dns_choice=None`, route OTP→venue.

### Serializers
- `OnboardIdentitySerializer` : retrait de `name`/`dns_choice`/`validate_name`.
- `OnboardVenueSerializer` (nouveau) : `name` (+ check unicité déplacé) + `slug` (SlugField) + `dns_choice`.

### Templates
- `steps/01_identity.html` : retrait des blocs nom + domaine, compteur 1/7.
- `steps/03_venue.html` (nouveau) : recherche TL (débounce + spinner) + nom + slug DNS éditable +
  .coop/.re + aperçu live ; JS inline (slugify + remplissage depuis fiche).
- `partials/venue_tierslieux.html` (nouveau) : fiches → bouton « Utiliser ce lieu » (remplit le form via JS).
- `steps/03_place.html` : « Adresse » 4/7, optionnelle, pré-remplie, bouton « passer », précédent→venue.
- `partials/progress_panel.html` + compteurs des steps : flux 7 étapes.

---

## 5. Revue post-implémentation — points traités (2026-06-05)

> ⚠️ **Bug découvert pendant la revue** : `TenantCreateValidator.create_tenant` construisait le
> domaine avec `slug = slugify(name)` — le **slug éditable saisi à l'étape venue (`wc.slug`)
> était ignoré au Lancement**. Corrigé : `slug = waiting_config.slug or slugify(name)`
> (`BaseBillet/validators.py`). Le slug éditable est donc désormais réellement utilisé.

1. ✅ **Unicité du slug/domaine** : `OnboardVenueSerializer.validate` vérifie maintenant que le
   domaine `{slug}.{dns}` (avec `dns="tibillet.localhost"` en DEBUG, comme au Lancement) n'est pas
   déjà pris (`Domain.objects.filter(domain=…)`). Conflit détecté à l'étape venue, plus au Lancement.
2. ✅ **`check-instance` (wizard event)** : rate-limit par IP (20/min, clé tenant-scopée, réponse
   vide silencieuse au-delà) — limite l'énumération email→instance.
3. ✅ **Duplication JS** : util partagé `BaseBillet/static/js/tierslieux_search.js`
   (`creerRechercheTiersLieux` : débounce + spinner) utilisé par `_form_lieu.html` ET `03_venue.html`.
   `slugify` exposé en `window.tibilletSlugify` (wizard.js) et réutilisé par `03_venue.html`.
4. ✅ **Code mort** : `wizard.js::setupDomainPreview()` (inactif sur l'identité) retiré.
5. ✅ **Tests** : `onboard/tests/test_step_venue.py` (GET, POST valide→redirect, nom pris, domaine
   pris, adresse TL en session, place skip). Refactor JS revalidé end-to-end dans Chrome.

### Dette restante (non traitée, accord mainteneur)
- **Bouton « Continuer » `disabled` en HTML** (wizard event) : un visiteur sans JS ne peut pas
   soumettre. Acceptable (le wizard exige déjà JS pour le toggle).

---

## 6. Migration & i18n
- Migration `MetaBillet 0017` (changement de `choices` sur `current_step`) — pas de SQL.
- Nombreux nouveaux `{% translate %}` (texte source FR) → `makemessages` / `compilemessages`.
