# PLAN 03 — Formulaire event unifié (frontend) — implémentation

> **Exécution inline** (executing-plans). Étapes en checkbox.
> **Spec :** [CHANTIER-03-formulaire-unifie.md](CHANTIER-03-formulaire-unifie.md).
> **Contraintes :** AUCUN git de l'assistant (« commit » → « le mainteneur committe ») · pas de
> `makemessages` auto · règle des 3 fichiers avant `check` + tests · périmètre **frontend**
> (admin Django non touché) · pytch dans le conteneur avec `API_KEY` injecté.

**Goal :** unifier les wizards event front (admin+public) en un seul `EventWizard` (1 bouton sur
`/event`), corriger le bug image, et ajouter 2 options config (anonyme + tag auto).

**Architecture :** 1 ViewSet `EventWizard` piloté par le contexte (staff vs public) ; serializer
unifié (tags commun, jauge staff-only) ; helpers `_wizard_*` réutilisés ; config pivote sur
`module_agenda_participatif` + 2 nouveaux champs.

**Tech Stack :** Django, DRF ViewSet, django-tenants, HTMX, SweetAlert2, StdImageField, pytest.

---

## Ordre d'implémentation (fondations → fusion)

Phase A (sûr, indépendant) : Task 1 (config) + Task 2 (fix image).
Phase B (le gros) : Task 3 (serializer) + Task 4 (fusion ViewSet + URLs).
Phase C (front) : Task 5 (bouton + tags public) + Task 6 (flux JS).
Phase D : Task 7 (tests) + Task 8 (doc).

---

### Task 1 — Config : `proposition_anonyme_autorisee` + `tag_auto_proposition`

**Files :** Modify `BaseBillet/models.py` (classe `Configuration`, près de `module_agenda_participatif` ~571) · Modify `Administration/admin_tenant.py` (`ConfigurationAdmin.fieldsets`)

- [ ] **1.1** Ajouter les 2 champs après `module_agenda_participatif` :
```python
    proposition_anonyme_autorisee = models.BooleanField(
        default=False,
        verbose_name=_("Autoriser les propositions anonymes"),
        help_text=_("Si activé, les visiteurs non connectés peuvent proposer des évènements "
                    "(nécessite le module Agenda participatif)."),
    )
    tag_auto_proposition = models.ForeignKey(
        "BaseBillet.Tag", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="config_tag_auto_proposition",
        verbose_name=_("Tag automatique des évènements proposés"),
        help_text=_("Tag ajouté automatiquement aux évènements proposés via l'agenda participatif."),
    )
```
- [ ] **1.2** `ConfigurationAdmin.fieldsets` : ajouter un fieldset (après « Personnalisation ») :
```python
        (_("Agenda participatif"), {
            "fields": ("module_agenda_participatif", "proposition_anonyme_autorisee", "tag_auto_proposition"),
        }),
```
(retirer `module_agenda_participatif` de son éventuel fieldset actuel pour éviter le doublon — vérifier à l'exécution).
- [ ] **1.3** `makemigrations BaseBillet` + `migrate_schemas` + `check` → 0 issue.
- [ ] **1.4** → le mainteneur committe.

---

### Task 2 — Fix image : migrer le fichier temp vers `images/`

**Files :** Modify `BaseBillet/views.py` (`_creer_event_admin_depuis_brouillon` ~3894, `_creer_event_public_depuis_brouillon` ~3943)

Le bug : `event.img.name = draft["image"]` laisse le fichier dans `event_wizard_drafts/`. Fix :
recopier dans `images/` via `img.save(..., save=False)` (préserve le « 1 seul save » voulu).

- [ ] **2.1** Créer un helper module-level (avant les 2 fonctions) :
```python
def _attacher_image_brouillon(event, draft):
    """
    Migre l'image temp du brouillon (event_wizard_drafts/...) vers le champ img
    de l'event (dossier images/), puis supprime le temp. save=False : l'event sera
    sauvé une seule fois par l'appelant (les signaux ne se declenchent qu'une fois).
    / Migrate the draft temp image into event.img (images/), delete the temp.
    """
    import os
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    chemin_temp = draft.get("image")
    if not chemin_temp or not default_storage.exists(chemin_temp):
        return
    with default_storage.open(chemin_temp, "rb") as f:
        contenu = f.read()
    extension = os.path.splitext(chemin_temp)[1] or ".jpg"
    event.img.save(f"event_{uuid.uuid4().hex[:8]}{extension}", ContentFile(contenu), save=False)
    default_storage.delete(chemin_temp)
```
- [ ] **2.2** Dans `_creer_event_admin_depuis_brouillon` : remplacer
```python
    if draft.get("image"):
        event.img.name = draft["image"]
```
par `_attacher_image_brouillon(event, draft)` (placé AVANT `event.save()`).
- [ ] **2.3** Idem dans `_creer_event_public_depuis_brouillon`.
- [ ] **2.4** `check` → 0 issue. Test manuel + test pytch (Task 7.1).
- [ ] **2.5** → le mainteneur committe.

---

### Task 3 — Serializer unifié `WizardEventSerializer`

**Files :** Modify `BaseBillet/validators.py` (remplacer `WizardEventAdminSerializer` + `WizardEventPublicSerializer`)

- [ ] **3.1** Créer un serializer unifié (tags commun, jauge optionnelle, garde module + anonyme) :
```python
class WizardEventSerializer(serializers.Serializer):
    """
    Step "Event" du wizard unifie. Champs communs + tags ; jauge_max reservee au staff
    (le ViewSet ne la passe que si staff). Tags : pour le public, on ne garde que les
    tags EXISTANTS (anti-spam) ; le staff peut en creer (gere dans le helper de creation).
    / Unified event wizard serializer. Common fields + tags; jauge_max staff-only.
    """
    name = serializers.CharField(max_length=200)
    datetime = serializers.DateTimeField()
    long_description = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    image = serializers.ImageField(required=False, allow_null=True)
    tags = serializers.CharField(required=False, allow_blank=True)
    jauge_max = serializers.IntegerField(required=False, allow_null=True, min_value=1)
```
(La garde `module_agenda_participatif` migre dans la garde d'accès du ViewSet, Task 4.)
- [ ] **3.2** `check` → 0 issue.
- [ ] **3.3** → le mainteneur committe.

---

### Task 4 — Fusion : `EventWizard` (remplace Admin+Public) + URLs + garde accès

**Files :** Modify `BaseBillet/views.py` (supprimer `EventWizardAdmin` + `EventWizardPublic`, créer `EventWizard`) · Modify `BaseBillet/urls.py` (routes wizard)

> **À l'exécution** : LIRE intégralement `EventWizardAdmin` (~3949-4138) et `EventWizardPublic`
> (~4140-4462) avant de fusionner. La majorité des méthodes (`step1_place`, `step_map`,
> `step2_event`, `events_add`, `events_remove`, `done`) sont quasi-identiques → factoriser en
> une seule classe avec `_est_staff(request)` qui pilote `show_admin_fields`, le serializer
> (jauge passée si staff), et `published`/`is_proposal`.

- [ ] **4.1** Ajouter le helper de rôle + garde d'accès (module-level ou méthodes) :
```python
def _wizard_est_staff(request):
    from Administration.admin.site import staff_admin_site  # ou le check tenant existant
    return request.user.is_authenticated and request.user.is_staff
```
> Vérifier à l'exécution le critère « staff » réellement utilisé ailleurs (TenantAdminPermission).
- [ ] **4.2** Créer `EventWizard(viewsets.ViewSet)` :
  - `SESSION_PREFIX = "event_wizard"`.
  - `_garde_acces(request)` : staff → OK ; sinon si `not module_agenda_participatif` → `Http404` ;
    sinon si anonyme et `not proposition_anonyme_autorisee` → `redirect(event-list?login=1)`.
  - `_build_draft(validated, image_path)` : inclut `tags` ; `jauge_max` seulement si staff.
  - `step2_event` POST : pour chaque draft, appeler `_creer_event_depuis_brouillon(draft,
    postal_address, user, est_staff)` (helper unifié, cf. 4.3).
  - `_inner_context_events` : `show_admin_fields = est_staff`, `all_tags = Tag.objects.all()`
    (pour le widget de sélection public).
- [ ] **4.3** Unifier les 2 helpers de création en un seul `_creer_event_depuis_brouillon(draft,
  postal_address, user, est_staff)` :
  - `published = est_staff`, `is_proposal = not est_staff`.
  - image via `_attacher_image_brouillon`.
  - jauge + FREERES seulement si `est_staff` et `draft.get("jauge_max")`.
  - tags : si `est_staff` → `get_or_create` (création libre) ; sinon → **uniquement** les tags
    existants (match par nom, pas de création) + `config.tag_auto_proposition` ajouté.
- [ ] **4.4** `BaseBillet/urls.py` : router unique `EventWizard` sous `event/propose` (basename
  `event-propose`) ; garder des **alias** pour les anciens noms d'URL si des templates les
  référencent (vérifier `grep -rn "event-admin-wizard\|event-propose-" --include=*.html`).
- [ ] **4.5** `check` → 0 issue. Vérifier qu'aucune URL cassée (grep templates).
- [ ] **4.6** → le mainteneur committe.

---

### Task 5 — Bouton unique sur `/event` + tags public (existants)

**Files :** Modify le template de `/event` (liste) + `_events_inner.html` · `get_context` (BaseBillet/views.py)

- [ ] **5.1** `get_context` : exposer `peut_proposer = est_staff or (module_agenda_participatif
  and (user.is_authenticated or proposition_anonyme_autorisee))` et `wizard_url`.
- [ ] **5.2** Template `/event` : remplacer les 2 boutons (« Ajouter » + « Proposer ») par **un
  seul** bouton conditionné par `peut_proposer`, pointant vers le wizard unifié.
- [ ] **5.3** `_events_inner.html` : champ `tags` — si `show_admin_fields` (staff) → input texte
  libre (actuel) ; sinon (public) → liste des `all_tags` existants (chips/checkboxes
  `name="tags"`).
- [ ] **5.4** Vérif visuelle Chrome (les 6 combinaisons du §4 de la spec). `check`.
- [ ] **5.5** → le mainteneur committe.

---

### Task 6 — Flux « Envoyer » (#4) : SweetAlert si saisie en cours

**Files :** Modify le template du step event (JS)

- [ ] **6.1** Garde JS au clic du bouton de finalisation : si le sous-form a des champs non vides
  (event non ajouté) → `Swal.fire` avec 3 actions : **Ajouter d'abord** (submit le form
  `events/add` puis enchaîne l'envoi), **Envoyer sans**, **Annuler**. Aucune saisie effacée sans
  confirmation.
- [ ] **6.2** Vérif visuelle Chrome (saisir un event, ne pas l'ajouter, cliquer Envoyer → popup).
- [ ] **6.3** → le mainteneur committe.

---

### Task 7 — Tests pytch

**Files :** Create `tests/pytest/test_event_wizard_unifie.py`

- [ ] **7.1** Test **fix image** : créer un event via `_creer_event_depuis_brouillon` avec une
  image temp (default_storage) → `event.img.name` commence par `images/`, le fichier existe,
  le temp est supprimé.
- [ ] **7.2** Test **rôle** : `est_staff=True` → `published=True, is_proposal=False` ;
  `est_staff=False` → `is_proposal=True` + `config.tag_auto_proposition` présent dans `event.tag`.
- [ ] **7.3** Test **tags public** : un tag inexistant fourni par le public n'est pas créé
  (count Tag inchangé) ; un tag existant est appliqué.
- [ ] **7.4** Test **garde accès** : anonyme + module ON + anonyme OFF → redirect login ;
  + anonyme ON → 200/autorisé. (via http_client + tenant_context, pattern test_event_wizard_public.)
- [ ] **7.5** Lancer + non-régression : `pytest tests/pytest/test_event_wizard_unifie.py
  tests/pytest/test_event_wizard_public.py tests/pytest/test_event_wizard_admin.py -q`.
- [ ] **7.6** → le mainteneur committe.

---

### Task 8 — Documentation

- [ ] **8.1** `CHANGELOG.md` : entrée « Formulaire event unifié + fix image + options config ».
- [ ] **8.2** `A TESTER et DOCUMENTER/event-formulaire-unifie.md` : scénarios (fix image, rôle,
  tags public, garde accès anonyme, bouton unique, flux Envoyer).
- [ ] **8.3** → le mainteneur committe.

---

## Self-review (spec → plan)

| Exigence CHANTIER-03 | Tâche |
|---|---|
| Fusion 1 ViewSet + 1 bouton (§1,§3) | Task 4, Task 5 |
| Champs : tags commun, jauge staff (§3) | Task 3, Task 5.3 |
| Rôle publié/proposition (§2) | Task 4.3 |
| Accès/visibilité (§4) | Task 4.2, Task 5.1 |
| Config anonyme + tag auto (§6) | Task 1 |
| Fix image (§7) | Task 2 |
| Flux Envoyer SweetAlert (§8) | Task 6 |
| Tags public = existants (§5) | Task 4.3, Task 5.3, Task 7.3 |

Pas de placeholder de logique (les « vérifier à l'exécution » concernent du code existant à lire
avant de fusionner, pas à inventer). Signatures cohérentes :
`_creer_event_depuis_brouillon(draft, postal_address, user, est_staff)`,
`_attacher_image_brouillon(event, draft)`, `WizardEventSerializer`.
