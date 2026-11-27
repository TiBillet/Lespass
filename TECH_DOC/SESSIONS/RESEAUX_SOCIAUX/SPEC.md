# SPEC — Publication automatique des événements sur Instagram et Mastodon

> **Hub :** [INDEX.md](INDEX.md)
> **Date :** 2026-11-27 · **Statut :** relue (agent Fable) et corrigée. En attente de validation du mainteneur.
> **Chantier voisin, indépendant :** [CO_ORGANISATION](../CO_ORGANISATION/INDEX.md).
> **Histoire :** remplace la piste [POSTIZ](../POSTIZ/INDEX.md). Postiz a été étudié puis écarté (§4).
>
> **Contraintes projet :** aucune opération git de l'assistant · pas de `makemessages` /
> `compilemessages` automatique · serveur tenu par le mainteneur dans byobu ·
> `ruff format` **jamais** sur un fichier existant · `ruff check --fix` avec inspection des
> imports à effet de bord · pytest toujours dans `lespass_django`, sous `ulimit -v 8000000; timeout 600`.

---

## 1. Objectif

Un lieu annonce ses événements sur Instagram et sur Mastodon. Aujourd'hui, il le fait à la main.
Il oublie souvent la relance, et personne ne sait ce qui est vraiment parti.

Lespass doit **programmer et publier tout seul** les annonces d'un événement, une fois que
l'admin a validé les textes. Le récap quotidien dit ensuite ce qui a été programmé et ce qui a
été publié, avec le lien vers le post.

**Le rythme par défaut** (modifiable par lieu, dans le singleton) :

| Quand | Instagram | Mastodon |
|---|---|---|
| J-7, 12 h | post (image principale + carrousel) | post (image principale + carrousel) |
| Veille, 16 h | story | — |
| Jour J, 10 h | story | post de relance |

Mastodon n'a pas de story : la relance y est un post normal, le jour J.

---

## 2. Décisions prises avec le mainteneur

1. **Pas de Postiz.** On écrit une app Django « Réseaux sociaux » qui parle directement aux API
   d'Instagram et de Mastodon (§4).
2. **Deux réseaux seulement : Instagram et Mastodon.**
   - **X** est sorti : son API est payante depuis février 2026 (environ 0,20 $ par post avec lien).
   - **Facebook** est sorti : le lieu repartage à la main depuis Instagram.
   - **TikTok** est reporté : sans audit, une app ne publie que sur des comptes privés.
3. **L'app Meta reste en mode développement.** C'est l'app existante `tibillet-postiz`. Chaque
   compte Instagram de lieu y est ajouté comme **testeur Instagram**, à la main, par Code Commun.
   Aucune App Review.
4. **Uniquement les événements.** Pas de post libre, pas de calendrier éditorial.
5. **Le booléen `communication_envoyee` devient un statut à choix** (§7.3).
6. **Les textes sont pré-remplis depuis un modèle**, puis relus et validés par l'admin dans un
   onglet « Réseaux sociaux » du formulaire d'événement, **avant** de changer le statut.
7. **Les comptes à mentionner sont des fiches séparées** de l'événement, réutilisables d'un
   événement à l'autre (§7.2).
8. **Mastodon multi-instance** : chaque lieu peut être sur une instance différente.
9. **Le menu :** l'app Newsletter passe dans la section « Réseau » de la barre latérale. La
   nouvelle app « Réseaux sociaux » y va aussi (§8, chantier 01).

---

## 3. Non-objectifs et anti-objectifs

**Non-objectifs :**
- Publier sur Facebook, X, TikTok, LinkedIn ou Bluesky.
- Les statistiques, les commentaires, les messages privés.
- La vidéo et les reels.
- Un rythme différent pour chaque événement : le rythme est **réglé par lieu**.
- La validation de l'app par Meta (App Review).

**Anti-objectifs** (le projet échoue, même si tout marche techniquement) :
- **Un post part sans que l'admin ait validé ses textes.** Le passage à « Com' en attente »
  est le seul déclencheur.
- **La migration programme des annonces en masse** pour les événements existants (§7.3).
- **Un jeton d'accès apparaît en clair** en base ou dans les logs.
- **Un nouveau service à héberger** (pas de Temporal, pas de file à part). Celery suffit.

---

## 4. Approches considérées

| Approche | Pour | Contre | Choix |
|---|---|---|---|
| **A. App Django sans Postiz** | Rien à héberger en plus. Multi-tenant natif. Mastodon multi-instance trivial. Le lien du post est connu dès la publication. | Environ 1 000 lignes Python à écrire. On suit nous-mêmes les changements d'API de Meta. | **Retenue** |
| B. Pont vers un Postiz auto-hébergé | ~500 lignes côté Lespass. Postiz suit les API. | Une stack de 8 conteneurs (~2,2 Gio). Une organisation par lieu, à créer par script (inscription verrouillée). Webhook bugué avant la v2.24. Mastodon mono-instance (`MASTODON_URL` global, `mastodon-custom` commenté). | Écartée |
| C. Postiz Cloud | La validation Meta est déjà faite par Postiz. | Un abonnement payant par lieu. Une dépendance extérieure. | Écartée |

Ce qui a fait pencher vers A : les lieux n'utilisent Postiz **que** pour les événements. Toute
l'interface de Postiz (calendrier, posts libres, équipe) ne sert à rien ici.

**La validation Meta ne change pas entre A et B :** elle porte sur une app Meta, pas sur le
logiciel. Un Postiz auto-hébergé utilise déjà notre app `tibillet-postiz`.

Le code de Postiz (AGPL-3, comme Lespass) sert de **référence de lecture** pour les appels aux
API. On ne le porte pas : les fichiers des providers mélangent publication, statistiques,
commentaires et IA. Clone local : `~/Gits/postiz/github/postiz-app`
(`libraries/nestjs-libraries/src/integrations/social/instagram.standalone.provider.ts`,
`instagram.provider.ts` pour le cycle conteneur → publication, `mastodon.provider.ts`).

---

## 5. Contraintes externes (vérifiées)

### Instagram — « Instagram API with Instagram Login »

C'est le provider `instagram-standalone` de Postiz. Il publie sur un compte Instagram
**professionnel** (Business ou Creator), **sans** Page Facebook. Il est déjà testé en réel sur
`@lafilature_villeurbanne` (notes : `~/Gits/postiz/docs/superpowers/specs/2026-07-30-notes-oauth-instagram.md`).

- **Mode dev :** seuls les comptes testeurs peuvent autoriser l'app. L'ajout se fait dans la
  console Meta (« Rôles dans l'application » → « Testeur(se) Instagram »). Le lieu accepte
  ensuite l'invitation dans Instagram (Paramètres → Applications et sites Web → Invitations à
  tester). **Meta demande le mode Live pour un usage en production :** si Meta restreint l'app,
  tous les lieux sont coupés d'un coup. Risque accepté.
- **Deux identifiants différents :** l'« ID d'app Instagram » (`1002853442802118`) n'est pas
  l'App ID Meta (`1521732185886543`). Le client OAuth est l'**ID d'app Instagram**.
- **Permissions à demander :** `instagram_business_basic` et `instagram_business_content_publish`.
  Attention : Meta valide toutes les permissions **du cas d'utilisation**, pas seulement celles
  du paramètre `scope`. Il faut donc toutes les activer dans la console. Sur l'écran de
  consentement, le lieu ne doit retirer aucun interrupteur.
- **Adresse de retour OAuth :** elle doit être déclarée à l'avance, en correspondance exacte.
- **Jeton :** le jeton long dure **60 jours**. On le renouvelle par
  `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token`. Il doit
  avoir plus de 24 h et être encore valide.
- **Images :** **JPEG uniquement**, servies en **HTTPS public** (Meta va les chercher par URL).
  Ratio du post : entre 4:5 et 1,91:1. Story : 9:16. Carrousel : 10 images au maximum.
- **Publication en deux temps :** on crée un conteneur (`POST /{ig-user-id}/media`), on attend
  que son `status_code` soit `FINISHED`, puis on publie (`POST /{ig-user-id}/media_publish`).
  Le lien s'obtient ensuite par le champ `permalink` du média.
- **Story :** `media_type=STORIES`. **Aucun texte** possible par l'API.
- **Limite :** 100 publications par API et par 24 h, par compte. Sans effet ici.

**Conséquence en dev :** les images de `*.tibillet.localhost` ne sont pas publiques. La
publication Instagram se teste en **préprod**, ou par des tests qui simulent les appels HTTP.

### Mastodon

- **Connexion par jeton collé**, sans OAuth : le lieu crée une application dans son instance
  (Préférences → Développement → Nouvelle application). Portées : `write:statuses`,
  `write:media`, `read:accounts`. Il colle l'URL de l'instance et le jeton dans Lespass.
- **Images envoyées en fichier** (`POST /api/v2/media`), donc **pas besoin d'URL publique**.
  4 images au maximum. Pas de contrainte de format.
- **Post :** `POST /api/v1/statuses` avec `status`, `media_ids[]` et `visibility=public`. La
  réponse contient `url` : c'est le lien du post.
- **Limite :** 500 caractères sur la plupart des instances. L'instance annonce sa vraie limite
  dans `GET /api/v2/instance` (`configuration.statuses.max_characters`).
- **Vérification du jeton :** `GET /api/v1/accounts/verify_credentials`. Elle renvoie aussi
  le nom du compte.

---

## 6. Ce qui existe déjà

| Brique | Emplacement | Rôle ici |
|---|---|---|
| `Event.communication_envoyee` | `BaseBillet/models.py:2372` | Le booléen à transformer en statut. Champ interne : jamais dans les serializers d'API ni dans l'export CSV (commentaire l. 2357-2361). |
| `Event.img` (StdImage) | `BaseBillet/models.py:2447` | Facultative. Une variation StdImage garde le format du fichier source (PNG reste PNG) : elle ne sert donc pas pour Instagram (§7.5). |
| `Event.get_img()` | `BaseBillet/models.py:2503` | Repli à trois niveaux : image de l'événement, sinon du lieu, sinon de la configuration. C'est la source de l'image principale. |
| `Event.carrousel` → `Carrousel` | `BaseBillet/models.py:2566`, `:396` | Images du carrousel, triées par `order`. Variations `fhd`, `hdr` (720 px), `med`, sans recadrage. |
| `_duplicate_event` | `Administration/admin_tenant.py:4929-4950` | Copie tous les champs (`pk = None`) et ne remet que `published=False`. |
| `Event.full_url` | calculé dans `save()`, l. 2954 | Le lien vers l'événement, à mettre dans les textes. |
| `Configuration.fuseau_horaire` | `BaseBillet/models.py:594` | Les heures du rythme sont en heure locale du lieu. |
| `GhostConfig` | `BaseBillet/models.py:5734` | Le modèle à copier pour le singleton : clé chiffrée Fernet, `get_api_key()` / `set_api_key()`. |
| `GhostConfigAdmin` | `Administration/admin_tenant.py:6720` (`save_model` l. 6804-6820) | Le modèle à copier pour l'admin du singleton. **Piège connu :** si le test d'API échoue, la clé reste en clair. La garde est dans `newsletter/services.py:53-92`. |
| `EventAdmin` | `Administration/admin_tenant.py:4405` | Le formulaire d'événement. `communication_envoyee` y est dans `list_display` (l. 4493), `list_editable` (l. 4498) et le fieldset « Interne (non publié) ». Il n'a pas d'onglets aujourd'hui. Exemple d'onglets : `ConfigurationAdmin` (l. 515-580). |
| Barre latérale | `Administration/admin/dashboard.py` | `DOMAINES` (l. 119-145) contient déjà `lerezo` « Réseau ». `MODULE_FIELDS["module_newsletter"]` (l. 2461) a `"domaine": "lespass"` (l. 2466). |
| Récap quotidien | `Administration/recap_quotidien.py` | Liste des rubriques écrite en dur dans `rubriques_de_la_veille()` (l. 962-990). Contrat d'une rubrique : `{"cle","titre","nombre","lignes","nombre_de_lignes_cachees","lien"}` ou `None`. Une ligne est une chaîne ou `{"texte","lien"}`. Aide : `_construire_la_rubrique` (l. 331). Exemple récent : commit `7c536a84`. |
| Retour central dans le schéma public | `TiBillet/urls_public.py:10` | `api/webhook_stripe/` reçoit déjà, à une seule adresse, des appels pour tous les lieux. Même idée pour le retour OAuth Instagram. |
| Boucle Celery sur les lieux | `booking/tasks.py:497-522`, `comptabilite/tasks.py:1112-1142` | Les deux façons de faire une tâche périodique par lieu. Les tâches périodiques se déclarent dans `TiBillet/celery.py` (`setup_periodic_tasks`). |
| Fernet | `fernet_encrypt` / `fernet_decrypt` | Déjà utilisés par `GhostConfig`, `BrevoConfig`, `FormbricksConfig`. |
| `requests` | `pyproject.toml` | Déjà là. **Aucune nouvelle dépendance.** |

---

## 7. Conception

### 7.1 L'app `reseaux_sociaux`

- Une nouvelle app Django `reseaux_sociaux`, dans **`TENANT_APPS`** : toutes ses tables vivent dans
  le schéma de chaque lieu.
- Un drapeau de module `Configuration.module_reseaux_sociaux`, sur le modèle de
  `module_newsletter` (`BaseBillet/models.py:732`). Son entrée dans `MODULE_FIELDS` a pour
  domaine `lerezo`.
- Une entrée dans la barre latérale, section « Réseau », visible si le module est actif :
  « Configuration » (le singleton) et « Comptes à mentionner » (les fiches).

### 7.2 Les modèles

**`ConfigurationReseauxSociaux`** (`SingletonModel`) — un par lieu :

| Groupe | Champs |
|---|---|
| Mastodon | `mastodon_url_instance`, `mastodon_jeton` (Fernet), `mastodon_nom_du_compte` (rempli par `verify_credentials`, sous la forme `@nom@instance`), `mastodon_limite_de_caracteres` (lue une fois à la connexion dans `GET /api/v2/instance`, 500 par défaut) |
| Instagram | `instagram_identifiant_utilisateur`, `instagram_nom_du_compte`, `instagram_jeton` (Fernet), `instagram_jeton_obtenu_le`, `instagram_renouvellement_echoue_le` (rempli quand le renouvellement échoue, vidé quand il réussit) |
| Rythme | `jours_avant_le_post` (7), `heure_du_post` (12:00), `heure_story_veille` (16:00), `heure_story_jour_j` (10:00), `heure_relance_mastodon` (10:00) |
| Modèles de texte | `modele_texte_instagram`, `modele_texte_mastodon`, `modele_texte_relance_mastodon` |

Méthodes `get_…_jeton()` / `set_…_jeton()` comme `GhostConfig`. Un jeton n'est **jamais**
affiché dans l'admin, ni écrit dans un log.

**`FicheReseauxSociaux`** — un compte à mentionner (artiste, collectif, partenaire) :
`nom`, `instagram` (sans `@`), `mastodon` (sous la forme `nom@instance`). Elle est réutilisée
d'un événement à l'autre. Elle n'a pas de lien vers `Client` : un lieu co-organisateur est
mentionné par ses propres comptes connectés (§7.5).

**`PreparationCommunication`** — `OneToOneField` vers `Event`, créée à la première ouverture de
l'onglet :
- `texte_instagram`, `texte_mastodon`, `texte_relance_mastodon` ;
- `comptes_a_mentionner` (M2M vers `FicheReseauxSociaux`) ;
- `image_post` et `image_story`, deux images **optionnelles** qui remplacent les variations
  générées depuis `Event.img`.

Ce modèle vit dans `reseaux_sociaux` et pointe vers `Event` : `BaseBillet` ne dépend pas de la
nouvelle app.

**`Publication`** — une annonce prévue sur un réseau :
`event` (FK), `reseau` (`instagram` | `mastodon`), `format` (`post` | `story`),
`moment` (`avant` pour J-7, `veille`, `jour_j`), `date_prevue`, `etat` (`prevue` | `publiee` | `echec`), `url`, `identifiant_sur_le_reseau`,
`message_d_erreur`, `traitee_le` (moment de la tentative, réussie ou non), `creee_le`.

Une `Publication` **ne stocke pas de texte**. Le texte est lu dans `PreparationCommunication` au
moment de l'envoi. Un texte corrigé après la programmation part donc dans sa dernière version.

### 7.3 Le statut de communication sur `Event`

Le booléen `communication_envoyee` devient `statut_communication` (CharField à choix) :

| Valeur | Libellé | Qui le pose |
|---|---|---|
| `N` | Pas besoin de com' | l'admin (valeur par défaut) |
| `A` | Com' en attente | l'admin, après avoir validé les textes |
| `P` | Programmée | Lespass, dès que les publications sont créées |
| `F` | Faite | Lespass, quand plus aucune publication n'est `prevue` |

**Migration :** `True` → `F`, `False` → `N`. Ainsi, aucun événement existant n'est programmé.
Le test `tests/pytest/test_event_champs_internes.py` (l. 8, 22, 112) est à adapter. Le champ
reste interne : jamais dans l'API ni dans l'export CSV.

Le statut reste **éditable dans la liste** (`list_editable`), comme le booléen aujourd'hui.

**Les choix proposés à l'admin :**
- **Module éteint** (la plupart des lieux) : seulement « Pas besoin » et « Faite ». Le champ se
  comporte comme l'ancienne case à cocher.
- **Module actif** : les quatre choix. « Programmée » est normalement posé par Lespass. Le
  choisir à la main ne programme rien, et ce n'est pas bloqué : c'est sans danger.
- Poser « Faite » ou « Pas besoin » à la main sur un événement « Programmée » supprime ses
  `Publication` `prevue`.

**Duplication d'un événement :** `_duplicate_event` remet le statut à « Pas besoin ». Sinon, le
doublon naîtrait « Programmée », sans aucune publication.

### 7.4 Connecter les comptes

**Mastodon :** dans l'admin du singleton, l'admin colle l'URL de l'instance et le jeton. À
l'enregistrement, Lespass appelle `verify_credentials`.
- Si l'appel réussit, le jeton est chiffré et le nom du compte est enregistré.
- Si l'appel échoue, **le jeton n'est pas enregistré** (le reste du formulaire l'est) et
  l'admin voit un message d'erreur. Le piège du jeton laissé en clair de `GhostConfigAdmin` ne
  doit pas se reproduire.

**Instagram :** un bouton « Connecter Instagram » dans l'admin du singleton.
1. Lespass redirige vers `https://www.instagram.com/oauth/authorize` avec l'ID d'app Instagram,
   les deux permissions, et un `state` **signé** (`django.core.signing`, durée de vie courte)
   qui contient l'UUID du lieu.
2. Instagram renvoie vers **une seule adresse de retour**, servie par le schéma public (comme
   `api/webhook_stripe/`). C'est la seule adresse à déclarer dans la console Meta.
3. Cette vue vérifie la signature du `state`, retrouve le lieu, échange le code contre un jeton
   court, puis le jeton court contre un jeton long (60 jours). Elle enregistre le jeton, l'id
   et le nom du compte dans le singleton du lieu (`tenant_context`).
4. Elle redirige vers l'admin du lieu, avec un message de succès ou d'échec.

L'ID et le secret de l'app Instagram sont des **variables d'environnement** (communs à tous les
lieux), jamais en base.

**Renouvellement du jeton :** une tâche Celery quotidienne renouvelle les jetons Instagram
obtenus il y a plus de 30 jours. Un jeton qui échoue au renouvellement est signalé dans le récap.

### 7.5 L'onglet « Réseaux sociaux » du formulaire d'événement

L'onglet est un **inline** (`PreparationCommunication`, `tab = True`). Il n'apparaît que si le
module est actif, et seulement sur un événement déjà enregistré. Le **statut** reste dans le bloc
« Interne (non publié) », où il est aujourd'hui : il sert aussi aux lieux sans le module.
L'onglet contient :

```
[ Réseaux sociaux ]
 Comptes à mentionner : [Artiste X ×] [Collectif Y ×] [+]
 Texte Instagram (post J-7)       [.............]  1 240 / 2 200
 Texte Mastodon (post J-7)        [.............]    312 / 500
 Texte Mastodon (relance jour J)  [.............]     98 / 500
 [ ] Régénérer les textes depuis le modèle
 Image post  [aperçu 4:5]  [Remplacer…]
 Image story [aperçu 9:16] [Remplacer…]
 Publications : J-7 12:00 Insta post — prévue · …   (lecture seule)
```

**Les textes** sont pré-remplis depuis les modèles du singleton : la `PreparationCommunication`
est créée, textes remplis, à la première ouverture de la fiche de l'événement. Les
variables disponibles : `{nom}`, `{date}`, `{heure}`, `{lieu}`, `{lien}`, `{mentions}`,
`{description_courte}`, `{description_longue}`. Le remplacement est un simple
`str.replace` : pas de moteur de template.

- `{mentions}` **reste tel quel** dans le texte validé. Lespass le remplace au moment de
  l'envoi, réseau par réseau : `@nom` sur Instagram, `@nom@instance` sur Mastodon. Les comptes
  mentionnés sont ceux des fiches. Une fois [CO_ORGANISATION](../CO_ORGANISATION/INDEX.md)
  livré, s'y ajoutent les comptes connectés du lieu co-organisateur, lus dans son schéma
  (chantier 05).
- La case « Régénérer les textes depuis le modèle » écrase les trois textes à l'enregistrement.
  Pas de bouton ni de JavaScript.
- Le serveur **refuse l'enregistrement** si un texte dépasse sa limite : 2 200 caractères pour
  Instagram, la limite de l'instance pour Mastodon (500 par défaut). Le compte se fait après le
  remplacement des mentions.

**Les images :**
- **L'image principale** est celle de `Event.get_img()` (repli événement → lieu → configuration).
  Si `image_post` ou `image_story` est rempli, il la remplace pour ce format.
- **Pour Instagram**, une seule fonction Pillow fabrique le fichier au moment de l'envoi :
  recadrage centré (`ImageOps.fit`) à 1080×1350 pour un post, 1080×1920 pour une story,
  conversion en **JPEG**, écriture dans un dossier média public, puis URL absolue donnée à
  Instagram. Elle sert aussi aux images du carrousel et aux images de remplacement. On n'ajoute
  **pas** de variation StdImage : une variation garde le format source, et n'aurait pas réglé le
  JPEG. Pas de `rendervariations` au déploiement.
- **L'aperçu dans l'onglet** est fait en CSS (`aspect-ratio` + `object-fit: cover`) sur l'image
  source. Il montre le même recadrage centré, sans code serveur.
- **Pour Mastodon**, le fichier d'origine de l'image part tel quel. Sans image principale, le
  post part avec le carrousel seul, ou en texte seul.
- **Le post Instagram** : image principale, puis les images du carrousel dans leur ordre,
  10 au maximum. Une seule image donne un post simple. Plusieurs donnent un carrousel.
- **Le post Mastodon** : image principale, plus les 3 premières du carrousel. Sans aucune
  image, le post part en texte seul.
- **La story** : l'image story seule.

### 7.6 Programmer

L'admin passe le statut à « Com' en attente » et enregistre. Lespass, après l'enregistrement
des inlines :
1. Vérifie que l'événement est publié et non archivé, qu'au moins un réseau est connecté, et
   que les textes des réseaux connectés ne sont pas vides. Si Instagram est connecté, il faut
   aussi une image (`get_img()` ne renvoie rien que si le lieu n'en a aucune). Sinon : message
   d'erreur, rien n'est créé, et le statut reste « Com' en attente ».
2. Calcule les dates depuis le rythme, en heure locale du lieu :
   - post Instagram et post Mastodon : J-`jours_avant_le_post`, à `heure_du_post` ;
   - story Instagram : veille, à `heure_story_veille` ;
   - story Instagram et relance Mastodon : jour J, à `heure_story_jour_j` /
     `heure_relance_mastodon`.
3. Supprime les `Publication` `prevue` de l'événement, puis crée une `Publication` par annonce,
   **seulement pour les réseaux connectés**, et **seulement pour les couples (réseau, moment)
   qui n'ont pas déjà une `Publication` `publiee`**. Ainsi, reprogrammer ne publie jamais deux
   fois la même annonce. Les `Publication` en `echec` restent en base, pour l'historique.
4. Passe le statut à « Programmée ».

**Une date déjà passée :**
- Un **post J-7** dont la date est passée part **tout de suite**, si l'événement n'a pas encore
  commencé.
- Une **story** ou une **relance** dont la date est passée **n'est pas créée**.

### 7.7 Publier

Une tâche Celery périodique (toutes les 10 minutes) parcourt les lieux qui ont le module actif.
Pour chaque `Publication` `prevue` dont la date est passée :
- elle fabrique le texte final (remplacement de `{mentions}`) ;
- elle publie sur le réseau (§5) ;
- en cas de succès : `etat=publiee`, `url`, `identifiant_sur_le_reseau`, `traitee_le` ;
- en cas d'échec : `etat=echec`, `message_d_erreur` et `traitee_le`. **Pas de nouvel essai automatique.**
  Le statut de l'événement revient à « Com' en attente », et l'échec apparaît dans le récap.

**Relancer après un échec :** l'admin corrige la cause (texte, jeton, image), puis enregistre
l'événement, toujours en « Com' en attente ». La programmation (§7.6) recrée les annonces qui
n'ont pas été publiées. Un post J-7 dont la date est passée part alors tout de suite. Il n'y a
pas de bouton « relancer » à part.

Quand un événement encore « Programmée » n'a plus de `Publication` `prevue`, son statut passe
à « Faite ». (Un échec l'a déjà fait revenir à « Com' en attente ».)

Une même `Publication` ne doit jamais partir deux fois, même si deux exécutions de la tâche se
chevauchent. La façon de le garantir est laissée au builder (verrou de ligne, ou passage par un
état intermédiaire).

**Instagram :** l'attente du conteneur (`status_code` `IN_PROGRESS` → `FINISHED`) se fait dans
la tâche, avec quelques essais espacés. Au-delà, c'est un échec.

### 7.8 Quand l'événement change

Si un événement est **« Programmée »** :
- sa **date change** : on reprogramme (§7.6). Les annonces déjà publiées ne sont pas recréées ;
- il est **dépublié** (`published=False`) ou **archivé** : on supprime ses `Publication`
  `prevue`, et le statut revient à « Com' en attente » ;
- l'admin remet le statut à **« Pas besoin »** : on supprime ses `Publication` `prevue`.

Une publication déjà `publiee` n'est jamais supprimée, ni sur le réseau, ni en base.

**Garde-fou au moment de publier :** l'archivage par l'action de ligne de la liste, et les
modifications faites par l'API, ne passent pas par la fiche admin. La tâche de publication
revérifie donc l'événement : s'il est dépublié ou archivé, elle supprime ses annonces prévues,
remet le statut à « Com' en attente », et ne publie rien.

Tout est local : il n'y a rien à annuler chez un service tiers.

### 7.9 Le récap quotidien

Deux rubriques ajoutées dans `rubriques_de_la_veille()`, visibles si le module est actif :

- **« Communication programmée »** : les événements passés à « Programmée » pendant la période.
  Une ligne par événement : nom, et dates des annonces. Le lien va vers l'onglet « Réseaux
  sociaux » de l'événement dans l'admin.
- **« Communication publiée »** : les `Publication` traitées pendant la période (`traitee_le`),
  avec le lien `url` vers le post. Les **échecs** de la période y figurent aussi, avec leur message. Un jeton
  Instagram qui n'a pas pu être renouvelé y figure également.

### 7.10 Le menu (chantier 01, indépendant)

- `MODULE_FIELDS["module_newsletter"]["domaine"]` passe de `"lespass"` à `"lerezo"`
  (`Administration/admin/dashboard.py:2466`). Newsletter s'affiche alors dans « Réseau ».
- Deux textes du même fichier disent le contraire et sont à mettre à jour : le commentaire des
  lignes 3117-3122 (« newsletter et réseaux sociaux vivent dans le domaine Lespass ») et le
  sous-titre du domaine `lespass` (l. 123), qui cite « newsletter ».
- `module_reseaux_sociaux` est déclaré directement avec le domaine `lerezo`.

---

## 8. Découpage en chantiers

| Chantier | Contenu | Dépend de |
|---|---|---|
| **01 — Menu** | Newsletter dans « Réseau » (§7.10). | rien |
| **02 — Socle + Mastodon** | App, modèles, statut et sa migration, singleton, fiches, onglet, programmation, tâche de publication, suivi des changements, pour **Mastodon seul**. Testable de bout en bout en dev (pas d'URL publique nécessaire). | rien |
| **03 — Instagram** | Connexion OAuth avec retour central, renouvellement du jeton, fabrication des JPEG recadrés, publication post / carrousel / story. Test réel en préprod. | 02 |
| **04 — Récap** | Les deux rubriques du récap. | 02 |
| **05 — Mentions du co-organisateur** | Ajouter aux mentions les comptes connectés du lieu co-organisateur. | 02 et [CO_ORGANISATION](../CO_ORGANISATION/INDEX.md) |

---

## 9. Tests

- **Unitaires** (pytest, `django_db`) : calcul des dates (heure locale, dates passées), remplacement
  des variables et des mentions, limites de caractères, transitions de statut, suivi des
  changements d'événement, migration du booléen, choix proposés selon le module, duplication
  d'un événement (statut remis à « Pas besoin »), reprogrammation sans doublon d'une annonce
  déjà publiée, fabrication d'un JPEG 4:5 et 9:16 depuis un PNG.
- **Appels HTTP simulés** pour Mastodon et Instagram : succès, échec, jeton refusé, conteneur
  jamais `FINISHED`.
- **Jeton jamais en clair** : un test vérifie qu'après un échec de vérification, aucun jeton
  n'est enregistré.
- **Retour OAuth** : `state` falsifié ou expiré refusé.
- **L'onglet** : un test pytest sur la fiche admin (pré-remplissage) et un test unitaire de la limite. Vérification visuelle à la main ; pas de test E2E.
- **Réel** : Mastodon sur un compte de test ; Instagram en préprod, avec un compte testeur.
- Chaque test doit être vu **échouer** sur une mutation volontaire avant d'être livré.

---

## 10. À vérifier en réel

- [ ] Un `@nom` dans la légende Instagram envoyée par l'API crée-t-il une vraie mention
      (lien et notification) ?
- [ ] Le ratio du carrousel Instagram : Instagram recadre-t-il les images suivantes sur le
      ratio de la première ?
- [ ] La console Meta accepte-t-elle une adresse de retour sur le domaine choisi pour le schéma
      public ?

---

## 11. Laissé au builder

- Les noms exacts des champs et des migrations, et l'ordre des opérations de migration.
- La disposition de l'onglet dans Unfold : un fieldset `tab` pour le statut, un inline `tab`
  pour `PreparationCommunication`. Le skill `unfold` fait foi.
- Le chemin exact de l'adresse de retour OAuth dans `urls_public.py`.
- Le verrou contre la double publication (§7.7).
- Le nombre et l'espacement des essais d'attente du conteneur Instagram.
