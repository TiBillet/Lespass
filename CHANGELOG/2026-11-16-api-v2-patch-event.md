# API v2 : modifier un évènement (PATCH) / API v2: partially update an event (PATCH)

**Date :** 2026-11-16
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Nouvelle route `PATCH /api/v2/events/{uuid ou slug}/` (`EventViewSet.partial_update`, `EventPatchSerializer`). Seuls les champs envoyés changent : nom, dates, jauge, descriptions, publication (`eventStatus`), fédération (`audience`), tags (`keywords`, remplace la liste), `offers`, catégorie (`additionalType`), ressource bloquée (`blockedResource`, `null` la libère), message de confirmation, options, images `img` / `sticker_img` en multipart.
- Les règles de la création s'appliquent aux valeurs finales (base + PATCH) : fin après le début, date de fin obligatoire si une ressource est bloquée, couple nom + date libre.
- En multipart, `audience` et `offers` sont refusés par une 400 (DRF les reçoit vides) au lieu d'être pris pour des valeurs vides : nouveau champ `ObjetImbriqueAbsentEnMultipart`.
- Création (`POST /api/v2/events/`) : la description longue est nettoyée par `clean_html`, comme dans l'admin (XSS). Un doublon nom + date renvoie une 400 sur `name` au lieu d'une 500.
- `blockedResource` est maintenant renvoyé dans `additionalProperty` quand l'évènement bloque une ressource (il était en écriture seule).
- `GET /api/v2/postal-addresses/` (et `location.address` d'un event) donne `identifier`, l'id attendu par `link-address`.
- OpenAPI (route `patchEvent`, schéma `EventPatch`, `PostalAddress.identifier`), `api_v2/GUIDELINES.md` et le skill `tibillet-api` mis à jour.

/ New `PATCH /api/v2/events/{uuid or slug}/`: only sent fields change, creation rules apply to the final values. POST now sanitizes the long description and returns 400 on a duplicate name + start date. `blockedResource` is returned when set. Postal addresses expose their `identifier`.

**Pourquoi / Why :** sans PATCH, corriger un évènement par l'API obligeait à le supprimer et le recréer (URL changée, réservations perdues). Besoin concret : corriger les ateliers de La Filature créés par l'API.
/ Without PATCH, fixing an event meant deleting and recreating it.

**i18n :** 9 nouvelles chaînes en français dans `api_v2/serializers.py` (messages d'erreur du PATCH et du POST) : workflow de traduction à lancer.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/serializers.py` | `EventPatchSerializer`, `ObjetImbriqueAbsentEnMultipart`, helpers `_trouver_la_ressource_a_bloquer`, `_valider_les_bornes_des_offres`, `_le_nom_et_la_date_sont_deja_pris` ; POST : `validate_description` + contrôle du doublon dans `create()` ; `blockedResource` en lecture ; `identifier` des adresses |
| `api_v2/views.py` | `EventViewSet.partial_update` |
| `api_v2/openapi-schema.yaml` | route `patch` des events, schéma `EventPatch`, `PostalAddress.identifier`, description de `blockedResource` |
| `api_v2/GUIDELINES.md` | section PATCH, `blockedResource`, nettoyage, doublon, identifiant d'adresse |
| `TECH_DOC/SKILLS/tibillet-api/SKILL.md`, `references/recettes.md` | recette PATCH, multipart + ressource bloquée |
| `tests/pytest/test_api_v2_event_patch.py` | 24 tests (nouveau) |
| `tests/pytest/test_api_v2_event_ressource_bloquee.py` | la réponse contient maintenant `blockedResource` |

---

## Comment tester (a la main) / Manual test

Préparer une clé avec le droit « Events » :
`python TECH_DOC/SKILLS/tibillet-api/scripts/creer_cle_api.py --tenant lespass --perms event`
puis `K="Api-Key <clé>"` et `H=lespass.tibillet.localhost`.

### Test 1 — modifier la description et rendre l'évènement non fédérable
1. `curl -sk "https://$H/api/v2/events/" -H "Authorization: $K"` : noter un `identifier`.
2. `curl -sk -X PATCH "https://$H/api/v2/events/<uuid>/" -H "Authorization: $K" -H "Content-Type: application/json" -d '{"description":"<p>Nouveau</p><script>x</script>","audience":{"audienceType":"private"}}'`
3. Attendu : 200, `description` sans `<script>`, `audience.audienceType` = `private`. Le nom et les dates n'ont pas changé.

### Test 2 — bloquer puis libérer une ressource
1. PATCH `{"additionalProperty":[{"name":"blockedResource","value":<id de /booking/<id>/resource/>}]}` sur un évènement qui a une date de fin.
2. Attendu : `additionalProperty` contient `blockedResource`. Sur `/booking/<id>/resource/`, le créneau de l'évènement est « complet ».
3. PATCH `{"additionalProperty":[{"name":"blockedResource","value":null}]}` : le créneau redevient libre.

### Test 3 — refus
- `{"endDate": "<avant le début>"}` → 400 sur `endDate`.
- `{"endDate": null}` sur un évènement qui bloque une ressource → 400 sur `endDate`.
- `{"name": "<nom d'un autre évènement à la même heure>"}` → 400 sur `name`.
- multipart `-F audience.audienceType=private` → 400 sur `audience`.
- `{"additionalType": "Inconnu"}` → 400 ; `{"additionalProperty":[{"name":"x","value":1}]}` → 400.

### Test 4 — image en multipart
`curl -sk -X PATCH "https://$H/api/v2/events/<uuid>/" -H "Authorization: $K" -F img=@photo.jpg` → 200, `image[0]` pointe vers la nouvelle image.

### Test 5 — création
- POST deux fois le même `name` + `startDate` → la deuxième fois, 400 sur `name` (plus de 500).
- `GET /api/v2/postal-addresses/` → chaque adresse a un `identifier` numérique.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_api_v2_event_patch.py"` (24 tests).
- Pas de test E2E : aucun rendu côté navigateur n'a changé.
