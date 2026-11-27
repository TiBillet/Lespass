# SPEC — Co-organiser un événement avec un autre lieu TiBillet

> **Hub :** [INDEX.md](INDEX.md)
> **Date :** 2026-11-27 · **Statut :** relue (agent Fable) et corrigée. En attente de validation du mainteneur.
> **Chantier voisin :** [RESEAUX_SOCIAUX](../RESEAUX_SOCIAUX/INDEX.md), qui mentionne les comptes
> du lieu co-organisateur.
>
> **Contraintes projet :** aucune opération git de l'assistant · pas de `makemessages` /
> `compilemessages` automatique · `ruff format` **jamais** sur un fichier existant ·
> pytest dans `lespass_django`, sous `ulimit -v 8000000; timeout 600`.
>
> **Consigne du mainteneur : faire simple.** On ne traite pas les cas qui n'arriveront jamais.

---

## 1. Objectif

Deux lieux montent un événement ensemble. Aujourd'hui, l'événement n'apparaît que dans
l'agenda du lieu qui l'a créé. Le second lieu doit le recréer, ou fédérer tout l'agenda du
premier.

Le lieu A, qui crée l'événement, choisit un **co-organisateur** B parmi les lieux TiBillet.
L'événement apparaît alors **dans les deux agendas**, et la page de l'événement affiche
« Organisé par A et B ». C'est comme l'agenda fédéré, mais **pour cet événement seulement**.

La billetterie reste chez A. Le jour où des tenants « artiste » existeront, le même champ
servira à la coproduction.

---

## 2. Non-objectifs

- Pas d'acceptation par B : A choisit, l'événement apparaît chez B (§6).
- Pas de billetterie chez B. Le bouton « Réserver » de B renvoie déjà vers A.
- Pas plus d'un co-organisateur par événement.
- La fiche détail sur le domaine de B n'est pas modifiée : la carte de l'agenda de B renvoie
  vers `full_url`, sur le domaine de A. C'est suffisant.

---

## 3. Ce qui existe déjà

| Brique | Emplacement | Rôle ici |
|---|---|---|
| `FederatedPlace.tenant` | `BaseBillet/models.py:5693` | Précédent d'une FK d'un modèle de tenant vers `Customers.Client` (schéma public). |
| `federated_events_filter` | `BaseBillet/views.py:3478-3752` | Le moteur de l'agenda. Il construit une liste `tenants` (l. 3521-3567) : les `FederatedPlace`, le lieu courant, puis les lieux trouvés par tags. Chaque entrée porte ses filtres (`tag_filter`, `tag_exclude`). Pour un autre lieu que le lieu courant, `private=False` est appliqué d'office. |
| Fédération par tags | `seo/services.py:736` (`get_tenant_uuids_with_event_tags`) | Le précédent exact : on lit le cache réseau `AGGREGATE_EVENTS`, sans requête entre schémas, pour trouver quels lieux ajouter. |
| `get_events_for_tenants` | `seo/services.py:247` | La requête `UNION ALL` qui remplit `AGGREGATE_EVENTS`. On y ajoute une colonne. |
| Rafraîchissement du cache réseau | `BaseBillet/signals.py:823-836`, `seo/tasks.py:66` | Lancé 5 s après chaque `Event.save()`, et toutes les 4 h. |
| Cache de l'agenda | `BaseBillet/models.py:2979`, `BaseBillet/views.py:3496` | Clé `event_list_version_{tenant.uuid}`, changée à chaque `Event.save()` **du lieu lui-même**. |
| « Organisé par » | `pages/templates/pages/V2/vues/evenement.html:271-274` | Affiche `config.organisation`, la config du lieu **qui affiche la page**. |

---

## 4. Conception

### 4.1 Le champ

`Event.co_organisateur` : `ForeignKey` vers `Customers.Client`, `null=True`, `blank=True`,
`on_delete=SET_NULL`. Dans l'admin d'événement, le choix exclut le lieu courant et les tenants
techniques (catégories `ROOT`, `META`, `WAITING_CONFIG`).

### 4.2 L'agenda de B

1. `get_events_for_tenants` ajoute la colonne `co_organisateur_id` au cache `AGGREGATE_EVENTS`.
2. Une fonction de `seo/services.py`, sur le modèle de `get_tenant_uuids_with_event_tags`, lit
   le cache et renvoie, pour le lieu B, les événements dont il est co-organisateur, groupés par
   lieu d'origine.
3. Dans `federated_events_filter`, chaque lieu d'origine trouvé est ajouté à la liste `tenants`,
   avec un filtre qui ne garde **que** les événements co-organisés avec B. Si ce lieu est déjà
   dans la liste (voisin fédéré), son entrée existante suffit à faire apparaître l'événement,
   à condition que ses filtres de tags ne l'excluent pas. Le builder choisit comment fusionner.

Un événement `private=True` reste invisible chez B, comme pour la fédération : le filtre
`private=False` des autres lieux s'applique aussi ici.

### 4.3 Le cache de l'agenda de B

Dans `Event.save()`, si l'événement a un co-organisateur, on change aussi
`event_list_version_{co_organisateur.uuid}`, en plus de la version du lieu courant. On fait
de même pour l'ancien co-organisateur si le champ a changé.

**Piège :** le cache `default` préfixe chaque clé par le schéma courant
(`TiBillet/settings.py:324`, `KEY_FUNCTION: django_tenants.cache.make_key`). Un `cache.set`
fait depuis A écrirait sous le préfixe de A, et B ne le lirait jamais. L'écriture se fait donc
sous `schema_context(co_organisateur.schema_name)`. Même piège et même parade que les clés de
`seo/tasks.py` (l. 50-62).

**Retard accepté :** quand A **ajoute** un co-organisateur, le cache réseau qui dit à B d'aller
lire chez A n'est reconstruit que 15 à 60 s plus tard. Si l'agenda de B est visité entre les
deux, l'événement peut mettre jusqu'à une heure à y apparaître. C'est déjà le cas de la
fédération par tags. On ne le traite pas.

### 4.4 « Organisé par »

- **Sur la page de A** : « Organisé par A et B ». Le nom de B est sa `Configuration.organisation`,
  lue dans son schéma (`tenant_context`).
- **Bug existant à corriger au passage** : une page d'événement fédéré affichée chez un voisin
  (`federated_events_get`, `BaseBillet/views.py:3433`) montre le nom du voisin, pas celui du lieu
  d'origine. `federated_events_get` lit déjà l'événement dans le schéma d'origine : il y lit
  aussi le nom de l'organisateur et le pose sur l'objet `event`. Le gabarit affiche ce nom quand
  il existe, sinon `config.organisation`.
- Seul le skin V2 affiche « Organisé par ». Le skin classic n'est pas touché.

---

## 5. Tests

- Un événement de A co-organisé avec B apparaît dans l'agenda de B, et **seulement celui-là**
  parmi les événements de A.
- Un événement co-organisé `private=True` n'apparaît pas chez B.
- Modifier l'événement chez A change la version du cache de B, **lue depuis le schéma de B**
  (sinon le test passe à tort).
- Retirer le co-organisateur le fait disparaître de l'agenda de B, au prochain rafraîchissement
  du cache réseau.
- La page de A affiche « Organisé par A et B ».
- La page d'un événement fédéré, affichée chez un voisin, montre le nom du lieu d'origine.
- Chaque test doit être vu **échouer** sur une mutation volontaire avant d'être livré.

---

## 6. Choix faits sans le mainteneur (à confirmer)

- **Pas d'acceptation par B.** Les lieux du réseau se connaissent et coopèrent. Un abus se
  verrait tout de suite, et B pourrait le signaler à A.
- **Un seul co-organisateur.** Une FK reste plus simple qu'un M2M, et suffit à la demande.
- **`private=True` l'emporte** sur la co-organisation.
