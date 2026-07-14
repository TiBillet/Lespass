# NEWSLETTER — Hub du chantier

> **Objet :** générer, depuis Lespass, des **brouillons de newsletter** dans une instance
> **Ghost** auto-hébergée, à partir des **événements du réseau fédéré** du tenant.
> Le brouillon est relu, élagué et envoyé **à la main** depuis Ghost.

**Branche :** `main-newsletter` (partie de `main`)
**Statut :** specs écrites et relues (agent Fable 5). Pas encore de code.

---

## Documents

| Document | Contenu | Statut |
|---|---|---|
| [CHANTIER-01](CHANTIER-01-semantique-tags-federes.md) | **Prérequis.** Redresser la sémantique inversée de `tag_filter` / `tag_exclude` dans le moteur de l'agenda fédéré. | **FAIT** — 270 tests verts. Reste : vérifier les données de prod avant déploiement (§6) |
| [SPEC.md](SPEC.md) | La newsletter : architecture, collecte, rendu, client Ghost, admin, tests. | Validée |
| [PLAN.md](PLAN.md) | Le plan d'implémentation : 6 tâches en TDD, code complet, zéro placeholder. | Relu (Fable 5) et corrigé. **Prêt à dérouler** |

---

## En une phrase

Deux boutons dans l'admin (« Brouillon — 7 jours », « Brouillon — 30 jours ») sur la page
`GhostConfig`. Ils rassemblent les événements à venir du tenant **et de son réseau fédéré**, en
font du HTML sémantique aux conventions Ghost, et le poussent en **brouillon** via l'Admin API.
Rien n'est jamais publié ni envoyé automatiquement.

---

## Les quatre décisions qui structurent tout

1. **Les voisins fédérés sont dans la même base Postgres** (`FederatedPlace.tenant` est une FK vers
   `Client`). On lit donc leurs `Event` complets via `tenant_context()` — descriptions, adresse,
   tarifs, image. Aucun appel HTTP entre instances.

2. **On envoie du HTML sémantique, pas du Lexical JSON, et surtout pas de styles inline.**
   Le convertisseur `?source=html` de Ghost reconstruit ses **cartes natives** (image, bouton,
   divider) à partir des conventions `kg-*` — vérifié dans le source de Koenig. Le format Lexical,
   lui, n'est **pas documenté**. Voir SPEC §4 : c'est le point le moins évident du chantier.

3. **L'apparence est le travail de Ghost**, via ses réglages de design newsletter (couleurs,
   polices, style des boutons). Lespass ne fournit que la structure.

4. **La newsletter doit montrer le même ensemble d'événements que l'agenda du site.** C'est ce qui
   impose CHANTIER-01 : le moteur de l'agenda applique aujourd'hui les tags **à l'envers** de ce que
   promettent les libellés de l'admin.

---

## Le point ouvert (avant de DÉPLOYER CHANTIER-01)

**Combien de `FederatedPlace` ont réellement des tags configurés, en production ?**
Le correctif est écrit et testé, mais il **change le comportement de l'agenda public**. La
commande de comptage est dans [CHANTIER-01 §6](CHANTIER-01-semantique-tags-federes.md).
**Le cas le plus probable (aucun tag configuré, ou des tags posés d'après les libellés de
l'admin) rend le correctif gratuit et sans risque.** Aucune migration de données n'est écrite,
délibérément : elle casserait précisément ce cas-là.

**Au déploiement : vider le cache** — l'agenda met en cache la page 1 et les pages par date.

---

## État d'avancement

- [x] Exploration Ghost (Admin API, Lexical, cartes Koenig, design newsletter)
- [x] Spec (`SPEC.md`) + relecture Fable → 1 erreur bloquante + 5 factuelles corrigées
- [x] Prérequis `CHANTIER-01` (sémantique des tags) — **codé, testé, vérifié au navigateur**
- [x] Plan (`PLAN.md`) + relecture Fable → tests à vide et « règle d'or » fausse corrigés
- [x] **Code livré — 331 tests verts**, relu par Fable après chaque tâche
- [x] **Validé bout-en-bout contre une vraie instance Ghost 6.52** (cartes natives) **et contre
      les données de production** (images chargées)
- [ ] Vérifier les `FederatedPlace` en production, puis déployer CHANTIER-01
- [ ] Workflow i18n (~20 chaînes ajoutées) — **au mainteneur**

## Ce qui a été livré

| Livrable | Où |
|---|---|
| App `newsletter/` (sans modèle, sans migration) | `newsletter/` |
| Deux actions dans l'admin Ghost | `Administration/admin_tenant.py` |
| 50 tests newsletter + 11 tests API | `tests/pytest/` |
| Correctif de la sémantique des tags fédérés | `BaseBillet/views.py` |
| **Bonus** : `?only_futur=1` réparé (500 systématique) + `next_days=N` | `api_v2/`, `ApiBillet/` |
| Fiches de test manuel | `A TESTER et DOCUMENTER/` (2 fichiers) |

## Bugs trouvés en chemin (hors périmètre, à arbitrer)

1. **`ruff check --fix` a supprimé un import à effet de bord** dans `admin_tenant.py` →
   `admin.E039`, Django ne démarre plus. Restauré et protégé. **La règle du `CLAUDE.md`
   affirmant que `--fix` est « sans danger » est à corriger.**
2. **L'agenda ne filtre pas `archived`** (`BaseBillet/views.py`), alors que `seo/services.py`
   le filtre partout. Un événement archivé disparaît de la carte mais reste sur l'agenda.
3. **L'API v2 renvoie les images en URL relative** — inexploitable par un client externe.
4. **`ghost_last_log` stocke la réponse brute de `/members/`** (`test_api_ghost_admin_button`)
   → des **emails d'adhérents** (données personnelles) finissent en base et s'affichent dans
   l'admin.
5. **La base de dev est polluée** par les événements créés par les tests d'intégration
   (`test_event_create.py` ne fait pas de rollback) : « Refund Event 9q6mwub7 »…
