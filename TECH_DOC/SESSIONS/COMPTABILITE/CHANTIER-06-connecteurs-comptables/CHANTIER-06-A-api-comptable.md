# Chantier 06-A — L'API comptable de TiBillet (la pièce commune à tous les connecteurs)

> **Statut** : ✅ **CODÉE le 2026-10-13, non commitée** (15 tests, 12 mutations tuées ; CHANGELOG
> `CHANGELOG/2026-10-13-api-comptable.md`). Spec relue par Fable le 2026-10-13 et corrigée
> (1 bloquant, 3 importants, 9 mineurs : §12). Décisions du mainteneur du même jour :
> curseur par numéro sans pagination, noms du FEC dans le JSON.
> Contexte : [`README.md`](README.md) du chantier 06, décisions du mainteneur au §7.
> Code lu le 2026-10-13 (branche `erp-dolibarr`, chantier 05 **en production** depuis le
> 2026-10-12). **Revérifier les numéros de ligne avant de coder.**
> Effort estimé : 1,5 j (une session API + une session tests et doc).
> Migration : **oui** (un booléen sur `ExternalApiKey`).

---

## 1. Le but, en une phrase

Donner à un logiciel comptable (Dolibarr d'abord, puis Dokos, Paheko, Pennylane) ce qu'il
lui faut pour ranger chaque nuit les clôtures du lieu dans sa comptabilité :

1. la **liste des clôtures** prêtes à importer ;
2. les **écritures** de chaque clôture, en **JSON** (montants en centimes) ;
3. les mêmes écritures en **fichier FEC** (le fichier légal, identique au bouton de l'admin) ;
4. la **liste des comptes** du lieu (numéro + libellé), pour que le connecteur crée ceux
   qui lui manquent.

**L'API ne calcule rien de nouveau.** Elle rend ce que le chantier 05 calcule déjà
(`ecritures_de_l_export`, `generer_fec_cloture`). Les règles comptables restent à un seul
endroit.

## 2. Expliqué simplement (FALC)

- Chaque nuit, le logiciel comptable du lieu appelle TiBillet avec **sa clé d'API**.
- Il demande : « quelles clôtures as-tu **après la n° 12** ? » (12 = le numéro de la
  dernière clôture qu'il a importée). TiBillet donne la liste.
- Pour chaque clôture de la liste, il demande ses **écritures**.
- Il les écrit dans son grand livre, **sans les verrouiller**. Le comptable valide ensuite.
- Il **retient** le numéro de la dernière clôture importée, et l'identifiant (`uuid`) de
  chaque clôture importée. Il n'importe jamais deux fois la même.
- Si TiBillet refuse une clôture (un compte manque dans le plan du lieu), le logiciel
  **s'arrête là** et réessaie la nuit suivante, à partir de la même clôture. Rien n'est
  perdu : il ne retient un numéro qu'une fois sa clôture importée.

**Pourquoi un numéro et pas une date ?** La clôture automatique de la nuit peut être
créée **après** le passage du logiciel tout en étant **datée d'avant** (elle finit à
l'heure de fermeture + 2 h). Avec une date, elle serait ratée pour toujours. Les numéros,
eux, ne font que monter, dans l'ordre de création des clôtures.

## 3. Ce qui existe déjà (vérifié le 2026-10-13, relu par Fable)

| Quoi | Où |
|---|---|
| Écritures d'une clôture, prêtes à écrire | `comptabilite/ventilation.py` `ecritures_de_l_export(cloture)` (l.604) → `{"ecritures": [...], "date_du_nom_du_fichier": date}`. Une écriture = `{"journal", "libelle_du_journal", "numero_d_ecriture", "date", "piece", "libelle", "lignes": [{"compte", "libelle", "debit", "credit"}]}`, montants en **centimes entiers**, un compte = une ligne (solde net, jamais négatif) |
| Fichier FEC | `comptabilite/fec.py` `generer_fec_cloture(cloture)` (l.100) → `(octets, nom, type)` ; il ne fait que mettre en forme `ecritures_de_l_export` |
| Refus du FEC avant la mise en service (Q-R3) | **dans la vue admin** `comptabilite/admin.py` `ClotureCaisseAdmin.exporter_fec` (l.234, refus l.269-275) : la J « reprise », et toute H / M / A dont `datetime_debut < mise en service`. **Aucune J ordinaire n'est refusée** : en production, la J reprise est la première J de chaque lieu (`creer_la_cloture_de_reprise` refuse s'il existe déjà une J) |
| Mise en service du lieu | `comptabilite/tasks.py` `mise_en_service_du_lieu()` (l.670 ; sa docstring liste ses appelants), `est_la_j_de_reprise(cloture)` (l.640) |
| Date des écritures d'une J | `comptabilite/ventilation.py` `date_de_debut_de_service(cloture)` : date locale de sa première vente, dans le fuseau **figé dans le rapport** de la J (une requête par J) |
| Ordre des J | chaque J commence à la fin de la précédente (`comptabilite/tasks.py` l.483-489) ; `numero_sequentiel` est posé à la création, croissant (l.355-361) : **pas de trou, pas de retour en arrière** |
| Refus de calcul | `CompteComptableManquant` (`laboutik/plan_comptable.py` l.82), `EcritureDesequilibree` (`comptabilite/ventilation.py` l.100) |
| Filet « plan absent » | `laboutik/plan_comptable.py` `s_assurer_que_le_plan_existe()` (l.264) : charge le plan par défaut si le lieu n'a aucun compte (idempotent) ; déjà appelé par `generer_fec_cloture` |
| Comptes du lieu | `laboutik.CompteComptable` (`laboutik/models.py` l.2080) : `numero_de_compte` (unique), `libelle_du_compte`, `est_actif`, … |
| Clés d'API | `BaseBillet.ExternalApiKey` (`BaseBillet/models.py` l.5275) : un booléen par droit, lu par `api_permissions()` selon le `basename` de la route (vaut aussi pour les `@action`, ex. `MembershipViewSet.by_wallet`). `rest_framework_api_key` et `BaseBillet` sont en `TENANT_APPS` : **une clé vit dans le schéma de son lieu** ; la clé d'un autre lieu n'est pas trouvée → 403 |
| Permission par clé seule | `api_v2/permissions.py` `SemanticApiKeyPermission` |
| Restriction d'IP | `ExternalApiKey.ip`, comparée à `get_client_ip` (`AuthBillet/utils.py`, en-tête `X-Real-IP` posé par nginx) |
| Pagination | **aucune liste d'`api_v2` n'est paginée** (`viewsets.ViewSet` ne pagine pas tout seul ; `EventViewSet.list` rend `{"results": [...]}`) |

## 4. Décisions de conception

| # | Sujet | Décision | Pourquoi |
|---|---|---|---|
| A1 | Le droit | Un nouveau booléen **`comptabilite`** sur `ExternalApiKey` (« Comptabilité (lecture) »), mappé sur les deux `basename` des routes (§5) | Une clé de connecteur ne doit lire **que** la comptabilité, pas les ventes ni les adhérents |
| A2 | Qui peut appeler | **La clé seule** (`SemanticApiKeyPermission`), pas « clé + admin du lieu » | Le connecteur tourne la nuit, sans humain. `TenantAdminApiPermission` (utilisée par `/sales/`) exige que le **créateur** de la clé soit encore admin : la clé tomberait en panne à son départ. Le droit est porté par la clé (et sa restriction d'IP). Relu par Fable : sain |
| A3 | Lecture seule | Seulement des `GET`. Seule écriture : le filet `s_assurer_que_le_plan_existe()`, idempotent, déjà déclenché par le FEC de l'admin | Le connecteur ne modifie jamais TiBillet |
| A4 | Quelles clôtures | **Seulement les J** qui ont des ventes (plage remplie), **pas** la J « reprise » | Le FEC fait foi par J (fiche 05-F §4). Une H / M / A n'est que la suite de ses J : l'importer en plus compterait tout deux fois. La J reprise (des années en une J) n'a pas de FEC (Q-R3) |
| A5 | Vocabulaire du JSON | **Les noms des colonnes du FEC** (`JournalCode`, `EcritureNum`, `CompteNum`, `Debit`…) pour les écritures ; des noms anglais simples pour l'enveloppe (mainteneur, 2026-10-13) | schema.org n'a aucun type pour une écriture comptable. Les noms du FEC sont **la norme française** que tous les logiciels comptables connaissent. Exception écrite dans `api_v2/GUIDELINES.md` |
| A6 | Montants | **Centimes entiers** dans le JSON | Pas de virgule à interpréter (piège `price2num()` de Dolibarr, README §8) ; c'est déjà la forme interne |
| A7 | Date de validation | **Absente du JSON** (pas de `ValidDate`) ; le fichier FEC, lui, reste **inchangé** (`ValidDate` rempli) | Décision R3 : non verrouillé. Dans Dolibarr, une `ValidDate` remplie verrouille l'écriture dès l'import (README §4). Le fichier FEC reste le fichier légal du bouton de l'admin |
| A8 | Rien de figé | Les écritures sont **recalculées à chaque appel** (Q-F2) ; aucun cache | Si le lieu corrige son plan après un refus, l'appel suivant doit voir la correction |
| A9 | Refus | `404` = cette clôture n'est pas à importer (jamais) ; `409` = pas maintenant (réessayer plus tard) ; corps `{"detail": phrase, "code": code}` | Le connecteur sait s'il doit **oublier** ou **réessayer** sans lire la phrase |
| A10 | Une seule règle de mise en service | Sortir **telle quelle** la règle de refus de la vue admin (J reprise, ou H / M / A commencée avant la mise en service) dans **une fonction** de `comptabilite/tasks.py`, à côté de `mise_en_service_du_lieu`, appelée par l'admin **et** par l'API | Même règle, un seul endroit (fiche R §11.4). Comportement de l'admin inchangé |
| A11 | Curseur et pagination | Paramètre **`after_number`** (entier) ; **pas de pagination** : la liste est rendue d'un coup, dans `{"results": [...]}`, comme les autres listes d'`api_v2` (mainteneur, 2026-10-13) | Les numéros ne font que monter (§3) : rien n'est raté, pas de fuseau à lire. Chaque nuit, la liste ne contient que quelques J |

## 5. Les routes

Toutes sous `/api/v2/`, en-tête `Authorization: Api-Key <clé>`. Deux `ViewSet`
(`viewsets.ViewSet`, pas de `ModelViewSet`), dans `api_v2/views.py`, déclarées dans
`api_v2/urls.py`.

| Route | `basename` | Droit |
|---|---|---|
| `GET /api/v2/closures/` | `closure` | `comptabilite` |
| `GET /api/v2/closures/{uuid}/entries/` | `closure` | `comptabilite` |
| `GET /api/v2/closures/{uuid}/fec/` | `closure` | `comptabilite` |
| `GET /api/v2/accounts/` | `account` | `comptabilite` |

Dans `ExternalApiKey.api_permissions()` : `"closure": self.comptabilite` et
`"account": self.comptabilite` (même mécanisme que `postaladdress` → `event`).

Pas de route `GET /closures/{uuid}/` : le connecteur n'en a pas besoin (la liste donne
tout, `entries` et `fec` cherchent déjà la clôture par son uuid).

### 5.1 `GET /api/v2/closures/` — la liste des clôtures à importer

Paramètre facultatif : `after_number` = entier ≥ 0. Garde les J dont
`numero_sequentiel > after_number`. Absent : toutes les J. Pas un entier, ou négatif :
`400`, avec un exemple (`?after_number=12`). Messages en `_()`, en français.

**Les J listées** (A4), dans l'ordre de `numero_sequentiel` croissant :

- `niveau = J` ;
- `numero_premiere_vente` et `numero_derniere_vente` remplis ;
- pas la J « reprise » (`est_la_j_de_reprise`).

La liste de J vient d'**une fonction** de `comptabilite/` (par ex.
`journees_a_importer(apres_le_numero=None)` dans `comptabilite/tasks.py`, à côté de
`est_la_j_de_reprise`), pas d'un filtre écrit dans la vue.

Réponse : `{"results": [ … ]}`. Un élément :

```json
{
  "uuid": "3f2a9c1e-…",
  "number": 12,
  "startDate": "2026-10-12T17:02:11+02:00",
  "endDate": "2026-10-13T04:00:00+02:00",
  "accountingDate": "2026-10-12",
  "entries": "https://<lieu>/api/v2/closures/3f2a9c1e-…/entries/",
  "fec": "https://<lieu>/api/v2/closures/3f2a9c1e-…/fec/"
}
```

- `number` = `numero_sequentiel` ; c'est aussi `PieceRef` des écritures, et la valeur à
  repasser dans `after_number`.
- `startDate` / `endDate` : `datetime_debut` / `datetime_fin`, en ISO avec décalage, dans
  le fuseau **figé dans le rapport de la J** (le même que `accountingDate`).
- `accountingDate` = la date des écritures (`date_de_debut_de_service`, fiche 05-F §4 : une
  soirée du 12 à 22 h au 13 à 2 h est datée du 12). Coût : une requête par J ; accepté
  (quelques J par nuit ; au premier import, les J depuis la mise en service du 2026-10-12).

### 5.2 `GET /api/v2/closures/{uuid}/entries/` — les écritures en JSON

Appelle `ecritures_de_l_export(cloture)` (après le filet `s_assurer_que_le_plan_existe()`,
comme le FEC) et réécrit chaque écriture avec les noms du FEC :

```json
{
  "closure": "3f2a9c1e-…",
  "number": 12,
  "accountingDate": "2026-10-12",
  "currency": "EUR",
  "amountUnit": "cent",
  "entries": [
    {
      "JournalCode": "BAR",
      "JournalLib": "Bar",
      "EcritureNum": "12-BAR",
      "EcritureDate": "2026-10-12",
      "PieceRef": "12",
      "PieceDate": "2026-10-12",
      "EcritureLib": "Clôture J n° 12 — Bar",
      "lines": [
        {"CompteNum": "512100", "CompteLib": "Carte bancaire (TPE)", "Debit": 30000, "Credit": 0},
        {"CompteNum": "530000", "CompteLib": "Caisse espèces", "Debit": 20000, "Credit": 0},
        {"CompteNum": "707000", "CompteLib": "Ventes de marchandises", "Debit": 0, "Credit": 41667},
        {"CompteNum": "445711", "CompteLib": "TVA collectée 20 %", "Debit": 0, "Credit": 8333}
      ]
    }
  ]
}
```

- `currency` et `amountUnit` sont des constantes (seules les ventes en euros ont une
  écriture) : elles rendent le JSON lisible sans la doc.
- Dates au format ISO `AAAA-MM-JJ` (pas `AAAAMMJJ` comme le fichier).
- **Pas** de `ValidDate` (A7). Pas de colonnes vides du FEC (`CompAuxNum`, `EcritureLet`…).
- Chaque écriture est équilibrée (Σ `Debit` = Σ `Credit`) : c'est garanti par
  `ventiler_cloture`, qui refuse sinon.
- Les libellés de compte sont ceux du plan **du moment** (A8).
- Le total des écritures **n'est pas** le chiffre d'affaires du Z : les débits comptent
  aussi les recharges de cartes, les vidages, les écarts (hors chiffre d'affaires). C'est
  pourquoi la liste ne donne pas de total.

### 5.3 `GET /api/v2/closures/{uuid}/fec/` — le fichier FEC

Rend **exactement** ce que rend le bouton de l'admin : `generer_fec_cloture(cloture)`,
dans un **`HttpResponse`** Django (pas un `Response` DRF, qui le rendrait en JSON), comme
`_telecharger` de `comptabilite/admin.py` (l.70) : `text/plain; charset=utf-8`,
`Content-Disposition: attachment; filename="FEC-AAAAMMJJ-<n°>.txt"`. Mêmes refus que §5.2.

Sert aux logiciels qui importent un FEC tout seuls, et au contrôle humain.

### 5.4 `GET /api/v2/accounts/` — le plan comptable du lieu

Appelle d'abord `s_assurer_que_le_plan_existe()`. Rend **tous** les comptes du lieu, actifs
ou non (un compte inactif est seulement caché des menus ; il sert encore aux exports,
règle du mainteneur, fiche F-3d), triés par numéro, dans `{"results": [ … ]}`.

```json
{"accountNumber": "707900", "name": "Ventes réglées en jetons offerts", "active": true}
```

Le connecteur crée dans son logiciel les numéros qui lui manquent, avec ce libellé. Il ne
modifie jamais un compte qui existe déjà chez lui (décision du README §7).

## 6. Les refus

| Cas | Code HTTP | `code` | Le connecteur… |
|---|---|---|---|
| Pas d'en-tête `Authorization` | `403` | — | message actuel de `get_apikey_valid` |
| Clé inconnue, clé d'un autre lieu, mauvaise IP, droit `comptabilite` faux | `403` | — | s'arrête, prévient l'admin du logiciel |
| `after_number` pas un entier ≥ 0 | `400` | — | corrige l'appel |
| uuid inconnu, H / M / A, J sans vente, J « reprise » | `404` | `not_exportable` | oublie cette clôture |
| Un compte ou un journal manque (`CompteComptableManquant`) | `409` | `missing_account` | s'arrête, réessaie la nuit suivante ; montre la phrase à l'admin |
| Écriture déséquilibrée (`EcritureDesequilibree`) | `409` | `unbalanced_entry` | s'arrête, réessaie ; **côté TiBillet, `logger.exception`** (remonte à Sentry si son intégration logging est active : à vérifier au brief), car c'est une donnée altérée après l'encaissement |

- La phrase de `missing_account` est celle de l'exception (elle nomme la J et le compte) ;
  elle renvoie au bouton « Vérifier le plan » de l'admin du lieu.
- La phrase de `not_exportable` pour la J reprise reprend celle de l'admin : « Le FEC
  commence à la date de mise en service de la comptabilité (jj/mm/aaaa). »
- Toutes les phrases en `_()`, en français.

## 7. Ce qui change dans le code

| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | `ExternalApiKey.comptabilite` (`BooleanField(default=False)`, libellé « Comptabilité (lecture) ») ; `api_permissions()` : `"closure"` et `"account"` |
| `BaseBillet/migrations/` | `AddField` (app tenant ; prod : 518 lieux, **un lieu après l'autre**, pas `--executor=multiprocessing`) |
| `Administration/admin_tenant.py` | `ExternalApiKeyAdmin` : le booléen dans `fields` et `list_display` |
| `comptabilite/tasks.py` | nouvelle fonction (A10), par ex. `refus_du_fec_avant_la_mise_en_service(cloture)` → phrase ou `None` ; docstring de `mise_en_service_du_lieu` mise à jour (appelants) |
| `comptabilite/admin.py` | `exporter_fec` appelle cette fonction (comportement inchangé) |
| `comptabilite/tasks.py` | `journees_a_importer(apres_le_numero=None)` (§5.1), à côté de la règle de la J reprise (écart à la spec : prévue dans `ventilation.py`) |
| `api_v2/views.py` | `ClosureViewSet` (`list`, actions `entries` et `fec`) et `AccountViewSet` (`list`) |
| `api_v2/serializers.py` | sérialisation de la clôture et du compte (`serializers.Serializer`, pas de `ModelSerializer`) |
| `api_v2/urls.py` | les deux routes, `basename` `closure` et `account` |
| `api_v2/openapi-schema.yaml` | les quatre routes, les schémas, les refus |
| `api_v2/GUIDELINES.md` | une section « Comptabilité » : routes, curseur `after_number`, exception des noms du FEC (A5), centimes |
| `Administration/management/commands/test_api_key.py` | `comptabilite=True` sur la clé de test |
| `TECH_DOC/comptabilite.md` | doc utilisateur : créer une clé **dédiée** au logiciel comptable, avec **seulement** le droit « Comptabilité », l'**IP** remplie si le logiciel a une IP fixe ; supprimer la clé si on change de logiciel |

## 8. Tests

Fichier : `tests/pytest/test_api_v2_comptabilite.py`, **schéma dédié**
(`FastTenantTestCase` : il lit des clôtures et la chaîne, tronc 05 §8 ; créer le
singleton `LaboutikConfiguration`, PIEGES 9.86). Client : le motif existant
`APIClient()` + `client.defaults["HTTP_HOST"] = <domaine du test>`
(`tests/pytest/test_inventaire.py` l.529-531), avec l'en-tête `HTTP_AUTHORIZATION`. Le
bouton de l'admin se teste par `RequestFactory` + méthode de l'admin, comme
`test_comptabilite_exports.py` (l.559-585) et `test_reprise_clotures.py` (l.692-790).

| # | Test |
|---|---|
| 1 | `test_sans_cle_ou_sans_droit_comptabilite_refuse` (pas d'en-tête, clé sans le droit → 403 ; avec le droit → 200) |
| 2 | `test_cle_d_un_autre_lieu_refusee` |
| 3 | `test_liste_ne_donne_que_les_j_avec_ventes_dans_l_ordre` (une H, une M, une J sans vente et la J reprise existent : absentes de la liste, et `404 not_exportable` sur `entries` et `fec`) |
| 4 | `test_after_number_ne_rend_que_les_suivantes_et_refuse_un_texte` |
| 5 | `test_j_creee_en_retard_est_vue_avec_after_number` (une J dont la fin est antérieure au passage précédent, mais créée après : elle est dans la liste) |
| 6 | `test_entries_egales_a_ecritures_de_l_export` (mêmes comptes, mêmes centimes, mêmes numéros, dates ISO) |
| 7 | `test_entries_sans_valid_date_et_equilibrees` |
| 8 | `test_fec_identique_au_bouton_de_l_admin` (octet pour octet, même nom de fichier) |
| 9 | `test_compte_manquant_409_missing_account` |
| 10 | `test_ecriture_desequilibree_409_unbalanced_entry` (donnée altérée en base) |
| 11 | `test_refus_de_la_j_reprise_meme_regle_pour_admin_et_api` (A10) |
| 12 | `test_accounts_tous_les_comptes_y_compris_inactifs` |
| 13 | `test_accounts_charge_le_plan_si_le_lieu_n_en_a_aucun` |
| 14 | `test_entries_suivent_le_plan_du_moment` (changer le compte d'une catégorie → l'appel suivant le montre) |

Vus rouges : tous. Tests existants qui doivent rester verts sans changement :
`test_fec_equilibre.py`, `test_comptabilite_exports.py` (bouton FEC), `test_reprise_clotures.py`
(refus avant la mise en service).

Mutations (à la main, sha256 avant / après) : droit `closure` mappé sur `sale` ; H / M / A
gardées dans la liste ; J reprise gardée ; `>` remplacé par `>=` dans `after_number` ;
filtre par `datetime_fin` au lieu du numéro (test 5) ; `ValidDate` ajoutée au JSON ;
montants en euros (`/100`) ; `409` remplacé par `500` ; filet du plan retiré de
`/accounts/` ; comptes inactifs filtrés ; refus de la J reprise gardé dans l'admin seulement.

## 9. Hors de cette fiche

- **Le module Dolibarr** (fiche 06-B, à écrire) : configuration (URL du lieu, clé), tâche
  quotidienne, curseur `after_number` gardé en base, création des comptes manquants,
  import non validé avec `ref` = `EcritureNum`, table des clôtures importées (par `uuid`),
  arrêt au premier `409`, pièges du README §8.
- **Le PDF de la clôture** dans l'API (décision : pas pour l'instant).
- **Les ventes détaillées, adhérents, factures** (étape 2) : après la revue du contrat
  de `/sales/` (Q-H8).
- **Dokos, Paheko, Pennylane** : étude de leur import (README §6.7).
- **Limitation de débit** de l'API v2 : aucune aujourd'hui (`TiBillet/settings.py`,
  throttles commentés) ; sujet de toute l'API, pas de cette fiche.

## 10. Vérifications

```bash
docker exec lespass_django pgrep -af pytest          # rien ne doit tourner
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
make test ARGS="tests/pytest/test_api_v2_comptabilite.py"
make test                                             # suite complète en fin de fiche
```

Essai à la main : créer une clé « Comptabilité » dans l'admin du lieu de dev, puis
`curl -H "Authorization: Api-Key <clé>" https://lespass.tibillet.localhost/api/v2/closures/`.

## 11. Guidelines alignées (2026-10-13)

`api_v2/GUIDELINES.md` disait « Prefer ModelViewSet or ReadOnlyModelViewSet », contre
`GUIDELINES.md` à la racine. Corrigé par le mainteneur le 2026-10-13 : `viewsets.ViewSet`
partout, comme le code réel d'`api_v2` et cette fiche.

## 12. Relecture Fable (2026-10-13) — ce qui a été appliqué

| Constat | Correction |
|---|---|
| **B-1** règle « J finie avant la mise en service » inventée, vide en prod, contraire à A10 | Retirée. La liste exclut la J reprise ; A10 reprend **telle quelle** la règle de l'admin ; tests fusionnés (n° 3, 11) |
| **I-1** pagination affirmée, faite nulle part dans `api_v2` | Pas de pagination (A11, mainteneur) |
| **I-2** `since` : une J du filet créée après le passage pouvait être ratée | Curseur `after_number` (A11, mainteneur) ; test 5 |
| **I-3** `totalPrice` ≠ somme des écritures | Retiré ; phrase au §5.2 |
| M-1 FEC dans un `Response` DRF | `HttpResponse` (§5.3) |
| M-2 client de test | motif `APIClient` + `HTTP_HOST` cité (§8) |
| M-3 i18n des messages 400 | `_()` en français (§5.1, §6) |
| M-4 fuseau de `startDate` / `endDate` | fuseau figé du rapport (§5.1) |
| M-5 place de la fonction A10, import de `tasks.py` depuis `fec.py` | dans `comptabilite/tasks.py` ; docstring à jour (§7) |
| M-6 champs en trop | `salesRange`, `totalPrice`, `nature`, `vatRate`, route `GET /closures/{uuid}/` retirés ; `currency` / `amountUnit` gardés et justifiés |
| M-7 sécurité de la clé | doc utilisateur (§7) ; limitation de débit hors fiche (§9) |
| M-8 alerte Sentry | `logger.exception`, à vérifier au brief (§6) |
| M-9 README §6 répondu | marqué dans le README |

## 13. Relecture de sécurité (Opus, 2026-10-13)

Aucun problème critique sur l'API comptable : une clé ne sert que dans son lieu
(`rest_framework_api_key` en TENANT_APPS), la permission passe avant la recherche de la
clôture (sans clé, un uuid inconnu donne 403), la clé n'apparaît dans aucun journal,
la restriction d'IP ne se falsifie pas (nginx impose `X-Real-IP`).

Corrigé dans le code de cette fiche :
- **M-9** `after_number` limité à 18 chiffres (au-delà de 4300, `int()` levait une erreur 500) ;
- **M-13** tests : 403 sur `entries/` et `fec/` avec une clé sans le droit ;
- **M-14** `fec/` acceptait mal `Accept: text/plain` (406) : la route accepte maintenant ce format ;
- **M-8** (choix A2 accepté) : doc utilisateur « quand une personne qui connaissait la clé part, supprimez-la et recréez-en une ».

**Existant, hors de cette fiche — questions au mainteneur** :
- **I-1** DRF garde l'authentification **Basic** par défaut (`DEFAULT_AUTHENTICATION_CLASSES` absent) : on peut essayer des mots de passe sans limite sur toute l'API ;
- **I-2** chaque clé invalide écrit un `logger.error` → un événement Sentry, déclenchable par n'importe qui ;
- **M-1** la date d'expiration d'une clé (`expiry_date`) n'est jamais vérifiée ;
- **M-3** le journal ne dit pas *quelle* clé a servi (ajouter son nom, jamais la clé) ;
- **M-4** `test_api_key` n'est gardée que par `settings.TEST` (elle crée un superuser) ;
- **M-2** aucune limitation de débit sur l'API v2.
