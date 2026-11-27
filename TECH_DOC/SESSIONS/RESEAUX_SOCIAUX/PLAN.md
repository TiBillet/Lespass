# Réseaux sociaux (Instagram + Mastodon) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** Lespass programme et publie seul les annonces d'un événement sur Instagram et Mastodon,
une fois les textes validés par l'admin, et le récap quotidien dit ce qui est programmé et publié.

**Architecture :** une app Django `reseaux_sociaux` dans `TENANT_APPS` (4 modèles), deux petits
clients HTTP (`mastodon.py`, `instagram.py`) écrits avec `requests`, une tâche Celery toutes les
10 minutes qui publie les `Publication` dues. L'admin Unfold porte la configuration (singleton) et
un onglet inline sur la fiche d'événement. Aucune nouvelle dépendance.

**Tech Stack :** Django 4 + django-tenants, django-solo, Unfold, Celery, `requests`, Pillow.

**Spec :** [SPEC.md](SPEC.md) — à lire avant toute tâche. Les §-références ci-dessous y renvoient.

**Hors plan :** le chantier 05 (mentions du co-organisateur) attend [CO_ORGANISATION](../CO_ORGANISATION/INDEX.md).

## Global Constraints

- **Git :** aucun `add`, `commit`, `push`, `merge`, `rebase`, `checkout --`, `restore`, `stash`, `reset --hard`, `clean -f`, `branch -D`, `worktree remove`. Jamais de `Co-Authored-By`. Chaque tâche se termine par un **message de commit proposé** ; le mainteneur commite.
- **Skill `djc` chargé avant d'écrire du code**, et skill `unfold` pour tout ce qui touche `Administration/`.
- **FALC :** noms verbeux, commentaires FR (FALC) + une ligne EN, en-tête `LOCALISATION :`. Le commentaire décrit le code tel qu'il est, jamais l'histoire de la session.
- **Simple :** pas de helper pour une opération faite une fois, pas d'option « au cas où », pas de `ModelViewSet`, pas de Django Forms hors de l'admin.
- **i18n :** chaînes visibles en `_()` / `{% translate %}`, **msgid en français**. Ne jamais lancer `makemessages` / `compilemessages` : le signaler dans le rapport.
- **Commandes :** toujours dans le conteneur. Tests : `docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest <fichier> -q"`. Jamais la suite complète sans accord.
- **Migrations :** `docker exec lespass_django poetry run python manage.py makemigrations <app>` puis `docker exec lespass_django poetry run python manage.py migrate_schemas`. Ne jamais réécrire une migration déjà commitée.
- **ruff :** `ruff check --fix` + `ruff format` sur les fichiers **neufs** seulement. Sur un fichier existant : jamais `format` ; `--fix` seulement après inspection des imports à effet de bord.
- **Tests :** classes `FastTenantTestCase` (comme `tests/pytest/test_recap_quotidien.py`). Si un test lève `relation ... does not exist` après une migration, suivre le skill `tibillet-test` (schémas `test_*` périmés). HTTP simulé avec `unittest.mock.patch("reseaux_sociaux.<module>.requests.<verbe>")` : le paquet `responses` n'est pas installé. Chaque test doit être vu **échouer** sur une mutation volontaire.
- **Patron `FastTenantTestCase`** : chaque classe définit `get_test_schema_name` (un nom unique par fichier, ex. `test_reseaux_sociaux_programmation`), `get_test_tenant_domain`, `setup_tenant`, et `connection.set_tenant(self.tenant)` dans `setUp`. Copier `tests/pytest/test_recap_quotidien.py:118-150`. Une fiche admin se teste avec `TenantClient` et un superutilisateur connecté par `force_login`.
- **Imports de l'admin :** `Administration/admin/reseaux_sociaux.py` importe `staff_admin_site` depuis `Administration.admin.site` et `ModelAdmin`, `SingletonAdmin` depuis `Administration.admin.base`. **Jamais** depuis `admin_tenant` (import circulaire).
- **Clients HTTP :** toute réponse non 2xx, et toute réponse sans le champ attendu, lève l'erreur typée du client (`ErreurMastodon`, `ErreurInstagram`), avec le code et le corps de la réponse dans le message. Jamais de `KeyError` qui sort.
- **Changer le statut d'un événement depuis `reseaux_sociaux`** : `Event.objects.filter(pk=event.pk).update(statut_communication=...)`, pas `event.save()` (qui relance `Event.save()` et le signal SEO). Mettre aussi à jour l'objet en mémoire.
- **Jetons :** jamais en clair en base, jamais dans un log, jamais affichés dans l'admin.
- **Celery :** après une tâche qui ajoute une tâche Celery, prévenir le mainteneur qu'il faut redémarrer `lespass_celery`.
- **CHANGELOG :** un seul fichier `CHANGELOG/2026-11-27-reseaux-sociaux-instagram-mastodon.md`, créé à la tâche 2 et complété à chaque tâche (format du skill `djc`). La tâche 1 a son propre fichier.

## Review Focus

1. **Deux passages de la tâche Celery qui se chevauchent** : une annonce ne part jamais deux fois. → Tâche 7, test `test_une_annonce_deja_traitee_n_est_pas_republiee`.
2. **Un post J-7 en retard sur un événement déjà commencé** : rien ne part. → Tâche 5, test `test_rien_n_est_cree_pour_un_evenement_deja_commence`.
3. **Le passage à l'heure d'hiver ou d'été** : 12 h reste 12 h heure du lieu. → Tâche 5, test `test_les_heures_sont_en_heure_locale_du_lieu_meme_au_changement_d_heure`.
4. **Les mentions qui font dépasser la limite** : le texte est refusé à l'enregistrement, pas à l'envoi. → Tâche 6, test `test_les_mentions_comptent_dans_la_limite_de_caracteres`.
5. **Une affiche PNG transparente** : elle devient un JPEG valide, sans planter. → Tâche 9, test `test_un_png_transparent_devient_un_jpeg`.

Limite assumée, non traitée : un événement dont la date change **hors de l'admin** (API v2) n'est pas reprogrammé.

---

## Carte des fichiers

| Fichier | Rôle |
|---|---|
| `reseaux_sociaux/__init__.py`, `apps.py` | L'app. |
| `reseaux_sociaux/models.py` | `ConfigurationReseauxSociaux`, `FicheReseauxSociaux`, `PreparationCommunication`, `Publication`. |
| `reseaux_sociaux/textes.py` | Modèles de texte, variables, mentions, limites. |
| `reseaux_sociaux/programmation.py` | Calcul des dates et machine d'états du statut. |
| `reseaux_sociaux/mastodon.py` | Client HTTP Mastodon. |
| `reseaux_sociaux/instagram.py` | Client HTTP Instagram (OAuth + publication). |
| `reseaux_sociaux/images.py` | Fabrication des JPEG recadrés. |
| `reseaux_sociaux/publication.py` | Publier une `Publication` et mettre à jour le statut. |
| `reseaux_sociaux/tasks.py` | Boucles sur les lieux (publier, renouveler les jetons). |
| `reseaux_sociaux/views.py` | Le retour OAuth Instagram (schéma public). |
| `Administration/admin/reseaux_sociaux.py` | Admins du singleton, des fiches, et l'inline de l'événement. |
| `BaseBillet/models.py` | `Event.statut_communication`, `Configuration.module_reseaux_sociaux`. |
| `Administration/admin_tenant.py` | `EventAdmin` : inline, choix du statut, synchronisation, duplication. |
| `Administration/admin/dashboard.py` | Menu « Réseau » (Newsletter + Réseaux sociaux), `MODULE_FIELDS`. |
| `Administration/recap_quotidien.py` | Deux rubriques. |
| `TiBillet/settings.py`, `TiBillet/celery.py`, `TiBillet/urls_public.py` | App, variables d'environnement, tâches périodiques, URL de retour. |

---

### Task 1 : Newsletter dans la section « Réseau » (chantier 01)

**Files :**
- Modify : `Administration/admin/dashboard.py:123` (sous-titre de `lespass`), `:131-133` (sous-titre de `lerezo`), `:2462-2466` (commentaire + `"domaine"`), `:3117-3122` (commentaire)
- Test : `tests/pytest/test_module_newsletter_activation.py` : le test existant `test_newsletter_est_rangee_dans_le_domaine_lespass` (l. 245-270, classe `TestSidebar`) affirme l'inverse. On le **réécrit**, et on corrige les docstrings des lignes 21 et 215.
- Create : `CHANGELOG/2026-11-27-newsletter-menu-reseau.md`

- [ ] **Step 1 : test qui échoue** : renommer `test_newsletter_est_rangee_dans_le_domaine_lespass` en `test_newsletter_est_rangee_dans_le_domaine_reseau`, et lui faire affirmer `MODULE_FIELDS["module_newsletter"]["domaine"] == "lerezo"` ainsi que le titre `DOMAINES["lerezo"]["titre"]` là où il affirmait celui de `lespass`. Garder le reste de sa structure.

- [ ] **Step 2 :** lancer le fichier de test. Attendu : FAIL (`'lespass' == 'lerezo'`).
- [ ] **Step 3 :** `"domaine": "lerezo"`. Retirer « newsletter » du sous-titre de `lespass`. Ajouter la communication au sous-titre de `lerezo` (texte FR : « Relier votre lieu au réseau, faire circuler les monnaies et annoncer vos événements. »). Réécrire le commentaire des lignes 3117-3122 pour qu'il dise où vivent la newsletter et les réseaux sociaux (domaine Réseau).
- [ ] **Step 4 :** relancer le fichier. Attendu : PASS, tous les tests du fichier.
- [ ] **Step 5 :** fichier CHANGELOG, puis proposer : `feat(admin): range la newsletter dans la section Réseau du menu`.

---

### Task 2 : L'app, ses modèles et le drapeau de module

**Files :**
- Create : `reseaux_sociaux/__init__.py`, `reseaux_sociaux/apps.py`, `reseaux_sociaux/models.py`, `reseaux_sociaux/migrations/0001_initial.py` (généré)
- Modify : `TiBillet/settings.py:278-307` (`'reseaux_sociaux'` à la fin de `TENANT_APPS`, avec un commentaire FALC), `BaseBillet/models.py:732` (après `module_newsletter`), `Administration/admin/dashboard.py:2461` (entrée `MODULE_FIELDS`)
- Test : `tests/pytest/test_reseaux_sociaux_modeles.py`
- Create : `CHANGELOG/2026-11-27-reseaux-sociaux-instagram-mastodon.md`

**Interfaces — Produces :**
- `Configuration.module_reseaux_sociaux` : `BooleanField(default=False, verbose_name=_("Module réseaux sociaux"))`.
- `MODULE_FIELDS["module_reseaux_sociaux"]` : `name=_("Réseaux sociaux")`, `description=_("Annoncer vos événements sur Instagram et Mastodon, au bon moment")`, `testid="dashboard-card-reseaux-sociaux"`, `beta=True`, `domaine="lerezo"`, `icone="campaign"`, `slug="reseaux_sociaux"`.
- `reseaux_sociaux.models` — noms exacts, utilisés par toutes les tâches suivantes :

```python
class ConfigurationReseauxSociaux(SingletonModel):
    # Mastodon
    mastodon_url_instance = URLField(blank=True, null=True)
    mastodon_jeton = CharField(max_length=500, blank=True, null=True)      # chiffré Fernet
    mastodon_nom_du_compte = CharField(max_length=200, blank=True, null=True)  # "@nom@instance"
    mastodon_limite_de_caracteres = PositiveIntegerField(default=500)
    # Instagram
    instagram_identifiant_utilisateur = CharField(max_length=100, blank=True, null=True)
    instagram_nom_du_compte = CharField(max_length=200, blank=True, null=True)  # sans "@"
    instagram_jeton = CharField(max_length=1000, blank=True, null=True)    # chiffré Fernet
    instagram_jeton_obtenu_le = DateTimeField(blank=True, null=True)
    instagram_renouvellement_echoue_le = DateTimeField(blank=True, null=True)
    # Rythme (heure locale du lieu)
    jours_avant_le_post = PositiveSmallIntegerField(default=7)
    heure_du_post = TimeField(default=time(12, 0))
    heure_story_veille = TimeField(default=time(16, 0))
    heure_story_jour_j = TimeField(default=time(10, 0))
    heure_relance_mastodon = TimeField(default=time(10, 0))
    # Modèles de texte (défauts FR fixés à la tâche 6)
    modele_texte_instagram = TextField(default=...)
    modele_texte_mastodon = TextField(default=...)
    modele_texte_relance_mastodon = TextField(default=...)

    def get_jeton_mastodon(self) -> str | None
    def set_jeton_mastodon(self, jeton_en_clair: str) -> None   # chiffre, ne sauvegarde PAS
    def get_jeton_instagram(self) -> str | None
    def set_jeton_instagram(self, jeton_en_clair: str) -> None  # chiffre, ne sauvegarde PAS
    def mastodon_est_connecte(self) -> bool    # url + jeton présents
    def instagram_est_connecte(self) -> bool   # identifiant + jeton présents

class FicheReseauxSociaux(models.Model):
    nom = CharField(max_length=200)
    instagram = CharField(max_length=200, blank=True)   # sans "@"
    mastodon = CharField(max_length=300, blank=True)    # "nom@instance", sans "@" de tête
    # __str__ -> nom ; ordering ["nom"]

class PreparationCommunication(models.Model):
    event = OneToOneField("BaseBillet.Event", on_delete=CASCADE, related_name="preparation_communication")
    texte_instagram = TextField(blank=True)
    texte_mastodon = TextField(blank=True)
    texte_relance_mastodon = TextField(blank=True)
    comptes_a_mentionner = ManyToManyField(FicheReseauxSociaux, blank=True)
    image_post = ImageField(upload_to="reseaux_sociaux/remplacements/", blank=True, null=True)
    image_story = ImageField(upload_to="reseaux_sociaux/remplacements/", blank=True, null=True)

class Publication(models.Model):
    RESEAU_INSTAGRAM, RESEAU_MASTODON = "instagram", "mastodon"
    FORMAT_POST, FORMAT_STORY = "post", "story"
    MOMENT_AVANT, MOMENT_VEILLE, MOMENT_JOUR_J = "avant", "veille", "jour_j"
    ETAT_PREVUE, ETAT_PUBLIEE, ETAT_ECHEC = "prevue", "publiee", "echec"
    uuid = UUIDField(primary_key=True, default=uuid4, editable=False)
    event = ForeignKey("BaseBillet.Event", on_delete=CASCADE, related_name="publications_reseaux_sociaux")
    reseau = CharField(max_length=20, choices=...)
    format = CharField(max_length=10, choices=...)
    moment = CharField(max_length=10, choices=...)
    date_prevue = DateTimeField()
    etat = CharField(max_length=10, choices=..., default=ETAT_PREVUE)
    url = URLField(max_length=500, blank=True)
    identifiant_sur_le_reseau = CharField(max_length=200, blank=True)
    message_d_erreur = TextField(blank=True)
    traitee_le = DateTimeField(blank=True, null=True)
    creee_le = DateTimeField(auto_now_add=True)
    # Meta.ordering = ["date_prevue"]
```

Les `verbose_name` sont en français, avec `_()`. Fernet : `from root_billet.utils import fernet_encrypt, fernet_decrypt`, comme `GhostConfig`.

- [ ] **Step 1 : tests qui échouent** (`TestModelesReseauxSociaux(FastTenantTestCase)`) :
  - `test_le_jeton_mastodon_est_chiffre_en_base` : après `set_jeton_mastodon("secret-123")` + `save()`, `mastodon_jeton != "secret-123"` et `get_jeton_mastodon() == "secret-123"`.
  - `test_un_compte_sans_jeton_n_est_pas_connecte` : singleton neuf → `mastodon_est_connecte() is False` et `instagram_est_connecte() is False`.
  - `test_le_rythme_par_defaut_est_celui_de_la_spec` : `jours_avant_le_post == 7`, `heure_du_post == time(12, 0)`, `heure_story_veille == time(16, 0)`, `heure_story_jour_j == time(10, 0)`, `heure_relance_mastodon == time(10, 0)`.
  - `test_le_module_reseaux_sociaux_est_eteint_par_defaut` : `Configuration._meta.get_field("module_reseaux_sociaux").default is False`.
- [ ] **Step 2 :** lancer. Attendu : FAIL (`ModuleNotFoundError: reseaux_sociaux`).
- [ ] **Step 3 :** écrire l'app, les modèles, le drapeau, l'entrée `MODULE_FIELDS`. Modèles de texte : chaîne vide provisoire, remplacée à la tâche 6.
- [ ] **Step 4 :** `makemigrations reseaux_sociaux BaseBillet`, puis `migrate_schemas`. Lire les deux migrations générées : uniquement les ajouts prévus.
- [ ] **Step 5 :** relancer. Attendu : PASS. Puis `docker exec lespass_django poetry run python manage.py check` : aucune erreur.
- [ ] **Step 6 :** CHANGELOG (Migration : Oui, les deux noms), puis proposer : `feat(reseaux_sociaux): crée l'app, ses modèles et le module`.

---

### Task 3 : Le statut de communication remplace le booléen

**Files :**
- Modify : `BaseBillet/models.py:2372` (`communication_envoyee` → `statut_communication`), `Administration/admin_tenant.py` (fieldset « Interne » l. 4480, `list_display` l. 4493, `list_editable` l. 4498, `_duplicate_event` l. 4929-4950, nouvelle méthode `formfield_for_choice_field`), et **tout autre endroit** que donne `rg -n communication_envoyee` (gabarits, exports, ressources import/export)
- Create : migration `BaseBillet/migrations/0XXX_event_statut_communication.py`
- Test : `tests/pytest/test_event_champs_internes.py` (l. 8, 22, 112 : adapter `CHAMPS_INTERNES` et les assertions), `tests/pytest/test_reseaux_sociaux_statut.py`

**Interfaces — Produces :**

```python
class Event:
    COMMUNICATION_PAS_BESOIN, COMMUNICATION_EN_ATTENTE = "N", "A"
    COMMUNICATION_PROGRAMMEE, COMMUNICATION_FAITE = "P", "F"
    statut_communication = CharField(max_length=1, choices=[
        ("N", _("Pas besoin de com'")), ("A", _("Com' en attente")),
        ("P", _("Programmée")), ("F", _("Faite"))], default="N",
        verbose_name=_("Statut de la com'"))
```

La migration fait, dans cet ordre : `AddField statut_communication` → `RunPython` (`communication_envoyee=True` → `"F"`, sinon `"N"`, avec la garde « schéma public → return » du skill `djc`) → `RemoveField communication_envoyee`. `reverse_code` : `RunPython.noop`.

`EventAdmin.formfield_for_choice_field(db_field, request, **kwargs)` : pour `statut_communication`, si `Configuration.get_solo().module_reseaux_sociaux` est faux, `kwargs["choices"]` = seulement `N` et `F`. Elle sert à la fiche **et** à `list_editable`.

`_duplicate_event` : le doublon reçoit `statut_communication = Event.COMMUNICATION_PAS_BESOIN`.

- [ ] **Step 1 : tests qui échouent** (`test_reseaux_sociaux_statut.py`, `FastTenantTestCase`) :
  - `test_un_nouvel_evenement_n_a_pas_besoin_de_com` : `Event.objects.create(...)` → `statut_communication == "N"`.
  - `test_sans_le_module_seuls_pas_besoin_et_faite_sont_proposes` : module éteint, `EventAdmin(Event, staff_admin_site).formfield_for_choice_field(Event._meta.get_field("statut_communication"), request)` → valeurs des choix (sans l'option vide) == `["N", "F"]`.
  - `test_avec_le_module_les_quatre_statuts_sont_proposes` : module allumé → `["N", "A", "P", "F"]`.
  - `test_un_evenement_duplique_repart_sans_besoin_de_com` : événement source en `"P"`, après `_duplicate_event` le doublon est en `"N"`.
  - La conversion de la migration se teste à la main (Step 4), pas en pytest.
- [ ] **Step 2 :** lancer les deux fichiers. Attendu : FAIL.
- [ ] **Step 3 :** remplacer le champ partout (`rg -n communication_envoyee` doit finir vide hors migrations), écrire la migration, `formfield_for_choice_field`, la ligne de `_duplicate_event`. Le commentaire « champs internes jamais dans l'API ni le CSV » (l. 2357-2361) cite le nouveau nom.
- [ ] **Step 4 :** avant `migrate_schemas`, noter en base de dev le nombre d'événements à `communication_envoyee=True` du tenant `lespass` (`manage.py shell`, `tenant_context`). Après : le même nombre en `"F"`, aucun en `"A"` ni `"P"`.
- [ ] **Step 5 :** relancer les deux fichiers. Attendu : PASS.
- [ ] **Step 6 :** CHANGELOG, puis proposer : `feat(admin): remplace « Comm' envoyée » par un statut de communication`.

---

### Task 4 : Admin du singleton, connexion Mastodon, fiches et menu

**Files :**
- Create : `reseaux_sociaux/mastodon.py`, `Administration/admin/reseaux_sociaux.py`
- Modify : `Administration/admin_tenant.py:34` (ajouter `reseaux_sociaux` à l'import à effet de bord `from Administration.admin import (...)`, **sans** retirer d'import existant), `Administration/admin/dashboard.py` (une section après celle de la newsletter, l. 1096-1128, même forme)
- Test : `tests/pytest/test_reseaux_sociaux_mastodon.py`

**Interfaces — Produces :**

```python
# reseaux_sociaux/mastodon.py — timeout de 15 s sur chaque appel, comme newsletter/client_ghost.py
class ErreurMastodon(Exception): ...
def verifier_le_jeton(url_instance: str, jeton: str) -> dict
    # GET {url}/api/v1/accounts/verify_credentials puis GET {url}/api/v2/instance
    # -> {"nom_du_compte": "@acct@hote", "limite_de_caracteres": int}
    # limite = configuration.statuses.max_characters, sinon 500. Lève ErreurMastodon si refus.
def publier_sur_mastodon(url_instance: str, jeton: str, texte: str, chemins_des_images: list[str]) -> dict
    # POST /api/v2/media (fichier) pour chaque image (4 au plus), puis POST /api/v1/statuses
    # (status, media_ids[], visibility="public") -> {"identifiant": str, "url": str}
```

- `ConfigurationReseauxSociauxAdmin(SingletonAdmin)` : `change_form_template = None`, comme les autres singletons (`admin_tenant.py:6726`). Un formulaire admin avec un champ **hors modèle** `nouveau_jeton_mastodon` (`PasswordInput`, facultatif). Le champ chiffré `mastodon_jeton` n'est jamais dans le formulaire. Les champs `mastodon_nom_du_compte`, `instagram_nom_du_compte`, `instagram_jeton_obtenu_le` sont en lecture seule. Fieldsets en onglets : « Mastodon », « Instagram » (texte d'état + bouton, câblé à la tâche 8), « Rythme », « Modèles de texte ».
- `save_model` : si `nouveau_jeton_mastodon` est rempli, appeler `verifier_le_jeton`. Si ça réussit : `set_jeton_mastodon`, `mastodon_nom_du_compte`, `mastodon_limite_de_caracteres`, message de succès. Si ça échoue : message d'erreur, **le jeton n'est pas écrit**, le reste du formulaire est enregistré.
- `FicheReseauxSociauxAdmin(ModelAdmin)` : `list_display = ["nom", "instagram", "mastodon"]`, `search_fields = ["nom", "instagram", "mastodon"]` (indispensable pour l'autocomplétion de la tâche 6).
- Les quatre `has_*_permission` sur chaque admin (`TenantAdminPermissionWithRequest`). Le singleton : `has_add_permission` → `False`.
- Menu : section « Réseaux sociaux », visible si `module_reseaux_sociaux`, `_domaine` lu dans `MODULE_FIELDS`. Deux entrées : « Configuration » (`staff_admin:reseaux_sociaux_configurationreseauxsociaux_changelist`, icône `settings`) et « Comptes à mentionner » (`staff_admin:reseaux_sociaux_fichereseauxsociaux_changelist`, icône `alternate_email`).

- [ ] **Step 1 : tests qui échouent** :
  - `test_verifier_le_jeton_renvoie_le_compte_et_la_limite` : `requests.get` simulé (`{"acct": "lieu"}` puis `{"configuration": {"statuses": {"max_characters": 1000}}}`) → `{"nom_du_compte": "@lieu@pouet.example", "limite_de_caracteres": 1000}`.
  - `test_verifier_le_jeton_leve_une_erreur_si_l_instance_refuse` : réponse 401 → `ErreurMastodon`.
  - `test_publier_sur_mastodon_envoie_les_images_puis_le_statut` : 2 chemins d'image → 2 appels `/api/v2/media`, puis 1 appel `/api/v1/statuses` avec les deux `media_ids[]`. Renvoie `{"identifiant": "109", "url": "https://pouet.example/@lieu/109"}`.
  - `test_un_jeton_refuse_n_est_jamais_enregistre` : `save_model` de l'admin avec `verifier_le_jeton` qui lève une erreur → après rechargement, `mastodon_jeton` est vide.
  - `test_le_menu_reseaux_sociaux_n_apparait_que_si_le_module_est_actif` : même forme que le test équivalent de `test_module_newsletter_activation.py` (l. 208).
- [ ] **Step 2 :** lancer. Attendu : FAIL.
- [ ] **Step 3 :** écrire `mastodon.py`, les admins, l'import, le menu.
- [ ] **Step 4 :** relancer. Attendu : PASS. `manage.py check` sans erreur. `test_module_newsletter_activation.py` toujours vert.
- [ ] **Step 5 :** vérification à la main sur `https://lespass.tibillet.localhost/admin/` : module allumé, la section apparaît dans « Réseau », le singleton s'ouvre.
- [ ] **Step 6 :** CHANGELOG, puis proposer : `feat(reseaux_sociaux): admin de configuration et connexion Mastodon`.

---

### Task 5 : Calcul des dates et machine d'états

**Files :**
- Create : `reseaux_sociaux/programmation.py`
- Test : `tests/pytest/test_reseaux_sociaux_programmation.py`

**Interfaces — Consumes :** modèles de la tâche 2, `Event.COMMUNICATION_*` de la tâche 3, `Configuration.get_tzinfo()` (`BaseBillet/models.py:611`).

**Interfaces — Produces :**

```python
def calculer_les_annonces(event, configuration_reseaux, maintenant) -> list[dict]
    # Une entrée par annonce : {"reseau", "format", "moment", "date_prevue"} (datetime aware).
    # Seulement pour les réseaux connectés. Règles des dates passées : SPEC §7.6.
def verifier_avant_de_programmer(event, configuration_reseaux) -> list[str]
    # Messages d'erreur traduits (liste vide = OK) : préparation absente (« Ouvrez la fiche
    # de l'événement et validez les textes. »), non publié ou archivé, aucun réseau connecté,
    # texte vide pour un réseau connecté, aucune image (get_img()) avec Instagram.
    # La préparation n'est JAMAIS créée ici : un post partirait sans relecture.
def synchroniser_les_publications(event, la_date_a_change: bool) -> list[str]
    # Appelée après chaque enregistrement admin. Renvoie les erreurs à afficher.
```

**La table des annonces** (date = jour J moins N jours, à l'heure indiquée, **heure locale du lieu**, convertie en aware) :

| reseau | format | moment | jour | heure |
|---|---|---|---|---|
| instagram | post | avant | J − `jours_avant_le_post` | `heure_du_post` |
| instagram | story | veille | J − 1 | `heure_story_veille` |
| instagram | story | jour_j | J | `heure_story_jour_j` |
| mastodon | post | avant | J − `jours_avant_le_post` | `heure_du_post` |
| mastodon | post | jour_j | J | `heure_relance_mastodon` |

« J » est la date locale de `event.datetime`. Si l'événement a déjà commencé (`event.datetime <= maintenant`), la liste est vide. Une annonce `avant` dont la date est passée prend `date_prevue = maintenant`. Une annonce `veille` ou `jour_j` dont la date est passée est retirée.

**`synchroniser_les_publications`** (SPEC §7.6 et §7.8) :
- statut `N` ou `F` → supprimer les `Publication` `prevue` de l'événement.
- statut `A` → `verifier_avant_de_programmer` ; s'il y a des erreurs, les renvoyer sans rien toucher. Sinon : supprimer les `prevue`, créer une `Publication` pour chaque annonce de `calculer_les_annonces` dont le couple (`reseau`, `moment`) n'a pas déjà une `Publication` `publiee`, puis passer le statut à `P` (par `update()`, voir Global Constraints).
- statut `P` et événement dépublié ou archivé → supprimer les `prevue`, statut `A`.
- statut `P` et `la_date_a_change` → même chemin que `A`.

- [ ] **Step 1 : tests qui échouent** (`maintenant` fixé, lieu en `Europe/Paris`, les deux réseaux connectés sauf mention) :
  - `test_les_cinq_annonces_sont_calculees_pour_un_evenement_lointain` : événement le 2026-12-20 à 20 h → 5 annonces ; post Instagram le 2026-12-13 à 12:00 heure de Paris ; relance Mastodon le 2026-12-20 à 10:00.
  - `test_seuls_les_reseaux_connectes_sont_programmes` : Mastodon seul → 2 annonces, toutes `mastodon`.
  - `test_un_post_en_retard_part_tout_de_suite` : événement dans 3 jours → l'annonce `avant` a `date_prevue == maintenant`.
  - `test_une_story_en_retard_n_est_pas_creee` : `maintenant` = jour J à 18 h, événement à 20 h → aucune annonce `veille`, aucune story `jour_j`.
  - `test_rien_n_est_cree_pour_un_evenement_deja_commence` : `event.datetime < maintenant` → `[]`.
  - `test_les_heures_sont_en_heure_locale_du_lieu_meme_au_changement_d_heure` : événement le 2026-11-01 (heure d'hiver depuis le 25 octobre), post J-7 le 2026-10-25 à 12:00 Paris → `date_prevue` en UTC == 2026-10-25 11:00.
  - `test_programmer_passe_le_statut_a_programmee` : statut `A`, textes remplis → 5 `Publication` `prevue`, statut `P`.
  - `test_programmer_sans_texte_renvoie_une_erreur_et_ne_cree_rien` : texte Mastodon vide → 1 erreur, 0 `Publication`, statut toujours `A`.
  - `test_programmer_sans_preparation_renvoie_une_erreur` : événement passé en `A` depuis la liste, jamais ouvert → 1 erreur, 0 `Publication`, aucune `PreparationCommunication` créée.
  - `test_reprogrammer_ne_recree_pas_une_annonce_deja_publiee` : une `Publication` (`mastodon`, `avant`) `publiee` existe → après reprogrammation, aucune nouvelle `mastodon`/`avant`.
  - `test_revenir_a_pas_besoin_supprime_les_annonces_prevues` : statut `P` → `N` → 0 `prevue`, les `publiee` restent.
  - `test_depublier_un_evenement_programme_le_remet_en_attente` : `published=False` → 0 `prevue`, statut `A`.
- [ ] **Step 2 :** lancer. Attendu : FAIL (`ModuleNotFoundError`).
- [ ] **Step 3 :** écrire `programmation.py`. Boucle `for` explicite sur la table des annonces : pas de compréhension imbriquée.
- [ ] **Step 4 :** relancer. Attendu : PASS.
- [ ] **Step 5 :** CHANGELOG, puis proposer : `feat(reseaux_sociaux): calcule et programme les annonces d'un événement`.

---

### Task 6 : Textes, mentions et onglet « Réseaux sociaux » de l'événement

**Files :**
- Create : `reseaux_sociaux/textes.py`
- Modify : `reseaux_sociaux/models.py` (défauts des trois modèles de texte → nouvelle migration), `Administration/admin/reseaux_sociaux.py` (`PreparationCommunicationInline`), `Administration/admin_tenant.py` (`EventAdmin` : `get_inlines`, `changeform_view`, `save_related`)
- Test : `tests/pytest/test_reseaux_sociaux_textes.py`

**Interfaces — Produces :**

```python
# reseaux_sociaux/textes.py
LIMITE_INSTAGRAM = 2200
def remplacer_les_variables(modele: str, event) -> str
    # {nom} {date} {heure} {lieu} {lien} {description_courte} {description_longue}
    # par str.replace ; {mentions} reste tel quel. Date et heure en heure locale du lieu
    # (django.utils.formats.date_format). {lieu} = nom de event.postal_address ou ""
    # (vérifier le nom exact du champ sur PostalAddress).
    # {lien} = event.full_url. {description_longue} sans balises HTML (strip_tags).
def textes_depuis_les_modeles(event, configuration_reseaux) -> dict
    # {"texte_instagram": ..., "texte_mastodon": ..., "texte_relance_mastodon": ...}
def remplacer_les_mentions(texte: str, reseau: str, fiches) -> str
    # fiches : itérable de FicheReseauxSociaux. instagram -> "@nom" ;
    # mastodon -> "@nom@instance" ; séparées par une espace ; fiches sans compte pour ce
    # réseau ignorées ; aucune mention -> "".
def erreurs_de_longueur(textes: dict, fiches, limite_mastodon: int) -> list[str]
    # textes : les clés de textes_depuis_les_modeles. Compte APRÈS remplacement des
    # mentions. Instagram : 2200. Mastodon : limite_mastodon.
    # Elle prend des VALEURS, pas l'instance : dans clean() d'un ModelForm, l'instance n'a
    # pas encore les nouveaux textes, et le M2M n'est écrit qu'à save_m2m.
```

**Défauts des modèles de texte** (msgid FR, valeur par défaut du champ) :
- Instagram : `"{nom}\n{date} à {heure} — {lieu}\n\n{description_courte}\n\n{mentions}\n\nInfos et billets : lien dans la bio."`
- Mastodon : `"{nom}\n{date} à {heure} — {lieu}\n\n{description_courte}\n\n{mentions}\n{lien}"`
- Relance Mastodon : `"C'est aujourd'hui ! {nom}, {heure} — {lieu}\n{mentions}\n{lien}"`

**L'onglet :**
- `PreparationCommunicationInline(StackedInline)` (Unfold) : `tab = True`, `max_num = 1`, `can_delete = False`, `autocomplete_fields = ["comptes_a_mentionner"]`. Champ hors modèle `regenerer_depuis_le_modele` (`BooleanField`, facultatif, libellé « Régénérer les textes depuis le modèle »). `clean()` du formulaire : `erreurs_de_longueur(cleaned_data, cleaned_data["comptes_a_mentionner"], configuration.mastodon_limite_de_caracteres)` → `ValidationError`. Si la case est cochée, `save()` réécrit les trois textes avec `textes_depuis_les_modeles`.
- Lecture seule dans l'inline : aperçu des deux images (`format_html`, `<img>` avec `style="aspect-ratio: 4 / 5; object-fit: cover; width: 160px"` et `9 / 16`, source = image de remplacement, sinon `event.get_img()`), et la liste des `Publication` de l'événement (date locale, réseau, format, état, lien). Styles inline, pas de classes Tailwind.
- `EventAdmin.get_inlines(request, obj)` : l'inline seulement si `obj` existe et que le module est allumé.
- `EventAdmin.changeform_view` : si `object_id` et module allumé, `PreparationCommunication.objects.get_or_create(event=..., defaults=textes_depuis_les_modeles(...))` avant `super()`.
- `EventAdmin.save_related` : **après** le code existant, si le module est allumé, appeler `synchroniser_les_publications(form.instance, "datetime" in form.changed_data)` et afficher chaque erreur avec `messages.error`. `save_related` est aussi appelé par `list_editable` : un seul point d'entrée.

- [ ] **Step 1 : tests qui échouent** :
  - `test_les_variables_sont_remplacees_et_les_mentions_gardees` : `"{nom} {lien} {mentions}"` → contient le nom et `full_url`, et toujours `{mentions}`.
  - `test_la_date_est_en_heure_locale_du_lieu` : événement à 19:00 UTC en hiver → `{heure}` donne 20:00.
  - `test_les_mentions_dependent_du_reseau` : fiche (`instagram="artiste_x"`, `mastodon="artiste@pouet.example"`) → `"@artiste_x"` pour Instagram, `"@artiste@pouet.example"` pour Mastodon.
  - `test_une_fiche_sans_compte_mastodon_n_est_pas_mentionnee_sur_mastodon`.
  - `test_les_mentions_comptent_dans_la_limite_de_caracteres` : texte Mastodon de 490 caractères avec `{mentions}`, limite 500, une mention de 25 caractères → 1 erreur.
  - `test_le_formulaire_de_l_onglet_refuse_une_mention_qui_fait_depasser` : formulaire de l'inline instancié avec des données POST (texte Mastodon de 490 caractères + une fiche de 25 caractères cochée) → `is_valid() is False`.
  - `test_la_fiche_de_l_evenement_cree_la_preparation_avec_les_textes` : GET de la fiche admin (`TenantClient`, superutilisateur, module allumé) → une `PreparationCommunication` existe, `texte_mastodon` non vide.
  - `test_sans_le_module_l_onglet_n_apparait_pas` : `get_inlines` renvoie une liste sans `PreparationCommunicationInline`.
- [ ] **Step 2 :** lancer. Attendu : FAIL.
- [ ] **Step 3 :** écrire `textes.py`, les défauts (`makemigrations reseaux_sociaux` + `migrate_schemas`), l'inline et les trois méthodes d'`EventAdmin`.
- [ ] **Step 4 :** relancer ce fichier, puis `test_event_champs_internes.py` et `test_reseaux_sociaux_programmation.py`. Attendu : PASS.
- [ ] **Step 5 :** à la main : ouvrir un événement, voir l'onglet pré-rempli, ajouter une fiche, enregistrer en « Com' en attente » → statut « Programmée », liste des publications affichée.
- [ ] **Step 6 :** CHANGELOG, puis proposer : `feat(admin): onglet Réseaux sociaux sur la fiche événement`.

---

### Task 7 : Publier sur Mastodon, tâche Celery

**Files :**
- Create : `reseaux_sociaux/publication.py`, `reseaux_sociaux/tasks.py`
- Modify : `TiBillet/celery.py` (`setup_periodic_tasks` + wrapper local `cron_publier_les_annonces`, même forme que `cron_rappel_des_benevoles` l. 246)
- Test : `tests/pytest/test_reseaux_sociaux_publication.py`

**Interfaces — Consumes :** `publier_sur_mastodon` (tâche 4), `remplacer_les_mentions` (tâche 6).

**Interfaces — Produces :**

```python
# reseaux_sociaux/publication.py
def texte_final(publication) -> str
    # Le texte de PreparationCommunication selon (reseau, moment), mentions remplacées.
    # Une story -> "".
def publier_une_annonce(publication_uuid) -> None
    # Dans transaction.atomic() : Publication.objects.select_for_update(skip_locked=True)
    # .filter(uuid=..., etat=PREVUE).first() ; None -> return (déjà prise ou traitée).
    # Mastodon : images = fichier d'origine de event.get_img() (.path), puis carrousel par
    # `order`, 4 au plus. Pas de variation : l'image de repli (lieu, configuration) n'a
    # pas forcément les mêmes variations que celle de l'événement. Instagram : branché à la tâche 9 (lever NotImplementedError d'ici là).
    # AVANT de publier : si l'événement est dépublié ou archivé, supprimer ses Publication
    # prevue, statut -> A, et ne rien publier. C'est le seul garde-fou pour l'action de
    # ligne « archive » (admin_tenant.py:4855-4860, save sans save_related) et pour l'API v2.
    # Si get_img() renvoie None, Mastodon part avec le seul carrousel, ou en texte seul.
    # Succès -> etat publiee, url, identifiant_sur_le_reseau, traitee_le.
    # Erreur (ErreurMastodon, requests.RequestException ; ErreurInstagram est ajoutée à
    # la tâche 9) -> etat echec,
    # message_d_erreur (le message de l'exception), traitee_le, et statut de l'event -> A.
    # Ensuite : event en P sans aucune Publication prevue -> statut F.

# reseaux_sociaux/tasks.py
def publier_les_annonces_dues_du_lieu() -> None
    # Les Publication prevue avec date_prevue <= now, dans l'ordre ; une par une.
def publier_les_annonces_dues() -> None
    # Boucle de booking/tasks.py:497-522 (exclut public et WAITING_CONFIG, try/except +
    # logger.exception par lieu), seulement si Configuration.get_solo().module_reseaux_sociaux.
```

Dans `TiBillet/celery.py` : `crontab(minute="*/10")`, `name="cron_publier_les_annonces"`.

- [ ] **Step 1 : tests qui échouent** (`publier_sur_mastodon` simulé) :
  - `test_une_annonce_mastodon_publiee_garde_son_lien` : → `etat == "publiee"`, `url` == l'URL simulée, `traitee_le` rempli.
  - `test_le_texte_envoye_contient_les_mentions_remplacees` : l'argument `texte` reçu par le simulacre contient `@artiste@pouet.example` et pas `{mentions}`.
  - `test_un_echec_remet_l_evenement_en_attente` : le simulacre lève `ErreurMastodon("401")` → `etat == "echec"`, `message_d_erreur` contient `401`, statut de l'événement `A`.
  - `test_la_derniere_annonce_publiee_passe_l_evenement_a_faite` : une seule `prevue` → après publication, statut `F`.
  - `test_une_annonce_deja_traitee_n_est_pas_republiee` : `Publication` en `publiee` → `publier_une_annonce` n'appelle pas le simulacre.
  - `test_seules_les_annonces_dues_partent` : une `prevue` dans le passé, une dans le futur → un seul appel.
  - `test_un_evenement_archive_n_est_pas_annonce` : événement `P` archivé par `update(archived=True)` → aucun appel, 0 `prevue`, statut `A`.
- [ ] **Step 2 :** lancer. Attendu : FAIL.
- [ ] **Step 3 :** écrire `publication.py`, `tasks.py`, le wrapper et la tâche périodique.
- [ ] **Step 4 :** relancer. Attendu : PASS.
- [ ] **Step 5 :** essai réel, si le mainteneur fournit un compte Mastodon de test : connecter le compte, programmer un événement dans 3 jours, lancer `publier_les_annonces_dues()` dans `manage.py shell` → le post apparaît sur l'instance, son lien est en base. Prévenir : redémarrer `lespass_celery`.
- [ ] **Step 6 :** CHANGELOG, puis proposer : `feat(reseaux_sociaux): publie les annonces Mastodon à leur date`.

---

### Task 8 : Connexion Instagram (OAuth) et renouvellement du jeton

**Files :**
- Create : `reseaux_sociaux/instagram.py`, `reseaux_sociaux/views.py`
- Modify : `TiBillet/settings.py` (`INSTAGRAM_APP_ID = os.environ.get("INSTAGRAM_APP_ID", "")`, `INSTAGRAM_APP_SECRET = os.environ.get("INSTAGRAM_APP_SECRET", "")`, près de `MAPTILER_KEY` l. 37), `TiBillet/urls_public.py` (une route), `Administration/admin/reseaux_sociaux.py` (bouton + URL « connecter-instagram/ » via `get_urls`), `reseaux_sociaux/tasks.py`, `TiBillet/celery.py` (`cron_renouveler_les_jetons_instagram`, `crontab(hour=4, minute=0)`)
- Test : `tests/pytest/test_reseaux_sociaux_instagram_connexion.py`

**Interfaces — Produces :**

```python
# reseaux_sociaux/instagram.py — timeout de 15 s ; GRAPH_API_VERSION = "v25.0"
# (version utilisée par Postiz sur sa branche main au 2026-11-27, facebook.provider.ts:27 ;
# à reconfirmer dans la doc Meta au moment de coder)
class ErreurInstagram(Exception): ...
PERMISSIONS = "instagram_business_basic,instagram_business_content_publish"
SEL_DE_SIGNATURE = "reseaux_sociaux.instagram"
def adresse_de_retour() -> str
    # "https://" + domaine principal du Client "public" + "/reseaux-sociaux/instagram/retour/"
def adresse_d_autorisation(uuid_du_lieu: str) -> str
    # https://www.instagram.com/oauth/authorize?enable_fb_login=0&client_id=&redirect_uri=
    # &response_type=code&scope=PERMISSIONS&state=signing.dumps(uuid, salt=SEL_DE_SIGNATURE)
def lire_le_lieu_depuis_l_etat(state: str) -> str
    # signing.loads(state, salt=SEL_DE_SIGNATURE, max_age=900) ; lève signing.BadSignature
def echanger_le_code(code: str) -> dict
    # POST https://api.instagram.com/oauth/access_token (jeton court)
    # GET  https://graph.instagram.com/access_token?grant_type=ig_exchange_token (jeton long)
    # GET  https://graph.instagram.com/{version}/me?fields=user_id,username
    # -> {"jeton": str, "identifiant_utilisateur": str, "nom_du_compte": str}
def renouveler_le_jeton(jeton: str) -> str
    # GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token
```

- `reseaux_sociaux/views.py` : `RetourInstagramViewSet(viewsets.ViewSet)`, avec `permission_classes = [permissions.AllowAny]` et `authentication_classes = []` (les défauts DRF du projet, `settings.py:543-546`, exigent une session et une clé d'API que la personne n'a pas sur le domaine public ; c'est la signature du `state` qui protège). Méthode `list(self, request)`, routé dans `urls_public.py` : `path("reseaux-sociaux/instagram/retour/", RetourInstagramViewSet.as_view({"get": "list"}))`. Flux : lire `state` → `Client` par uuid → `echanger_le_code(code)` → dans `tenant_context(lieu)`, `set_jeton_instagram`, identifiant, nom, `instagram_jeton_obtenu_le = now`, `instagram_renouvellement_echoue_le = None`, `save()` → redirection vers `https://<domaine du lieu>/admin/reseaux_sociaux/configurationreseauxsociaux/` avec `?instagram=connecte`. `state` invalide ou expiré : page d'erreur 400, rien d'écrit. Erreur Instagram : redirection avec `?instagram=echec`. Le singleton affiche un message selon ce paramètre.
- Renouvellement (`tasks.py`) : `renouveler_les_jetons_instagram()` (boucle sur les lieux, module allumé) → `renouveler_les_jetons_instagram_du_lieu()` : si connecté et `instagram_jeton_obtenu_le` a plus de 30 jours, renouveler. En cas de succès : nouveau jeton chiffré, `instagram_jeton_obtenu_le = now`, `instagram_renouvellement_echoue_le = None`. En cas d'échec : `instagram_renouvellement_echoue_le = now`, jeton inchangé.
- Le bouton « Connecter Instagram » est désactivé, avec une phrase d'explication, si `INSTAGRAM_APP_ID` est vide.

- [ ] **Step 1 : tests qui échouent** (`requests` simulé) :
  - `test_l_adresse_d_autorisation_porte_un_etat_signe_du_lieu` : `lire_le_lieu_depuis_l_etat(state extrait de l'URL) == uuid`.
  - `test_un_etat_falsifie_est_refuse` : `lire_le_lieu_depuis_l_etat("faux")` lève `BadSignature`.
  - `test_un_etat_de_plus_de_quinze_minutes_est_refuse` : `state` signé, puis `patch("django.core.signing.time.time")` avancé de 901 s → `SignatureExpired`.
  - `test_echanger_le_code_renvoie_un_jeton_long_et_le_compte` : trois réponses simulées → dict attendu, le jeton est celui de l'étape longue.
  - `test_le_retour_enregistre_le_jeton_chiffre_dans_le_bon_lieu` : appel de la vue avec un `state` valide et `echanger_le_code` simulé → dans le lieu, `get_jeton_instagram() == "jeton-long"`, `instagram_jeton != "jeton-long"`.
  - `test_le_retour_avec_un_etat_falsifie_n_ecrit_rien` : statut 400, singleton inchangé.
  - `test_un_jeton_de_plus_de_trente_jours_est_renouvele` et `test_un_renouvellement_rate_est_note` : `instagram_renouvellement_echoue_le` rempli, jeton inchangé.
- [ ] **Step 2 :** lancer. Attendu : FAIL.
- [ ] **Step 3 :** écrire `instagram.py` (partie connexion), la vue, la route, le bouton, le renouvellement, la tâche périodique.
- [ ] **Step 4 :** relancer. Attendu : PASS. `manage.py check` sans erreur.
- [ ] **Step 5 :** donner au mainteneur l'adresse de retour exacte à déclarer dans la console Meta (cas d'utilisation Instagram, étape 4). L'essai réel se fait en préprod (SPEC §5). Prévenir : redémarrer `lespass_celery`.
- [ ] **Step 6 :** CHANGELOG (variables d'environnement à ajouter), puis proposer : `feat(reseaux_sociaux): connexion Instagram et renouvellement du jeton`.

---

### Task 9 : Publier sur Instagram (post, carrousel, story)

**Files :**
- Create : `reseaux_sociaux/images.py`
- Modify : `reseaux_sociaux/instagram.py`, `reseaux_sociaux/publication.py` (brancher Instagram)
- Test : `tests/pytest/test_reseaux_sociaux_instagram_publication.py`

**Interfaces — Produces :**

```python
# reseaux_sociaux/images.py
TAILLE_POST, TAILLE_STORY = (1080, 1350), (1080, 1920)
def fabriquer_un_jpeg_recadre(fichier_image_source, taille: tuple, nom_du_fichier: str) -> str
    # PIL.Image.open -> exif_transpose -> convert("RGB") (fond blanc si transparence)
    # -> ImageOps.fit(taille, centering=(0.5, 0.5)) -> JPEG qualité 90 dans
    # MEDIA_ROOT/reseaux_sociaux/jpeg/<nom_du_fichier>.jpg. Renvoie l'URL ABSOLUE :
    # f"https://{connection.tenant.get_primary_domain().domain}{settings.MEDIA_URL}reseaux_sociaux/jpeg/<nom>.jpg"
    # (ne pas importer api_v2.serializers : il charge la moitié du projet).

# reseaux_sociaux/instagram.py
def publier_sur_instagram(identifiant_utilisateur: str, jeton: str, format: str,
                          texte: str, urls_des_images: list[str]) -> dict
    # post 1 image : POST /{id}/media (image_url, caption)
    # post 2 à 10 : un conteneur par image (is_carousel_item=true), puis
    #               POST /{id}/media (media_type=CAROUSEL, children=ids, caption)
    # story : POST /{id}/media (image_url, media_type=STORIES), sans caption
    # Attente : GET /{conteneur}?fields=status_code jusqu'à FINISHED, pour CHAQUE conteneur
    # enfant d'un carrousel puis pour le conteneur final (5 essais, 10 s d'écart ;
    # ERROR, EXPIRED ou essais épuisés -> ErreurInstagram).
    # Puis POST /{id}/media_publish (creation_id), GET /{media}?fields=permalink.
    # -> {"identifiant": str, "url": str} ; "url" vide si Instagram ne donne pas de permalink.
```

Dans `publier_une_annonce` : attraper aussi `ErreurInstagram`. Si `url` est vide pour une story, le lien devient `https://www.instagram.com/stories/<instagram_nom_du_compte>/` (le singleton est connu ici, pas dans le client). Images Instagram = image de remplacement du format (`image_post` / `image_story`), sinon `event.get_img()`, puis, pour un post, le carrousel par `order` (10 au total au plus). Chaque image passe par `fabriquer_un_jpeg_recadre` avec le nom `<uuid de la publication>-<rang>`.

- [ ] **Step 1 : tests qui échouent** :
  - `test_un_png_transparent_devient_un_jpeg` : PNG RGBA 300×300 → fichier JPEG de 1080×1350, mode `RGB`.
  - `test_une_affiche_paysage_est_recadree_au_centre_en_story` : image 2000×1000 → 1080×1920.
  - `test_un_post_d_une_image_ne_cree_pas_de_carrousel` : `requests.post` simulé → aucun appel avec `media_type=CAROUSEL`.
  - `test_un_post_de_trois_images_cree_un_carrousel` : 3 conteneurs enfants avec `is_carousel_item`, puis 1 conteneur `CAROUSEL` dont `children` liste les 3 ids.
  - `test_une_story_n_envoie_pas_de_legende` : le conteneur a `media_type=STORIES` et pas de `caption`.
  - `test_un_conteneur_en_erreur_leve_une_erreur_instagram` : `status_code=ERROR` → `ErreurInstagram`, aucun `media_publish`.
  - `test_un_conteneur_jamais_pret_leve_une_erreur_instagram` : `IN_PROGRESS` aux 5 essais → `ErreurInstagram`, aucun `media_publish`.
  - `test_une_annonce_instagram_publiee_garde_son_permalink` : de bout en bout avec `publier_sur_instagram` simulé.
  - `time.sleep` est simulé dans tous ces tests.
- [ ] **Step 2 :** lancer. Attendu : FAIL.
- [ ] **Step 3 :** écrire `images.py`, `publier_sur_instagram`, et le branchement.
- [ ] **Step 4 :** relancer ce fichier et `test_reseaux_sociaux_publication.py`. Attendu : PASS.
- [ ] **Step 5 :** essai réel en préprod, par le mainteneur, avec un compte testeur : post, carrousel et story, puis réponse aux trois questions de SPEC §10.
- [ ] **Step 6 :** CHANGELOG, puis proposer : `feat(reseaux_sociaux): publie les posts, carrousels et stories Instagram`.

---

### Task 10 : Les deux rubriques du récap quotidien

**Files :**
- Modify : `Administration/recap_quotidien.py` (deux fonctions + leur place dans `rubriques_de_la_veille`, l. 971-982 : après `_rubrique_nouveaux_evenements`)
- Test : `tests/pytest/test_recap_quotidien.py` (nouvelle classe, même style que les classes existantes)

**Interfaces — Produces :**

```python
def _rubrique_communication_programmee(debut, fin, domaine) -> dict | None
    # Module éteint -> None. Les événements ayant au moins une Publication créée dans
    # [debut, fin[ (creee_le). Une ligne par événement : {"texte": "<nom> — <dates locales
    # des annonces>", "lien": f"https://{domaine}/admin/BaseBillet/event/{event.pk}/change/"}.
    # cle "communication_programmee", titre _("Communication programmée"),
    # lien de la rubrique : f"https://{domaine}/admin/BaseBillet/event/".
def _rubrique_communication_publiee(debut, fin, domaine) -> dict | None
    # Module éteint -> None. Les Publication publiees ou en echec avec traitee_le dans
    # [debut, fin[. Publiée : {"texte": "<nom> — <réseau> <format>", "lien": url}.
    # Échec : texte "<nom> — <réseau> <format> : échec — <message_d_erreur>", lien vers la
    # fiche admin de l'événement. Plus une ligne si instagram_renouvellement_echoue_le est
    # dans la période : _("Le jeton Instagram n'a pas pu être renouvelé : reconnectez le
    # compte."), lien vers le singleton. cle "communication_publiee",
    # titre _("Communication publiée"), lien de la rubrique : f"https://{domaine}/admin/
    # reseaux_sociaux/configurationreseauxsociaux/". Construit avec _dict_de_la_rubrique
    # (l. 352).
```

- [ ] **Step 1 : tests qui échouent** :
  - `test_les_annonces_programmees_hier_sont_listees_une_fois_par_evenement` : 3 `Publication` d'un même événement créées hier → 1 ligne.
  - `test_une_annonce_publiee_hier_renvoie_vers_le_reseau` : `lien == publication.url`.
  - `test_un_echec_d_hier_montre_son_message` : le texte contient `message_d_erreur`.
  - `test_un_jeton_instagram_non_renouvele_est_signale`.
  - `test_sans_le_module_les_rubriques_sont_absentes` : les deux fonctions renvoient `None`.
- [ ] **Step 2 :** lancer la nouvelle classe. Attendu : FAIL.
- [ ] **Step 3 :** écrire les deux fonctions et les ajouter à la liste.
- [ ] **Step 4 :** relancer **tout** `test_recap_quotidien.py` et `test_demo_recap_de_la_veille.py`. Attendu : PASS.
- [ ] **Step 5 :** CHANGELOG (fin du chantier : section « Comment tester » complète), puis proposer : `feat(admin): ajoute la communication programmée et publiée au récap quotidien`.

---

## Fin du plan

Rapport final au mainteneur :
- les chaînes traduisibles ajoutées : le workflow i18n est à lancer ;
- les variables d'environnement `INSTAGRAM_APP_ID` et `INSTAGRAM_APP_SECRET` ;
- l'adresse de retour à déclarer dans la console Meta ;
- le redémarrage de `lespass_celery` ;
- la liste des migrations, dans l'ordre ;
- ce qui reste à essayer en préprod (SPEC §10).
