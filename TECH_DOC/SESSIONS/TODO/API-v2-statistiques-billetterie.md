# API v2 : publier les chiffres de la billetterie

**Statut :** idée cadrée le 2026-11-01, spec à écrire. Rien n'est codé.

## Le besoin
Le mainteneur veut retrouver dans la V2 les données de `GET /api/gauge/` (V1), et toutes
les infos utiles : billets valides, non valides, jauge maximale de l'événement, billets
scannés, etc. Le tout par l'API des événements et/ou celle du scan.

**But :** alimenter des bases de données et des tableurs de type Grist, notamment pour
les comptables.

**Contrainte :** vocabulaire schema.org, API sémantique et RESTful. Pas de format à plat
sous prétexte que la cible est un tableur.

## Ce qui existe
- **V1 :** `/api/gauge/` renvoie `gauge_max` (lu sur `Configuration.jauge_max`, pas sur
  l'événement), `all_tickets` et `scanned_tickets`, pour la journée en cours.
- **V2, `GET /api/v2/events/` :** publie `maximumAttendeeCapacity`, mais aucun compteur
  de billets. Seuls les événements publiés sortent. Les passés publiés y figurent, mais
  on ne peut pas limiter la liste à une période (`only_futur`, `next_days`, `filter`).
- **V2, `GET /api/v2/reservations/?event=<uuid>` :** liste les inscrits, sans le statut
  de scan. `reservedTicket` compte tous les billets, sans filtre de statut.
- **Routes `/scan/*` (`BaseBillet/views_scan.py`) :** JSON hors schema.org, clé
  scanner `HasScanApi`. Elles restent telles quelles.
- **Droit `ticket` :** présent sur `ExternalApiKey`, sans route V2. Pas de migration.

## Piste retenue pour la spec
**Modèle à suivre :** `GET /api/v2/products/?accounting=true`. Un mode explicite ajoute
des champs dans `additionalProperty`, sans nouvelle route. La réponse par défaut ne
change pas.

```
GET /api/v2/events/?statistics=true&dateFrom=2026-10-01&dateTo=2026-10-31
```

- **Accès :** droits `event` et `ticket`, sinon 403. La seconde vérification suit le
  modèle de `CleAvecLeDroitDesVentes`, posée après `SemanticApiKeyPermission`.
- **Clé seule, sans compte admin :** décision A2 de la spec 06-A, un logiciel tourne la
  nuit sans humain.
- **Pas de champs selon la clé :** une route donne le même format à tout le monde. Une
  clé `event` peut servir à un agenda partenaire et ne doit pas recevoir ces compteurs.
- **Racine de l'`Event` :** `remainingAttendeeCapacity` (terme schema.org), à côté de
  `maximumAttendeeCapacity`.
- **`additionalProperty` :** un `PropertyValue` par compteur, en camelCase anglais comme
  les ajouts comptables. Noms à figer dans la spec.

| Compteur | Statuts `Ticket` |
|---|---|
| billets valides | `NOT_SCANNED` (K) + `SCANNED` (S) |
| billets scannés | `SCANNED` (S) |
| billets non scannés | `NOT_SCANNED` (K) |
| billets annulés | `CANCELED` (R) |
| paiements en cours | `CREATED` (C) + `NOT_ACTIV` (N), bornés comme `Event.under_purchase()` |

## Questions ouvertes
1. **Grain :** les compteurs par événement suffisent-ils, ou faut-il aussi une ligne par
   billet avec nom et e-mail ? Dans ce cas : ressource `schema.org/Ticket` sur
   `GET /api/v2/tickets/?event=<uuid>`, avec des données personnelles à exposer.
2. **Festivals :** cumuler les sous-événements dans le parent, ou compter chaque
   événement seul ?
3. **Événements non publiés :** à inclure dans le mode statistiques ?
4. **Fin de vie de `/api/gauge/` :** la route lit la jauge du lieu et la journée en
   cours, la V2 lirait celle de l'événement. À décider une fois la V2 livrée.

## Points de vigilance
- **Heure de scan :** `Ticket` garde le statut et l'appareil (`scanned_by`), pas l'heure.
  Une courbe des entrées demande une migration. Hors périmètre sauf décision contraire.
- **QR code :** ne jamais le publier ici. `Ticket.qrcode()` produit le billet signé.
- **`identifier` :** dans `reservedTicket`, c'est l'uuid du **tarif**. Dans une ressource
  `Ticket`, ce serait l'uuid du **billet**. À documenter.
- **`ticketQuantity` :** déjà utilisé par la V2, mais ce n'est pas un terme schema.org.
- **schema.org :** `interactionStatistic` n'existe pas sur `Event`. `additionalProperty`
  n'y est pas prévu non plus, mais la V2 s'en sert déjà sur `Event` : on garde cette
  convention, écrite dans `api_v2/GUIDELINES.md`.
- **Performance :** une seule requête d'agrégation pour toute la liste.
  `tests/pytest/test_api_v2_liste_des_evenements.py` vérifie que le coût ne dépend pas du
  nombre d'événements. Rejeter `dateFrom` / `dateTo` mal formés en 400.

## Fichiers à mettre à jour dans le même commit
- `api_v2/views.py`, `api_v2/serializers.py`, `api_v2/permissions.py`
- `api_v2/openapi-schema.yaml` (à la main, vérifié avec `yamllint`), `api_v2/GUIDELINES.md`
- `TECH_DOC/SKILLS/tibillet-api/SKILL.md` et `references/recettes.md`
- `Administration/management/commands/test_api_key.py` et `scripts/creer_cle_api.py` si
  les droits des clés de test changent
- Tests dans `tests/pytest/`, vérifiés par mutation, et une entrée dans `CHANGELOG/`

## À lire avant de reprendre
- `api_v2/GUIDELINES.md`, `api_v2/openapi-schema.yaml`
- `api_v2/serializers_benevolat.py` et `api_v2/views_benevolat.py` : le modèle le plus
  récent (compteurs en `additionalProperty`, `remainingAttendeeCapacity`)
- `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-comptables/CHANTIER-06-A-api-comptable.md`
- Chantier voisin : [`API-v2-ventes-reglements.md`](API-v2-ventes-reglements.md)
