# Newsletter : brouillons Ghost depuis les événements fédérés

## Ce qui a été fait

Un **panneau Newsletter** en haut de la page **Newsletter → Serveur Ghost** de l'admin, avec
trois boutons et les textes d'aide qui vont avec :

- **« Tester la connexion »** — interroge Ghost, ne modifie rien.
- **« Brouillon des 7 prochains jours »** et **« — 30 prochains jours »**.

Ils rassemblent les événements à venir du tenant **et de son réseau fédéré**, en font du HTML
sémantique, et le déposent en **brouillon** dans l'instance Ghost du tenant.

Le résultat s'affiche **dans le panneau**, sous les boutons — pas en toast. (Les
`django.messages` ne sont **pas rendus** sur la page de modification de l'admin : piège
documenté dans `tests/PIEGES.md`.)

> **Rien n'est jamais publié ni envoyé.** Le post est créé en `status: draft`. L'envoi reste
> un geste humain, dans Ghost.

### Le point à comprendre avant de tester

Chaque événement devient une **carte `product` native de Ghost** (image + titre + lieu/date/tarif
+ bouton « Réserver »), suivie de sa description longue en paragraphes, et séparée de la suivante
par un **divider**.

**Lespass n'envoie aucun style.** L'apparence (couleurs, polices, forme des boutons) vient des
**réglages de design newsletter de ton instance Ghost**. Si tu changes ta couleur d'accent dans
Ghost, toutes les newsletters suivent — sans toucher à Lespass.

### Modifications
| Fichier | Changement |
|---|---|
| `newsletter/` | **Nouvelle app**, sans modèle, sans migration |
| `TiBillet/settings.py` | `'newsletter'` dans `TENANT_APPS` |
| `newsletter/views.py` | **Nouveau** — le contrôleur : `viewsets.ViewSet` + `TenantAdminPermission`. La logique n'est **pas** dans l'admin |
| `newsletter/urls.py` | **Nouveau** — routes `/newsletter/admin/…` (non publiques) |
| `Administration/templates/admin/ghost/panneau_newsletter.html` | **Nouveau** — le panneau |
| `Administration/admin_tenant.py` | `GhostConfigAdmin` : juste le `change_form_before_template` et son contexte (+ restauration d'un import à effet de bord, voir plus bas) |
| `tests/pytest/test_newsletter_ghost.py` | **Nouveau** — 52 tests |

---

## Tests à réaliser

### Prérequis : une instance Ghost et une clé Admin

1. Dans **Ghost Admin → Settings → Integrations → Add custom integration**
2. Copier l'**Admin API key** (de la forme `<id>:<secret hexa>`)
3. Dans Lespass : **Newsletter → Serveur Ghost**, renseigner l'**URL** et la **clé**, puis
   **Enregistrer**

> ⚠️ Le menu **Newsletter** n'apparaît que si le **module Newsletter est activé** (dashboard,
> superadmin seulement). Voir `module-newsletter-activation.md`.

> ⚠️ **Enregistre pendant que Ghost est joignable.** `save_model` ne chiffre la clé que si le
> test de connexion réussit — sinon elle est stockée **en clair**. Le code le détecte
> maintenant et affiche un message au lieu de planter, mais il faudra ressaisir la clé.

### Test 1 : le cas nominal

1. Cliquer **« Tester la connexion »**. **Attendu :** une boîte **verte** dans le panneau,
   *« Connexion réussie. »*
2. Cliquer **« Brouillon des 30 prochains jours »**
3. **Attendu :** une boîte **verte** dans le panneau, *« Brouillon créé avec N évènement(s). »*
   + un lien **« Ouvrir dans Ghost → »** — **cliquable**
3. Ouvrir le lien. **Attendu dans l'éditeur Ghost :**
   - le post est en **« Draft »** (jamais publié)
   - chaque événement est une **carte encadrée** (pas un pavé de texte) : image, titre en gras,
     lieu/date/tarif en gris, bouton pleine largeur **à la couleur d'accent de ton site**
   - les blocs sont **manipulables** : tu peux déplacer une image, éditer un bouton, supprimer
     un événement
   - la **description longue** est sous la carte, en texte normal et lisible
4. Vérifier que le champ **Ghost last log** de l'admin porte la trace du succès

### Test 2 : les images

> **En dev local, les images NE S'AFFICHERONT PAS.** Les URLs pointent vers
> `*.tibillet.localhost`, que Ghost ne peut pas joindre. **C'est normal.**
> Les images se vérifient sur **`demo-tibillet.ovh`** ou en prod.

Sur une instance publique : les images doivent s'afficher dans les cartes. Un événement **sans
image propre** doit quand même en avoir une (fallback : image du lieu, puis image de la
configuration du tenant).

### Test 3 : les cas d'erreur

| Manipulation | Attendu |
|---|---|
| Vider l'URL ou la clé, puis cliquer | Boîte **bleue** *« L'instance Ghost n'est pas configurée… »*, **aucun brouillon créé** |
| Mettre une URL bidon (`https://nexistepas.invalid`) | Boîte **rouge** *« Instance Ghost injoignable. »* |
| Mettre une clé fausse mais bien formée | Boîte **rouge** *« La clé Admin API est refusée par Ghost. »* |
| Cliquer « 7 jours » sur un tenant **sans évènement** dans la semaine | Boîte **bleue** *« Aucun évènement… »*, **et surtout aucun brouillon vide dans Ghost** |

> ⚠️ **Si vous cliquez et qu'il ne se passe RIEN :** ce n'est pas le bouton, c'est le serveur
> qui renvoie une erreur. **htmx ne swappe pas sur une 4xx/5xx.** Ouvrez la console (F12) :
> elle affiche `Response Status Error Code 500 from /newsletter/admin/…`. Voir `tests/PIEGES.md`.

### Test 4 : la fédération

Sur un tenant qui fédère des voisins (`Fédération → Espaces fédérés`) :

1. Générer un brouillon de 30 jours
2. **Attendu :** les événements des **voisins** apparaissent, avec **leur** nom d'organisateur
   et un bouton « Réserver » pointant vers **leur** domaine
3. **Attendu :** aucun événement marqué **« Non fédérable » (`private`)** d'un **voisin**
4. Les `tag_filter` / `tag_exclude` des voisins sont respectés (mêmes règles que l'agenda du
   site — cf. `federation-tags-semantique-inversee.md`)

---

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py -v
```

**50 tests.** Aucun ne tape une vraie instance Ghost (`requests.post` est mocké avec
`unittest.mock`).

Les tests de collecte sont des **oracles** : ils recalculent à la main, dans le schéma de chaque
tenant, l'ensemble d'événements attendu, puis vérifient que la collecte produit **exactement**
celui-là — ni moins (événement manquant), ni plus (filtre ignoré). Vérifié par sabotage : un
`return []` ou un `tag_filter` ignoré les fait bien échouer.

Suite complète : **331 tests**.

---

## ⚠️ Point de vigilance : un import à effet de bord restauré

`ruff check --fix` a supprimé, dans `Administration/admin_tenant.py` :

```python
from Administration.admin import (products, prices)
```

Cet import **nu** charge les modules qui enregistrent `ProductAdmin` et `PriceAdmin`. Sans lui,
Django refuse de démarrer (`admin.E039`) — le serveur tombe, et **319 tests partent en erreur**
(la fixture `conftest.py` appelle `manage.py test_api_key`, qui ne boote plus).

Il est restauré **avec `# noqa: F401`** et un commentaire explicite.

**La règle du `CLAUDE.md` / `GUIDELINES.md` est à corriger** : elle affirme que
`ruff check --fix` est « sans danger », en supposant que tous les imports à effet de bord sont
protégés. **Ils ne le sont pas tous.** D'autres sont peut-être nus ailleurs dans le code.

---

## Chaînes traduisibles

Cette feature ajoute **~20 chaînes traduisibles** (msgid en français) :
- `newsletter/collecte.py` et `services.py` : 8
- `newsletter/templates/newsletter/email_evenements.html` : 1 `blocktranslate`
- `Administration/admin_tenant.py` : 11 (libellés des boutons et messages des toasts)

**Le workflow i18n est à lancer par le mainteneur** (`makemessages` / `compilemessages`).

---

## Hors périmètre (évolutions faciles sur cette base)

- **Cron périodique** (brouillon auto chaque lundi / 1er du mois) : les boutons fournissent déjà
  toute la mécanique, il ne resterait qu'à l'appeler depuis Celery.
- **Upload des images vers Ghost** (`POST /images/upload/`) pour figer l'archive du post.
  Aujourd'hui on **référence** les URLs TiBillet : zéro upload, zéro pollution du storage Ghost.
- **Choix de la newsletter Ghost destinataire** quand l'instance en a plusieurs.
- **`Configuration.module_newsletter`** pour en faire un module activable / facturable.

---

## Mise à jour (2026-07-13) — le module est maintenant activable

La configuration Ghost n'est plus dans **« Outils externes »**. Elle vit désormais dans le
groupe **« Newsletter »** de la sidebar, qui n'apparaît **que si le module Newsletter est
activé** (dashboard → carte « Newsletter », **superadmin seulement**).

Voir `module-newsletter-activation.md`.

## Mise à jour — l'import à effet de bord est maintenant protégé POUR DE BON

La section « Point de vigilance » ci-dessus reste vraie, mais le problème est désormais traité
à la racine, en deux couches :

1. **`pyproject.toml`** — `[tool.ruff.lint.per-file-ignores]` : F401 est ignoré sur `admin*.py`,
   `admin/*.py`, `apps.py`, `signals.py`, `triggers.py`, `settings.py`, `__init__.py`.
   **`ruff --fix` ne peut plus y toucher.**
2. **`tests/pytest/test_django_system_checks.py`** — la suite échoue immédiatement si un
   enregistrement d'admin disparaît. Vérifié par sabotage.

Audit au passage : **141 imports F401 « fixables »** dans le projet, et **aucune configuration
ruff** jusqu'ici.
