# CHANTIER 01 — Observatoire des instances / Instance observatory

**Date :** 2026-11-12
**Statut :** Implémenté, à relire (Fable) puis à commiter par le mainteneur
**Migration :** Oui — `AlterField` sur `SEOCache.cache_type` (ajout d'un choix, aucun SQL)
**Source du prototype :** `~/Téléchargements/observatoire-tibillet/` (fait avec Claude Cowork)
**Relecture :** Fable (2026-11-12), points retenus intégrés ci-dessous.

> **Mis à jour par le chantier 04** ([`CHANTIER-04-usages-hors-argent.md`](CHANTIER-04-usages-hors-argent.md)) :
> compteurs hors argent (billets gratuits et payants, adhésions, locations, ventes
> cashless Fedow), classement par mois d'usage, usages et rythme à la place de la
> nature, catégorie et bidouillage retirés. Les sections 5.4, 5.6 et 6.3 sont à jour ;
> pour le classement, c'est le chantier 04 qui fait foi.

---

## 1. Contexte

Le prototype « Observatoire des instances » montre, pour chaque lieu du réseau,
l'activité mois par mois sur 24 mois : chiffre d'affaires, événements,
inscriptions, billets scannés, adhésions, recharges cashless, cartes actives,
usagers. La page classe ensuite chaque lieu : très actif, actif, peu utilisé,
bidouillage, sommeil. Elle donne aussi sa nature (festival, lieu, mixte,
adhésions, ponctuel) et sa taille. Les seuils de classement se règlent dans la
page, sans relancer le calcul.

C'est du code **pour avoir de l'information**, pas du code métier. Il ne doit
jamais pouvoir ralentir, faire tomber ou exposer la production.

Le prototype n'est pas conforme djc :

- le calcul tourne **pendant la requête HTTP**, lancé par un bouton « Recalculer » ;
- le résultat est un CSV posé sur le disque, dans `Backup/observatoire/` ;
- il recalcule le chiffre d'affaires lui-même, avec une règle fausse (recharges
  de caisse comptées dans le CA, recharge FED `E` oubliée, remboursements ignorés) ;
- les vues sont des fonctions protégées par un décorateur maison ;
- le JS vit dans le gabarit, avec des noms courts, sans i18n, sans `data-testid` ;
- le gabarit charge Google Fonts et Chart.js depuis des CDN.

**Il ne faut PAS lancer `installer.py`.** Le prototype sert de source à lire.

| Fichier du prototype | Ce qu'on en garde |
|---|---|
| `Administration/observatoire/calcul.py` | Les noms des compteurs. Les requêtes sont remplacées (section 5). |
| `Administration/templates/admin/observatoire.html` | Le HTML, le CSS et la logique JS (classement, graphiques, onglet « Sur mesure »). Le JS est **généré** : ses sources ne sont pas fournies. On repart du fichier généré. |
| `vues.py`, `urls.py`, `export_observatoire.py`, `installer.py` | Rien, sauf l'idée de `each_context()` pour le cadre Unfold. |

## 2. Décisions du mainteneur

1. **Le calcul vit dans l'app `seo`.** Elle porte déjà les agrégats cross-tenant (`SEOCache`).
2. **Le calcul se lance SEULEMENT par un cron Celery beat ou par `manage.py`.**
   Aucun bouton, aucune route HTTP ne peut déclencher le calcul.
3. **La page s'affiche dans l'admin Unfold d'un lieu**, dans le groupe
   « Root Configuration » (`Administration/admin/dashboard.py`), réservée au
   superadmin. Le domaine root (schéma public) n'a pas d'admin.
4. **Le classement reste en JavaScript** : il dépend de seuils réglés à la volée.
   Les données arrivent par `{{ donnees|json_script:"observatoire-donnees" }}`.
5. **L'argent vient des clôtures comptables.** On ne recalcule pas le chiffre
   d'affaires : on lit les `ClotureCaisse` de chaque lieu. Les chiffres de
   l'observatoire sont donc ceux des tickets Z. Un lieu legacy apparaîtra dès
   que ses ventes et ses clôtures seront importées, sans changer de code.
6. **Le cache n'expire pas.** Le résultat est stocké dans `SEOCache` (une ligne
   en base), sans copie Memcached. Il n'est remplacé que par le calcul suivant.
7. **Pas de suivi historique des métriques pour l'instant** : voir
   `CHANTIER-02-historique-des-metriques.md` (à faire plus tard).
8. Travail direct dans `/home/jonas/TiBillet/dev/Lespass`, sans worktree.

## 3. Architecture cible

```
Celery beat (chaque nuit, 2 h 30)          manage.py refresh_observatoire
   TiBillet/celery.py                          (dev, ou relance à la main)
   cron_refresh_observatoire()                          |
        |  call_command("refresh_observatoire", par="cron")
        +---------------------+-------------------------+
                              v
        seo/management/commands/refresh_observatoire.py
                              |
                              v
        seo/observatoire.py : calculer_observatoire_du_reseau()
           - 4 requêtes sur le schéma public + 1 appel HTTP à Fedow legacy
           - 8 requêtes par lieu, dans tenant_context()
                              |
                              v
        SEOCache(cache_type=OBSERVATOIRE, tenant=None)   (aucune expiration)

Navigateur du superadmin
   GET /admin/observatoire/   (route ajoutée dans StaffAdminSite.get_urls)
        |  admin_view() : admin du lieu ou superadmin
        v
   seo/views_observatoire.py : page_observatoire()  — LECTURE SEULE
        contrôle RootPermissionWithRequest (superadmin), sinon 403
        lit SEOCache, ajoute les libellés traduits
        render seo/observatoire.html (cadre Unfold + json_script)
        |
        v
   seo/static/seo/observatoire.js : classement + graphiques (Chart.js d'Unfold)
```

## 4. Déclenchement : cron et commande

### 4.1 Commande `seo/management/commands/refresh_observatoire.py`

- Elle appelle `calculer_observatoire_du_reseau(nombre_de_mois, calcule_par)`
  puis écrit le résultat dans `SEOCache` (`update_or_create`).
- Options : `--mois` (défaut 24, minimum 13 : la page compare deux années) et
  `--par` (`"manage.py"` par défaut, `"cron"` depuis le beat).
- Elle écrit sur `stderr` une ligne par lieu avec sa durée, puis un bilan :
  lieux lus, erreurs, durée totale.
- Un lieu en erreur (dont un schéma sans tables) est noté dans `bilan.erreurs` et
  journalisé ; les autres sont lus.
- **Garde-fou :** si aucun lieu n'a été lu, elle lève `CommandError` et
  n'écrit rien. Le dernier bon calcul reste en place.

### 4.2 Beat Celery dans `TiBillet/celery.py`

- Wrapper `@app.task cron_refresh_observatoire()` qui fait
  `call_command("refresh_observatoire", par="cron")` (pattern `cron_refresh_seo_cache`,
  même raison : la course entre `on_after_configure` et `autodiscover_tasks`).
- `crontab(hour=2, minute=30)`. Ce créneau est libre : à 3 h tournent les
  besoins de bénévolat et la purge d'onboarding, toutes les 4 h le cache SEO.
  L'heure est celle de `CELERY_TIMEZONE` (variable `TIME_ZONE`).
- `CELERY_TASK_TIME_LIMIT = 30 min` s'applique. Un calcul tué n'écrit rien.

### 4.3 Interdit

- Aucune vue, aucun formulaire ne lance le calcul. Aucune route POST.
- Cache vide : la page affiche « Aucun calcul pour l'instant. Il sera fait
  cette nuit, ou par `manage.py refresh_observatoire`. » Elle ne lance
  **jamais** le calcul.

## 5. Le calcul : `seo/observatoire.py`

Nouveau fichier, séparé de `seo/services.py`.

### 5.1 Période

- `liste_des_mois(nombre_de_mois)` : les N mois `AAAA-MM`, du plus ancien au
  mois en cours, calculés avec `timezone.localtime()`.
- `premier_jour_de_la_periode` : le 1er jour du mois le plus ancien, à 00:00
  heure locale.

### 5.2 Les lieux lus

`Client.objects.exclude(schema_name="public").exclude(categorie__in=[Client.ROOT, Client.WAITING_CONFIG])`,
comme `seo/services.py:154` et `comptabilite/tasks.py:1130`. Lire un emplacement
`WAITING_CONFIG` pendant que `cron_morning` le migre provoque un interblocage.

### 5.3 Requêtes sur le schéma public : 2 requêtes (+ 2 pour le bloc 5 bis)

**P1 — lieux et nombre d'admins :** la requête 5.2 avec
`.annotate(nombre_de_comptes_admin=Count("user_admin", distinct=True)).order_by("name")`.
`user_admin` est le `related_name` de `TibilletUser.client_admin` (`AuthBillet/models.py:209`).

**P2 — cartes actives :** `fedow_core.Transaction` depuis le premier jour,
`TruncMonth("datetime")`, `.values("tenant_id", "mois")`,
`Count("card", distinct=True)`. Seul le moteur Fedow V2 interne alimente cette
table : la page affiche le bandeau de la section 7.3.

### 5.4 Requêtes dans le schéma de chaque lieu : 6 requêtes (+ 2 pour le bloc 5 bis)

**L1 — clôtures mensuelles.** `ClotureCaisse.objects.filter(niveau=NIVEAU_MENSUEL, datetime_fin__gt=premier_jour)`.
Filtre sur la **fin** : la M du mois le plus ancien d'un lieu à l'est du serveur
(Europe/Paris, serveur en UTC) commence la veille au soir en UTC.
On ne lit que les clés utiles du `rapport_json`, extraites en SQL
(`.values("datetime_debut", "rapport_json__chiffre_affaires", ...)`), jamais
le gros `detail.ventes_par_produit`.

**L2 — clôtures journalières des mois sans clôture mensuelle.** Les J qui
**commencent** après la fin de la dernière M lue (ou après le premier jour s'il n'y a
aucune M), **sauf la J « reprise »**, exclue par `rapport_json__contains={"en_tete": {"reprise": True}}`
(une comparaison de clé vaudrait NULL pour une J sans clé « reprise » et l'exclurait aussi) :
elle couvre tout l'historique d'avant la bascule. Une J est rangée dans le mois
de sa fin. Une J finit à l'heure de fermeture + 2 h, pas à minuit : celle de la
soirée du 31 est déjà dans la M et n'est pas reprise. Limite connue : les ventes
du 1er entre minuit et la fermeture manquent au mois en cours jusqu'à sa M.
Les agrégats L3 à L5 (`TruncMonth`) découpent les mois dans le fuseau du serveur.

**Le mois d'une clôture** se lit dans le fuseau du lieu
(`rapport_json.en_tete.fuseau_horaire`), comme ses bornes.

**Ce qu'on prend dans chaque clôture (M ou J) :**

| Compteur | Clé du `rapport_json` |
|---|---|
| `ca_total` | `chiffre_affaires.total_ttc_en_centimes` |
| `ca_adhesions` | somme des `total_ttc_en_centimes` de `detail.adhesions.*` |
| `ca_billetterie` | somme des `total_ttc_en_centimes` de `detail.billets.*.par_tarif.*` |
| `ca_caisse` | `chiffre_affaires.par_origine.LB.total_ttc_en_centimes` |
| `recharges_ligne` | `annexe.recharges_et_cartes.recharges_encaissees.par_moyen`, moyens Stripe `SN`, `SP`, `SR` (le rapport écarte `SF`, qui n'est pas un moyen d'argent) |
| `recharges_place` | même dictionnaire, tous les autres moyens |

`par_categorie` n'est PAS utilisé : un produit rangé dans une catégorie de caisse y
est classé sous l'uuid de cette catégorie, pas sous `type_A` ou `type_B`. Le détail
(articles reliés à une réservation ou à une adhésion) ne dépend pas de ce rangement.

Les montants restent en centimes jusqu'au JS, qui les affiche en euros.
`ca_total` est lu tel quel : une adhésion vendue en caisse compte à la fois
dans `ca_adhesions` et `ca_caisse`, et le total ne doit pas être reconstruit
par addition. Le NOMBRE de billets et d'adhésions ne vient pas des clôtures : un
billet gratuit ne passe pas toujours par une vente (L4, L5).
Une clé absente d'un rapport vaut 0.

**L3 — événements :** `Event` publiés et sans parent (un créneau de bénévolat est un
sous-événement), par mois de `datetime`, `Count("pk")`.

**L4 — billets :** `Ticket` valides (`NOT_SCANNED`, `SCANNED`), par mois de
`reservation__event__datetime` (jamais `Reservation.created_at`, rempli par sa
migration), une requête : gratuits (offerts, sans tarif vendu, ou tarif vendu à 0),
payants, scannés. Le modèle n'a pas de date de scan.

**L4 bis — adhésions :** `LigneArticle` liées à une adhésion, statuts `P`, `V`, `F`,
par mois de `datetime` (gratuites et renouvellements compris).

**L4 ter — locations :** `Booking` aux statuts `PA`, `AU`, `VA`, `FU`, par mois de
`start_datetime`.

**L5 — usagers distincts :** `Vente` réglées depuis le premier jour, par mois de
`datetime_encaissement`, `Count("client", distinct=True)`. `TibilletUser` est
commun à tous les lieux : un compte n'appartient à aucun lieu, c'est son
activité qui le rattache.

**L6 — points de vente :** `PointDeVente.objects.filter(hidden=False).count()`.

**L7 — Place Fedow legacy :** `FedowConfig.objects.values_list("fedow_place_uuid")`,
jamais `get_solo()` (il crée la ligne). Sert à retrouver les ventes du lieu dans la
réponse de Fedow (`ventes_par_lieu`, clé `uuid.hex`).

**L8 — fédération :** `FederatedPlace.tenant_id` du lieu. Le lieu qui affiche et les
lieux affichés sont marqués `federe` après la boucle.

**Ventes cashless :** V2 en une requête sur le schéma public (`Transaction.SALE` par
lieu et par mois), legacy par l'appel unique à Fedow, fait **avant** la boucle.
Transactions additionnées, porte-monnaie : le plus grand des deux nombres.

### 5.5 Boucle sur les lieux

- `with tenant_context(lieu):` pour chaque lieu de P1.
- Toute exception : on l'ajoute à `erreurs`, `logger.exception`, et on continue.
  Un lieu cassé ne bloque pas les autres.
- Boucles `for` simples, noms longs, pas de compréhension imbriquée.

### 5.6 Coût

| | Prototype | Cible |
|---|---|---|
| Schéma public | 2 + 400 (`count()` des admins) | **4**, + 1 appel HTTP à Fedow (bloc 5 bis) |
| Par lieu | 7, dont 2 qui chargent des lignes | **12** (10 + 2 du bloc 5 bis), toutes agrégées ou extraites en SQL |
| Où ça tourne | requête HTTP | worker Celery, la nuit |

## 5 bis. Le bloc « Le réseau depuis le début »

Demandé pour une présentation (chiffres de l'AAP : lieux, utilisateurs, transactions,
billets, cartes, heures de bénévolat). Ordres de grandeur, rendus par le serveur
(`calcul["reseau"]`), sans JS.

| Chiffre | Source | Règle |
|---|---|---|
| Lieux | requête P1 | lieux lus |
| Utilisateurs | `TibilletUser`, `espece=HUM` (public) | un compte n'appartient à aucun lieu |
| Transactions | **recharges seulement**, par asset : Fedow legacy (route `GET /statistiques_reseau/`, clé root) + moteur V2 (`fedow_core.Transaction` REFILL) | total en euros = assets `FED` et `TLF`. **Le FED ne vient que de Fedow legacy** : le FED du moteur V2 est exclu (aujourd'hui `Asset.save()` le refuse ; la garde sautera à la migration). Pas de calcul des ventes, pas de doublon |
| Billets vendus | `Ticket` valides (scannés ou non), par lieu | dont scannés |
| Cartes cashless | **Fedow legacy seulement** | dont liées à un compte. Les cartes de Lespass ne s'additionnent pas : ce sont les mêmes cartes physiques |
| Heures de bénévolat | `BesoinBenevole` à horaires × inscriptions, par lieu, **plus** les tokens cadeaux (`TNF`) de **Fedow legacy seulement** | fin avant début = lendemain ; journée entière non comptée ; 3 tokens cadeaux = 1 h (montants Fedow en centièmes). Les tokens cadeaux du moteur V2 ne comptent pas : en V2, seul le planning compte |

Si Fedow ne répond pas : `logger.exception` (Sentry), le reste est calculé, la page affiche
« Fedow legacy n'a pas répondu ». Coût ajouté : 2 requêtes sur le public, 1 appel HTTP,
2 requêtes par lieu. Côté Fedow : 2 requêtes agrégées, cache 1 h, base SQLite en WAL.

Décision du mainteneur (2026-11-12) : on ne compte que les cartes et le FED de Fedow
legacy. L'observatoire sera revu quand toute la migration sera faite.

## 6. Le cache

### 6.1 Migration

On ajoute `OBSERVATOIRE = "observatoire"` aux `CACHE_TYPE_CHOICES` de
`seo/models.py`. Django garde les `choices` dans l'état des migrations : il faut
une migration `AlterField`, même si **la base ne change pas**.
`sqlmigrate` doit être vide. Pas de `migrate_schemas` sans l'accord du mainteneur.

### 6.2 Écriture et lecture

- Écriture : `SEOCache.objects.update_or_create(cache_type=SEOCache.OBSERVATOIRE, tenant=None, defaults={"data": donnees})`.
- Lecture : `SEOCache.objects.filter(cache_type=SEOCache.OBSERVATOIRE, tenant__isnull=True).first()`.
- Pas de Memcached : la page est lue quelques fois par semaine, et des chiffres
  internes n'ont rien à faire dans un cache partagé.
- La purge SEO ne touche que les lignes avec lieu (`seo/tasks.py:468`).

### 6.3 Format

```json
{
  "cles": ["evenements", "billets_gratuits", "...15 clés"],
  "mois": ["2024-12", "...", "2026-11"],
  "calcule_le": "2026-11-12T02:30",
  "calcule_par": "cron",
  "bilan": {"lieux_lus": 398, "erreurs": [], "duree_s": 120.4},
  "inst": [
    ["schema", "Nom du lieu", "2023-04-01", 2, 3, true,
     [[...24 valeurs], "... un tableau par clé, dans l'ordre de cles"]]
  ],
  "reseau": {"lieux": 398, "comptes": 9000, "...": "voir 5 bis"}
}
```

- `cles` est **dans le cache** : c'est le contrat entre Python et JS. Le JS le
  lit et ne le redéfinit pas. Ordre : `evenements, billets_gratuits, billets_payants,
  billets_scannes, adhesions, ca_total, ca_billetterie, ca_adhesions, ca_caisse,
  recharges_ligne, recharges_place, locations, transactions_cashless,
  portemonnaies_actifs, usagers`.
- Positions : schéma, nom, création, points de vente, admins, fédéré (booléen), compteurs.

## 7. La page dans l'admin

### 7.1 Route

Dans `Administration/admin/site.py`, `StaffAdminSite.get_urls()`, ajouter à
`routes_des_modules` (import dans la méthode, comme les autres) :

```python
path("observatoire/", self.admin_view(page_observatoire), name="observatoire"),
```

### 7.2 Vue : `seo/views_observatoire.py`

Une **fonction Django**, comme `page_de_module` (`dashboard.py:1606`). Pas de
ViewSet DRF : le réglage global de DRF exige une clé API (`settings.py:543`).

- Méthode autre que GET : `HttpResponseNotAllowed(["GET"])`.
- `RootPermissionWithRequest(request)` faux : `HttpResponseForbidden`.
  `admin_view()` accepte tout admin du lieu : ce contrôle est indispensable.
  `is_staff` n'est lu nulle part.
- Contexte : `staff_admin_site.each_context(request)`, `title`, et
  `donnees_observatoire` = le dict du cache plus les libellés traduits.
- `Cache-Control: no-store`.

### 7.3 Gabarit, JS et CSS

| Fichier | Contenu |
|---|---|
| `seo/templates/seo/observatoire.html` | Hérite de `unfold/layouts/base.html`. HTML, `json_script`, `<link>` et `<script>` vers les statiques. Pas de `<style>` ni de `<script>` en ligne. |
| `seo/static/seo/observatoire.js` | Le JS du prototype, logique et onglet « Sur mesure ». |
| `seo/static/seo/observatoire.css` | Le CSS du prototype, confiné sous `.obs`. Polices Luciole (texte) et Unbounded (titres) de `pages/static/V2/fonts/`. |

Sur le JS :
- **Supprimer** : le CSV, le jeu fictif, le badge « Données fictives », le champ
  « Charger un nouveau calcul », le formulaire « Recalculer », l'encart de
  contrôle du jeu fictif, et le bloc « Ce que chaque indicateur coûte au serveur ».
- **Garder** une phrase : « Les lieux encore en moteur legacy n'ont pas encore
  leurs clôtures dans TiBillet : leurs chiffres apparaîtront après l'import. »
- **Bandeau cartes actives** : « En cours de migration : beaucoup de données
  sont encore dans le Fedow legacy. »
- **Afficher le bilan** près de la date du calcul : lieux lus, en erreur.
- **Renommer en FALC** (`o` → `instance`, `S` → `seuils`, `N` → `nombre_de_mois`…),
  commentaires bilingues, `LOCALISATION`, flux en tête.
- **Ne pas changer les règles de classement** (`classer()`) ni les seuils. Seul
  changement de `preparer()` : `ca_total` est lu, plus reconstruit par addition.
- Natures et activités : clés ASCII internes (`tres_actif`…), libellés traduits à côté.
- Les noms de lieux passent toujours par `esc()` ou `textContent`.
- Chart.js : déjà chargé par Unfold sur toutes les pages (4.4.0). Ne pas l'ajouter.

i18n : le projet n'a pas de `JavaScriptCatalog`. Les textes du JS sont construits
en Python avec `_()`, msgid en français ; les phrases à trous utilisent des
marqueurs `{nombre}` remplis par une fonction JS `remplir(modele, valeurs)`.
Pas de `makemessages` ni de `compilemessages`.

`data-testid` : `observatoire-onglet-standard`, `observatoire-onglet-sur-mesure`,
`observatoire-tuiles`, `observatoire-matrice`, `observatoire-graphique`,
`observatoire-liste`, `observatoire-seuils`, `observatoire-date-calcul`,
`observatoire-vide`. Garder les `role` et `aria-*` du prototype. Chaque graphique
a un équivalent texte.

### 7.4 Menu

Dans `Administration/admin/dashboard.py`, groupe « Root Configuration », après
« Domaines iframe autorises » : titre `_("Observatoire des instances")`, icône
`monitoring`, lien `_safe_rev("staff_admin:observatoire")`, `root_permission`.

## 8. Tests

pytest (`tests/pytest/test_observatoire.py`) :
1. Un lieu avec deux clôtures M donne le CA, les adhésions, la caisse et les
   recharges en ligne / sur place attendus, au bon mois.
2. Une J postérieure à la dernière M compte dans son mois ; la J « reprise » ne compte jamais.
3. Une réservation à 3 billets dont 2 scannés donne `billets_scannes=2` au mois de l'événement.
4. Un client qui achète deux fois dans le mois compte pour `usagers=1`.
5. Les admins d'un lieu sont comptés par P1 ; un lieu `WAITING_CONFIG` n'est pas lu.
6. Un lieu en erreur n'empêche pas les autres d'être lus.
7. Un calcul sans aucun lieu lu n'écrase pas le cache existant.
8. `call_command("refresh_observatoire")` écrit un cache avec `cles`, `mois`, `inst`, `bilan`.
9. `GET /admin/observatoire/` : 403 pour un admin de lieu non superadmin, 200 pour un superadmin.
10. `POST /admin/observatoire/` en superadmin : 405.
11. Cache vide : la page affiche « Aucun calcul » et ne lance aucun calcul.

Chaque test est vu échouer sur une mutation volontaire avant d'être livré.

E2E Playwright : la page se charge en superadmin, le graphique se dessine,
changer un seuil change le comptage d'au moins une catégorie.

Après le travail : `manage.py check`, tests ciblés `seo` et admin.
`ruff check --fix` et `ruff format` **seulement sur les fichiers neufs**.

## 9. Documentation

- `CHANGELOG/2026-11-12-observatoire-instances.md` au format djc.
- `TECH_DOC/SESSIONS/OBSERVATOIRE/INDEX.md` à jour. Lien depuis `SEO/INDEX.md`.
- Journal en bas de cette spec.

## 10. Hors périmètre

- Le CA des caisses des lieux encore sur **LaBoutik V1** : aucune route de LaBoutik ne
  le donne à Lespass (les rapports V1 demandent une session admin), et il faudrait un
  appel par serveur de lieu. Décision du mainteneur (2026-11-12) : il arrivera avec
  l'import des ventes et des clôtures legacy dans Lespass ; l'observatoire le lira alors
  sans changement. La bulle « ? » du CA le dit.
- Les connexions admin (`connexions_admin`) : il faudrait d'abord les enregistrer.
- L'historique des métriques dans le temps : chantier 02.
- L'export CSV. Un calcul incrémental. Changer les règles de classement.
- Le seed de démo par de vraies ventes : `COMPTABILITE/CHANTIER-07-seed-ventes-reelles.md`
  (sans lui, l'observatoire est presque vide en dev).

## 11. Critères d'acceptation

- [ ] Aucune route HTTP ne lance le calcul. Seuls le beat et `manage.py` le font.
- [ ] L'argent vient des clôtures ; 4 requêtes sur le public et 1 appel Fedow, 8 par lieu, aucune ligne chargée en mémoire.
- [ ] Les données vivent dans `SEOCache`, sans expiration. Plus rien dans `Backup/`.
- [ ] La page est dans « Root Configuration », en 403 pour un non-superadmin.
- [ ] Aucune ressource externe (CDN, Google Fonts).
- [ ] Tous les textes passent par `_()` ou `{% translate %}`, msgid en français.
- [ ] Les `data-testid` listés sont présents.
- [ ] Les tests pytest et E2E passent.
- [ ] CHANGELOG et INDEX à jour.

## 12. Journal

| Date | Étape | Note |
|---|---|---|
| 2026-11-12 | Spec v1 | Rédigée à partir du prototype Cowork (dans `SEO/CHANTIER-13`). |
| 2026-11-12 | Relecture Fable | Vue DRF bloquée par `HasAPIKey`, règle du CA fausse, exclusion `WAITING_CONFIG`, garde-fou cache. |
| 2026-11-12 | Spec v2 | Déplacée dans `OBSERVATOIRE/`. L'argent vient des clôtures M et J. Cache sans expiration (`SEOCache` seul). Vue en fonction Django. |
| 2026-11-12 | Audit Fable complet | Corrigé : tuile « Lieux » = lieux lus, bulles « sommeil » (événements datés), rôle `img` du « ? », docs. Retiré : connexions admin de l'affichage, gardes JS sans effet. |
| 2026-11-12 | Relecture Fable du code | Corrigé : M du mois le plus ancien (filtre sur la fin), J à cheval sur la M comptée deux fois, `SF` retiré des recharges en ligne. Retiré : contrôle de format du cache, `schemas_ignores`, positions 2-3 du jeu fictif, détour par `_get`. |
| 2026-11-12 | Bloc réseau | Ajout du bloc « Le réseau depuis le début » et de la route Fedow `statistiques_reseau` (dépôt `../Fedow`). |
| 2026-11-12 | Implémentation | Code, 15 tests pytest et 2 E2E verts, 9 + 2 mutations détectées. Piège trouvé : `.exclude(rapport_json__en_tete__reprise=True)` exclut aussi les J SANS clé « reprise » (NULL en SQL) ; on utilise `rapport_json__contains`. |
| 2026-11-13 | Chantier 04 | Usage hors argent : compteurs, classement par mois d'usage, usages, rythme sur le volume, ventes Fedow legacy par lieu. Voir le chantier 04. |
