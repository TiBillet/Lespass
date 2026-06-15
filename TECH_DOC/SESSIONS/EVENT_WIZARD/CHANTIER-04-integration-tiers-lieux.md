# CHANTIER-04 — Intégration API Tiers-Lieux dans le wizard event (étape 1)

**Date :** 2026-06-05
**App :** BaseBillet (wizard event front) + FederationConfiguration
**Statut :** spec validée, implémentation en cours
**API externe :** https://api.tiers-lieux.fr/ (recensement national des tiers-lieux)

---

## 1. Objectif

Enrichir l'étape 1 du wizard de proposition d'évènement (`event-wizard-place`) pour
un visiteur **anonyme**, afin de :

1. **Détecter son instance** : si son email correspond à un compte qui administre
   déjà un tenant TiBillet, l'inviter (non-bloquant) à créer son évènement chez lui
   + ajouter le(s) tag(s) que ce tenant fédère + proposer son instance à la fédération.
2. **Retrouver son lieu** dans le recensement national Tiers-Lieux quand aucune
   adresse locale ne correspond, et pré-remplir la création d'un nouveau lieu.

But métier : faciliter la remontée des évènements d'autres tiers-lieux dans
l'agenda du tenant courant (cf. fédération automatique par tags, CHANTIER FEDERATION).

---

## 2. Décisions (validées avec le mainteneur)

| # | Point | Décision | Raison |
|---|---|---|---|
| 1 | Email → instance | Via `TibilletUser.client_admin` (compte admin) | Plus précis que `Configuration.email` pour « c'est MON instance » |
| 2 | Recherche instance — affichage | **Encart informatif non-bloquant** | L'anonyme ne peut pas agir sur la fédération ; on informe sans forcer |
| 3 | Clé de recherche Tiers-Lieux | **Champ « nom/ville/CP » existant** | L'API ne retrouve PAS un lieu par email (testé : `q=email` matche n'importe quoi via Meilisearch). L'email ne sert qu'à la détection d'instance |
| 4 | Déclenchement Tiers-Lieux | **Auto débounce 600 ms, seulement si 0 adresse locale** | Évite les appels API inutiles et le doublon local/national |
| 5 | Fiche Tiers-Lieux retenue | Pré-remplit le « nouveau lieu » + **validation à l'étape carte** | On réutilise l'étape carte existante, sans retape ni géocodage |

### Fait technique vérifié (test API réel)

- `GET /search?q=contact@laraffinerie.re` → renvoie « LE BERCAIL », « Terres de Baume Rousse » (**PAS** La Raffinerie). La recherche par email est inutilisable.
- `GET /search?q=raffinerie` → renvoie « La Raffinerie » correctement. La recherche par nom fonctionne.

---

## 3. Flow (étape 1, visiteur anonyme)

```
1. Saisie email
   └─(blur)─> HTMX check-instance
              ├─ instance(s) trouvée(s) -> encart non-bloquant (lien wizard de son
              │   instance + tag(s) tags_federation du tenant courant + invitation
              │   fédération si pas déjà membre)
              └─ aucune -> conteneur reste vide

2. Recherche d'adresse (champ nom/ville/CP)
   ├─ filtre JS local instantané (existant)
   ├─ si >=1 résultat local -> on s'arrête là (sélection radio classique)
   └─ si 0 résultat local ET terme >= 3 car. -> (débounce 600 ms) HTMX search-tierslieux
        ├─ fiche(s) trouvée(s) -> encart « recensement Tiers-Lieux »
        │     └─ « Utiliser ce lieu » -> POST use-tierslieux -> session prefill
        │        -> redirection étape carte pré-remplie -> validation
        └─ aucune -> message « créez via Créer un nouveau lieu »
```

---

## 4. Architecture / fichiers

### Nouveaux

| Fichier | Rôle |
|---|---|
| `BaseBillet/services/__init__.py` | package services |
| `BaseBillet/services/tiers_lieux.py` | client API : `rechercher_tiers_lieux(terme, limite)` + normalisation + timeout + cache |
| `…/wizard/_instance_trouvee.html` | partial encart instance |
| `…/wizard/_tierslieux_resultats.html` | partial fiches Tiers-Lieux |
| `tests/pytest/test_tiers_lieux.py` | tests service + endpoints |

### Modifiés

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | 3 `@action` sur `EventWizard` (`check-instance`, `search-tierslieux`, `use-tierslieux`) + lecture `tierslieux_prefill` dans `_wizard_etape_carte_lieu` |
| `…/wizard/_form_lieu.html` | conteneurs `#wizard-instance-result` / `#wizard-tierslieux-result` + câblage HTMX email + JS débounce conditionnel |
| `…/wizard/_form_carte.html` | pré-remplissage des champs depuis `tierslieux_prefill` (initial) |
| `CHANGELOG.md`, `A TESTER et DOCUMENTER/` | doc |

---

## 5. Service `tiers_lieux.py`

```
TIERS_LIEUX_API_BASE = "https://api.tiers-lieux.fr"
TIMEOUT_SECONDES = 4
CACHE_TTL = 3600  # 1h, donnée nationale publique (clé NON tenant-scopée, documenté)

def rechercher_tiers_lieux(terme, limite=5) -> list[dict]:
    # cache.get(f"tierslieux:search:{terme}:{limite}")
    # GET {base}/search?q={terme}&limit={limite}, timeout=4s
    # try/except (Timeout, RequestException, ValueError) -> [] (jamais d'exception)
    # normalise chaque hit -> _normaliser_fiche(hit)
```

Mapping `_normaliser_fiche(hit)` :
- `name` ← `nom_tiers_lieu`
- `postal_code` ← `adresse_nationale_cp`
- `locality` ← `adresse_nationale_ville`
- `region` ← `adresse_nationale_region`
- `street_address` ← `adresse_nationale` sans le CP ni la ville (sinon `adresse_nationale` brut)
- `latitude` / `longitude` ← `adresse_nationale_lat` / `adresse_nationale_lon`
- `country` ← `"France"`
- `identifiant_national` ← `Identifiant_national`

---

## 6. Endpoints `EventWizard`

- `check-instance` (GET) : lit `email_proposeur`. `TibilletUser.objects.filter(email__iexact=email).first()`.
  Si user : `instances = user.client_admin.all()`. Pour chaque instance, on calcule (dans le
  contexte du tenant COURANT) les `tags_federation` à suggérer et si l'instance est déjà fédérée.
  Renvoie `_instance_trouvee.html` (ou réponse vide si 0 instance).
- `search-tierslieux` (GET) : lit `q`. Si `len(q.strip()) < 3` → vide. Sinon `rechercher_tiers_lieux(q)`
  → `_tierslieux_resultats.html`.
- `use-tierslieux` (POST) : reçoit les champs normalisés de la fiche. Stocke en session
  `tierslieux_prefill`. Redirige vers l'étape carte (`event-wizard-map`).

---

## 7. Sécurité / robustesse

- **API externe** : `timeout=4s` + `try/except` → `[]`. Le wizard ne casse jamais.
- **Énumération email→instance** (`check-instance`) : un anonyme peut tester un email et savoir
  s'il administre une instance + son nom. Risque limité (emails de contact souvent publics) mais
  réel. **MVP : accepté + log** ; rate-limit par IP possible en évolution si besoin. À signaler
  au mainteneur.
- **Cache** : clé Tiers-Lieux non tenant-scopée (donnée nationale partagée) — exception
  documentée à la règle « clé = tenant.pk ».
- **Validation conservée** : la fiche pré-remplie est validée par l'utilisateur à l'étape carte
  (serializer existant), comme une création de lieu normale.

---

## 8. Tests (pytest DB-only, requests mocké)

1. `rechercher_tiers_lieux` succès → liste normalisée (mock `requests.get`).
2. `rechercher_tiers_lieux` timeout / erreur réseau → `[]` (jamais d'exception).
3. `rechercher_tiers_lieux` cache hit → pas de 2e appel réseau.
4. `check-instance` : email d'un admin → encart contient le nom de l'instance.
5. `check-instance` : email sans instance / inconnu → réponse vide.
6. `search-tierslieux` : `q` court (<3) → vide ; `q` valide (service mocké) → fiches rendues.

---

## 9. i18n

Tous les nouveaux textes en **français** (`{% translate %}` / `_()`). `makemessages` /
`compilemessages` à la main du mainteneur après la feature.
