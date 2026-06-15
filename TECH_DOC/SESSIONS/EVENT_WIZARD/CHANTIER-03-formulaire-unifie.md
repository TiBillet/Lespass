# CHANTIER 03 — Formulaire event unifié (frontend) + options config + fix image

> **Hub :** [INDEX.md](INDEX.md) · [SPEC.md](SPEC.md) · suite de
> [CHANTIER-02-login-place-split-multi-events.md](CHANTIER-02-login-place-split-multi-events.md)
> **Date :** 2026-06-01
> **Périmètre :** **frontend uniquement** — on NE touche PAS à l'admin Django.
> **Contraintes projet :** aucune opération git de l'assistant · pas de
> `makemessages`/`compilemessages` auto · règle des 3 fichiers avant `check` + tests ·
> serveur tenu par le mainteneur dans byobu · s'arrêter et demander avant le JS (déjà autorisé ici).

## 1. Contexte et objectif

La page publique `/event` propose aujourd'hui **deux boutons / deux wizards frontend** :
- « Ajouter un évènement » → `EventWizardAdmin` (staff, crée des events **publiés**).
- « Proposer un évènement » → `EventWizardPublic` (public, crée des **propositions** modérées,
  `is_proposal=True`), activé par `Configuration.module_agenda_participatif`.

Les deux ViewSets partagent déjà ~90 % du code (helpers `_wizard_*`, template `_events_inner.html`).
Ils ne diffèrent que par : `SESSION_PREFIX`, le serializer (admin ajoute `jauge_max`+`tags`),
`show_admin_fields`, `published`/`is_proposal`, et la garde login (`_require_login_or_redirect`).

**Objectif :** **un seul bouton** sur `/event` → **un seul ViewSet frontend `EventWizard`** qui
s'adapte au contexte (staff vs public). + 3 corrections/ajouts liés (image, tag auto, anonyme,
flux « envoyer »). **L'admin Django (Unfold) reste intact.**

## 2. Décisions validées

| Sujet | Décision |
|---|---|
| Champs communs (tous) | `name`, `datetime`, `long_description`, `image`, **`tags`** |
| Champ staff seulement | `jauge_max` |
| Comportement staff connecté | event **publié** (`published=True, is_proposal=False`) |
| Comportement public (connecté/anonyme) | **proposition modérée** (`published=False, is_proposal=True`) + **tag auto** |
| Fusion | 1 ViewSet front `EventWizard`, 1 bouton sur `/event`. Admin Django non touché. |
| Bouton staff | **toujours visible** pour le staff, même si `module_agenda_participatif` OFF |
| Flux « Envoyer » avec saisie en cours | **SweetAlert** : ajouter d'abord / envoyer sans / annuler |

## 3. Le ViewSet unifié `EventWizard` (frontend)

Un seul `EventWizard(viewsets.ViewSet)` remplace `EventWizardAdmin` + `EventWizardPublic`.
Un **drapeau de contexte** calculé par requête :

```python
def _est_staff(self, request):
    # Staff = a les droits admin du tenant (même critère que l'admin existant).
    # / Staff = has tenant admin rights.
    return request.user.is_authenticated and TenantAdminPermission(request)
```

- `est_staff = True` → `show_admin_fields=True`, serializer avec `jauge_max`, event **publié**.
- `est_staff = False` → champs communs (+ tags), event **proposition** + tag auto.

**Garde d'accès** (remplace `_require_login_or_redirect` figé) :
```python
def _garde_acces(self, request):
    config = Configuration.get_solo()
    if self._est_staff(request):
        return None                      # staff : toujours autorisé
    if not config.module_agenda_participatif:
        raise Http404                    # proposition désactivée
    if not request.user.is_authenticated and not config.proposition_anonyme_autorisee:
        # public anonyme non autorisé -> invite à se connecter
        return redirect(f"{reverse('event-list')}?login=1")
    return None
```

**Un seul `SESSION_PREFIX = "event_wizard"`** (les anciens `event_wizard_admin` /
`event_wizard_public` fusionnent). Helpers `_wizard_*` inchangés.

## 4. Visibilité du bouton unique sur `/event`

| Contexte | `module_agenda_participatif` OFF | ON |
|---|---|---|
| Staff | **bouton visible** (crée publié) | **bouton visible** (crée publié) |
| Public connecté | masqué | **bouton visible** (propose) |
| Anonyme | masqué | **visible si `proposition_anonyme_autorisee`**, sinon le bouton mène au login |

Logique dans `get_context`/le template `/event` : `peut_proposer = est_staff OR
(module_agenda_participatif AND (user_authentifié OR proposition_anonyme_autorisee))`.

## 5. Champs `tags` (nouveau pour le public) — sécurité

`tags` devient commun. Mais création libre de tags par des anonymes = risque de spam/pollution.

- **Staff** : saisie libre (texte séparé par virgules) + création à la volée (`ensure_tag`) —
  comportement actuel inchangé.
- **Public** : **sélection parmi les tags EXISTANTS uniquement** (pas de création). Le serializer
  public ignore/refuse les tags inexistants. Widget : liste de tags existants (cases/chips), ou
  champ texte qui ne matche que l'existant.

> ⚠️ **À confirmer par le mainteneur** : restreindre le public aux tags existants (recommandé,
> anti-spam) vs autoriser la création libre comme le staff.

## 6. Nouveaux champs `Configuration` (« déplacer dans la config »)

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
- `module_agenda_participatif` : **existe déjà** (pivot d'activation).
- Admin : ajouter ces 2 champs dans un fieldset « Agenda participatif » de `ConfigurationAdmin`
  (`Administration/admin_tenant.py`). Migration `BaseBillet` (FK + Bool).

## 7. Bug image (#1) — migration du fichier

Dans `_creer_event_admin_depuis_brouillon` / `_creer_event_public_depuis_brouillon`
(`BaseBillet/views.py` ~3894 / ~3943), remplacer l'assignation directe du chemin par une
**vraie migration** du fichier temp vers le champ image :

```python
# AVANT (bug : pointe sur un fichier temporaire jamais migré)
# event.img.name = draft["image"]

# APRÈS
if draft.get("image"):
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    chemin_temp = draft["image"]
    if default_storage.exists(chemin_temp):
        with default_storage.open(chemin_temp, "rb") as f:
            event.img.save(f"event_{event.uuid.hex[:8]}.jpg", ContentFile(f.read()), save=False)
        default_storage.delete(chemin_temp)
event.save()
```

Résultat : `event.img` pointe vers un vrai fichier sous `images/` (variations StdImage générées),
servi correctement par `/event` (`get_sticker_img` → `get_img`).

## 8. Flux « Envoyer » (#4) — ne pas perdre l'event en cours

Le bouton de finalisation (« Envoyer ma proposition » / « Créer les évènements ») :
- reste **inactif** s'il n'y a aucun brouillon validé (déjà : le serveur renvoie un warning) ;
- au clic, si le **sous-formulaire contient une saisie en cours** (champs non vides, event pas
  encore « Ajouté ») → **SweetAlert** : « Vous avez un évènement non ajouté » avec 3 choix :
  **Ajouter d'abord** (déclenche `events/add` puis envoie) / **Envoyer sans** / **Annuler**.
- Aucune saisie n'est jamais effacée sans confirmation explicite.

Implémentation : garde JS dans le template du step (détection sous-form non vide + SweetAlert2,
déjà utilisé dans le projet). Aucune logique métier côté client (le `events/add` reste serveur).

## 9. Compatibilité & nettoyage

- **Admin Django intact.** Aucune modification de l'admin Unfold.
- Suppression des classes `EventWizardAdmin` et `EventWizardPublic` au profit d'`EventWizard` ;
  les URLs `event-admin-wizard-*` et `event-propose-*` convergent vers les routes d'`EventWizard`
  (garder des alias d'URL si des templates pointent dessus — à vérifier à l'implémentation).
- Serializers : un `WizardEventSerializer` commun (champs communs + `tags`) ; `jauge_max` ajouté
  conditionnellement pour le staff (ou serializer staff dédié héritant du commun).
- Migration `BaseBillet` : 2 champs sur `Configuration` (Bool + FK Tag).

## 10. Tests (pytch)

1. **Bug image** : créer un event via le wizard avec image → `event.img` pointe vers un fichier
   réel sous `images/` (pas `event_wizard_drafts/`), le fichier existe, et le temp est supprimé.
2. **Rôle** : staff → event `published=True`; public → `is_proposal=True` + tag auto présent.
3. **Garde d'accès** : anonyme + module ON + anonyme OFF → redirigé login ; + anonyme ON → autorisé.
4. **Tags public** : un tag inexistant proposé par le public est ignoré (pas de création) ;
   un tag existant est bien appliqué.
5. **Visibilité bouton** : `peut_proposer` correct selon les 6 combinaisons du tableau §4.

## 11. Hors scope

- Admin Django (création d'event via Unfold) — inchangé.
- Le wizard « lieu » (steps place/map) — réutilisé tel quel, non modifié.
