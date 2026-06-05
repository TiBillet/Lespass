# Intégration recensement Tiers-Lieux dans le wizard d'évènement (CHANTIER-04)

## Ce qui a été fait

Étape 1 du wizard de proposition d'évènement (visiteur anonyme) enrichie :
- **Détection d'instance** par email (`User.client_admin`) → encart non-bloquant.
- **Recherche nationale Tiers-Lieux** (API publique) quand aucune adresse locale ne
  correspond → pré-remplissage du nouveau lieu + validation à l'étape carte.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/services/tiers_lieux.py` | Client API (recherche, normalisation, timeout 4 s, cache 1 h, jamais d'exception) |
| `BaseBillet/views.py` | 3 `@action` : `check-instance`, `search-tierslieux`, `use-tierslieux` + pré-remplissage carte |
| `…/wizard/_form_lieu.html` | conteneurs HTMX + câblage email + JS débounce conditionnel |
| `…/wizard/_form_carte.html` | géocodage de l'adresse complète pré-remplie |
| `…/wizard/_instance_trouvee.html`, `_tierslieux_resultats.html` | partials |

Spec complète : `TECH_DOC/SESSIONS/EVENT_WIZARD/CHANTIER-04-integration-tiers-lieux.md`.

## Tests à réaliser

### Pré-requis
- Tenant avec `module_agenda_participatif=True` + `proposition_anonyme_autorisee=True`
  (lespass est déjà configuré).
- Naviguer en **anonyme** (déconnecté) sur `https://lespass.tibillet.localhost/event/wizard/place/`.

### Test 1 — Détection d'instance (nominal)
1. Saisir l'email d'un compte qui administre une instance (ex : un admin de tenant).
2. Quitter le champ (blur).
3. **Attendu** : encart vert « Vous gérez déjà « … » sur TiBillet » + bouton vers son wizard
   + conseil fédération (et tag si le tenant courant a des `tags_federation`). Le reste du
   formulaire reste utilisable (non-bloquant).

### Test 2 — Email sans instance
1. Saisir un email quelconque sans instance.
2. **Attendu** : aucun encart (conteneur vide).

### Test 3 — Recherche nationale Tiers-Lieux
1. Dans « Utiliser une adresse existante », taper un nom de lieu **absent** des adresses
   locales (ex : « raffinerie »).
2. **Attendu** : « Aucune adresse ne correspond » (filtre local) puis, après ~600 ms,
   encart « Donnée trouvée dans le recensement national Tiers-Lieux » avec la/les fiche(s).
3. Cliquer « Utiliser ce lieu ».
4. **Attendu** : étape carte, marqueur positionné, champs rue/CP/ville/pays pré-remplis par
   géocodage. Vérifier/ajuster puis valider → étape évènements.

### Test 4 — Aucun lieu trouvé
1. Taper un terme sans correspondance locale ni nationale (ex : « zzzzz »).
2. **Attendu** : « Aucun lieu trouvé dans le recensement national. Utilisez Créer un nouveau lieu. »

### Test 5 — API indisponible (robustesse)
1. (Simulation) couper l'accès réseau sortant du conteneur, ou attendre un timeout.
2. **Attendu** : le wizard continue normalement, encart Tiers-Lieux vide, pas d'erreur 500.

## Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tiers_lieux.py -q
```
11 tests : service (succès/timeout/erreur→[]/cache/normalisation) + endpoints
(check-instance avec/sans instance, search-tierslieux court/valide).

## Sécurité à valider avec le mainteneur
- `check-instance` expose si un email administre une instance (énumération email→instance).
  Accepté pour le MVP. Ajouter un rate-limit par IP si besoin.

## Compatibilité
- Aucune migration. Le filtre local JS existant est conservé (instantané) ; la recherche
  nationale ne part qu'en repli. Si l'API externe est down, dégradation gracieuse.
- i18n : lancer `makemessages` + `compilemessages` (textes source FR).
