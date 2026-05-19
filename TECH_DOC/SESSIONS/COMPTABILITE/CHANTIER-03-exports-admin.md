# Chantier 03 — Exports admin (remplacer `django-import-export`)

> **Statut** : 📋 SPEC RÉDIGÉE, en attente de validation maintainer
> **Démarrage prévu** : à planifier après validation
> **Date spec** : 2026-05-19
> **Approche choisie** : A — Helpers génériques + 4 modules métier courts

---

## 1. Objectif

Remplacer les **exports** (formats Tableur + PDF) des 4 ModelAdmin qui utilisent
aujourd'hui le plugin `django-import-export` :

- `MembershipAdmin` (adhésions)
- `TicketAdmin` (billets)
- `LigneArticleAdmin` (lignes comptables)
- `EventAdmin` (évènements)

…par la méthode mise en place dans l'app `comptabilite/` (clôture de caisse) :
boutons directs 1-clic, fichiers mis en forme (xlsx stylé + PDF paysage), code
partagé entre admin et exports via `comptabilite/services.py`.

**Les imports** (`MembershipImportResource`, `EventImportResource` pour Event)
sont **conservés** — le plugin `django-import-export` reste mounted pour les
opérations d'import.

## 2. Scope

### On garde

- Le plugin `django-import-export` (dépendance Python conservée)
- L'import Membership via `MembershipImportResource` (création/maj d'adhérents
  depuis un CSV)
- L'import Event via `EventResource` renommée `EventImportResource` (création
  d'évènements depuis un CSV, clé unique `name + datetime`)

### On remplace

- L'export Membership (`MembershipExportResource`, 11 colonnes statiques + clés
  dynamiques `custom_form`)
- L'export Ticket (`TicketExportResource`, 12 colonnes statiques + clés
  dynamiques `reservation.custom_form`)
- L'export LigneArticle (`LigneArticleExportResource`, 14 colonnes)
- L'export Event (18 colonnes, partie export de `EventResource`)

### On ne fait pas

- Pas de CSV custom (Tableur + PDF seulement)
- Pas de JSON / YAML / TSV / ODS (formats exotiques du plugin)
- Pas de sélection dynamique des colonnes (UX figée)
- Pas de background task / email (export synchrone direct)
- Pas de limite de volumétrie (l'export respecte le queryset filtré visible —
  cf. garde-fou sur l'absence de filtre)

## 3. Décisions principales

| # | Décision | Choix retenu |
|---|---|---|
| 1 | Scope | B — Tous les exports admin (4 modèles). Imports conservés. |
| 2 | Formats | Tableur (.xlsx) + PDF (A4 paysage). Pas de CSV ni JSON. |
| 3 | Volumétrie | Toujours exporter tout le queryset filtré visible (pas de limite, pas de background). |
| 4 | Colonnes | Figées par module + clés `custom_form` ajoutées automatiquement au runtime. |
| 5 | Queryset filtré visible | Via `django.contrib.admin.views.main.ChangeList` (comme `django-import-export`). |
| 6 | Garde-fou queryset vide | Redirect changelist + `messages.warning("Aucun élément à exporter.")`. |
| 7 | Garde-fou aucun filtre | Modal HTMX de confirmation avec count des lignes avant téléchargement. |
| 8 | Anti-N+1 | Fonction `optimiser(qs)` par module + tests `django_assert_num_queries` obligatoires. |
| 9 | Template bandeau | 1 partagé `bandeau_exports.html` réutilisé sur les 4 admins. |
| 10 | Ordre migration | Ajouter d'abord (sessions 1-3), retirer ensuite (session 4). |
| 11 | Localisation code | Sous-dossier `Administration/exports/` (pas une vraie app Django, pas de modèles). |

## 4. Architecture

```
Administration/exports/                       # nouveau dossier (sous-module Python)
├── __init__.py
├── helpers/
│   ├── __init__.py
│   ├── xlsx.py                               # generer_xlsx(titre, meta, colonnes, lignes)
│   └── pdf.py                                # generer_pdf(titre, meta, colonnes, lignes)
├── membership.py                             # colonnes + aplatir + optimiser
├── ticket.py
├── lignearticle.py
└── event.py

Administration/templates/exports/
├── pdf_generique.html                        # A4 paysage, table dynamique
└── admin/
    ├── bandeau_exports.html                  # 2 boutons en haut de changelist
    └── confirmation_sans_filtre.html         # modal HTMX
```

### Principe de séparation

- **Couche `helpers/`** : aucune connaissance des modèles Django. Reçoit une
  liste de dicts + des colonnes, produit `(bytes, filename, content_type)`.
  Réutilisable au-delà de ces 4 cas.
- **Couche métier** (`membership.py`, etc.) : seule à toucher aux modèles.
  Expose 3 fonctions publiques par modèle :
  - `colonnes(queryset) -> list[str]` — statiques + dynamiques custom_form
  - `aplatir(queryset) -> list[dict]` — itère et produit 1 dict par objet
  - `optimiser(queryset) -> QuerySet` — applique `select_related` / `prefetch_related`
- **Couche admin** : les `ModelAdmin` reçoivent juste les vues `exporter_tableur`
  et `exporter_pdf` qui orchestrent : filtre via ChangeList → optimiser → aplatir
  → helper xlsx/pdf → `HttpResponse` téléchargement.

## 5. Composants par modèle (colonnes exactes)

### 5.1 `membership.py` (11 colonnes statiques + `custom_form` dynamique)

| Colonne FR | Source modèle |
|---|---|
| last_contribution | `Membership.last_contribution` |
| email | `user.email` |
| member_name | `Membership.member_name` (méthode) |
| produit | `price.product.name` |
| tarif | `price.name` |
| contribution | `Membership.contribution_value` (Decimal, format euros) |
| moyen_paiement | `Membership.payment_method_name` (méthode) |
| options | `Membership.options.all()` (M2M, joint séparateur `;`) |
| valide | `Membership.is_valid` (méthode → "oui"/"non") |
| deadline | `Membership.deadline` |
| statut | `Membership.status_name` (méthode) |
| `<clé custom_form 1>` … | clés JSON découvertes en parcourant le qs |

`optimiser` : `select_related('user', 'price__product').prefetch_related('options')`

### 5.2 `ticket.py` (12 colonnes statiques + `reservation.custom_form` dynamique)

| Colonne FR | Source modèle |
|---|---|
| event | `reservation.event.name` |
| event_datetime | `reservation.event.datetime` (formaté TZ du tenant) |
| email | `reservation.user_commande.email` |
| user_id | `f"{email} {reservation.uuid:.4}"` |
| reservation_uuid | `reservation.uuid` |
| ticket_uuid | `Ticket.numero_uuid` |
| statut | `Ticket.get_status_display()` |
| tarif | `pricesold.price.name` |
| produit | `pricesold.productsold.product.name` |
| options | `Ticket.options` (M2M) |
| reservation_datetime | `reservation.datetime` (formaté TZ) |
| moyen_paiement | `Ticket.get_payment_method_display()` |
| `<clé reservation.custom_form 1>` … | clés JSON découvertes en parcourant le qs |

`optimiser` : `select_related('reservation__event', 'reservation__user_commande',
'pricesold__price', 'pricesold__productsold__product').prefetch_related('options')`

### 5.3 `lignearticle.py` (14 colonnes)

| Colonne FR | Source modèle |
|---|---|
| uuid | `LigneArticle.uuid` (Référence paiement) |
| date | `LigneArticle.datetime` (formaté TZ, `%Y-%m-%d`) |
| produit | `pricesold` (Libellé) |
| quantite | `LigneArticle.qty` |
| prix_unitaire | `LigneArticle.amount / 100` (euros) |
| tva | `LigneArticle.vat` |
| montant | `LigneArticle.total() / 100` (euros) |
| moyen_paiement | `LigneArticle.get_payment_method_display()` |
| statut | `LigneArticle.get_status_display()` |
| email_user | `LigneArticle.user_email()` (méthode, attention FK) |
| stripe_uuid | `LigneArticle.paiement_stripe_uuid()` (méthode, attention FK) |
| carte | `LigneArticle.carte` |
| wallet | `LigneArticle.wallet` |
| ref_avoir | `LigneArticle.credit_note_for.uuid[:8]` si présent |

`optimiser` : `select_related('pricesold__productsold__product', 'carte', 'wallet',
'credit_note_for', 'paiement_stripe')`

**⚠️ Audit FK** : `user_email()` et `paiement_stripe_uuid()` sont des méthodes
du modèle qui font des accès FK invisibles. À tracer en session 1 et compléter
`select_related` en conséquence. Mitigé par tests `django_assert_num_queries`.

### 5.4 `event.py` (18 colonnes)

| Colonne | Source modèle |
|---|---|
| name | `Event.name` |
| datetime | `Event.datetime` |
| end_datetime | `Event.end_datetime` |
| jauge_max | `Event.jauge_max` |
| max_per_user | `Event.max_per_user` |
| short_description | `Event.short_description` |
| long_description | `Event.long_description` |
| published | `Event.published` |
| archived | `Event.archived` |
| private | `Event.private` |
| show_time | `Event.show_time` |
| show_gauge | `Event.show_gauge` |
| slug | `Event.slug` |
| is_external | `Event.is_external` |
| full_url | `Event.full_url` |
| postal_address | `postal_address.name` (FK) |
| reservation_button_name | `Event.reservation_button_name` |
| minimum_cashless_required | `Event.minimum_cashless_required` |

Les noms techniques restent en **anglais** (pas de FR-isation) pour la
compatibilité avec le ré-import (les colonnes du CSV exporté doivent matcher
celles attendues par `EventImportResource`).

`optimiser` : `select_related('postal_address')`

## 6. Data flow

```
1. User clique "📊 Tableur" sur /admin/basebillet/membership/?status_valid=Y
   ↓
2. GET /admin/basebillet/membership/exporter-tableur/?status_valid=Y
   (les params GET portent les filtres actifs)
   ↓
3. MembershipAdmin.exporter_tableur(request)
   ↓
4. qs = self._queryset_filtre_visible(request)
   → utilise ChangeList(request, self.model, ...) pour appliquer
     search box + list_filter + date_hierarchy (comme django-import-export)
   ↓
5. Garde-fou queryset vide
   if qs.count() == 0:
       messages.warning(request, _("Aucun élément à exporter."))
       return redirect("admin:basebillet_membership_changelist")
   ↓
6. Garde-fou aucun filtre actif
   if not request.GET.dict() and not request.GET.get('force') == '1':
       return render(..., "exports/admin/confirmation_sans_filtre.html",
                     {"count": qs.count(), "url": "?force=1"})
   ↓
7. qs_optim = exports.membership.optimiser(qs)
   ↓
8. colonnes = exports.membership.colonnes(qs_optim)
   → ['last_contribution', 'email', ..., 'q1', 'q2']  # custom_form en queue
   ↓
9. lignes = exports.membership.aplatir(qs_optim)
   → [{...}, {...}, ...]
   ↓
10. bytes_, name, ctype = helpers.xlsx.generer_xlsx(
        titre="Adhésions",
        meta={'filtres_actifs': '...', 'tenant': 'lespass', 'date': '2026-05-19'},
        colonnes=colonnes,
        lignes=lignes,
    )
    ↓
11. return HttpResponse(bytes_, content_type=ctype) avec Content-Disposition
```

## 7. Intégration ModelAdmin

### 7.1 Pattern type (sur les 4 admins)

```python
class MembershipAdmin(ModelAdmin, ImportExportModelAdmin):
    # ... existant ...
    changelist_before_template = "exports/admin/bandeau_exports.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("exporter-tableur/",
                 self.admin_site.admin_view(self.exporter_tableur),
                 name="basebillet_membership_exporter_tableur"),
            path("exporter-pdf/",
                 self.admin_site.admin_view(self.exporter_pdf),
                 name="basebillet_membership_exporter_pdf"),
        ]
        return custom + urls

    def exporter_tableur(self, request):
        return self._exporter(request, format="tableur")

    def exporter_pdf(self, request):
        return self._exporter(request, format="pdf")

    def _exporter(self, request, format):
        from Administration.exports import membership as exp_mb
        qs = self._queryset_filtre_visible(request)
        # Garde-fous (queryset vide + pas de filtre)
        if qs.count() == 0:
            messages.warning(request, _("Aucun élément à exporter."))
            return redirect("admin:basebillet_membership_changelist")
        if not request.GET and request.GET.get('force') != '1':
            return render(request,
                          "exports/admin/confirmation_sans_filtre.html",
                          {"count": qs.count(), "format": format})
        qs_optim = exp_mb.optimiser(qs)
        if format == "tableur":
            from Administration.exports.helpers.xlsx import generer_xlsx
            bytes_, name, ctype = generer_xlsx(
                titre=_("Adhésions"),
                meta=self._build_meta(request),
                colonnes=exp_mb.colonnes(qs_optim),
                lignes=exp_mb.aplatir(qs_optim),
            )
        else:
            from Administration.exports.helpers.pdf import generer_pdf
            bytes_, name, ctype = generer_pdf(...)
        return _telecharger(bytes_, name, ctype)
```

### 7.2 Helper mutualisable `_queryset_filtre_visible`

Pattern repris de `django-import-export` (re-créer `ChangeList`) — placer dans
`Administration/exports/__init__.py` ou un mixin réutilisable.

### 7.3 Template bandeau partagé

```html
{# Administration/templates/exports/admin/bandeau_exports.html #}
{% load i18n %}
<div class="flex flex-row gap-2 mb-4">
    <a href="exporter-tableur/{{ request.GET.urlencode|default:'' }}"
       data-testid="export-tableur"
       class="bg-base-100 ... px-3 py-2 rounded-md">
        📊 {% translate "Tableur" %}
    </a>
    <a href="exporter-pdf/{{ request.GET.urlencode|default:'' }}"
       data-testid="export-pdf"
       class="bg-base-100 ... px-3 py-2 rounded-md">
        🖨️ {% translate "PDF" %}
    </a>
</div>
```

Les params GET sont propagés pour conserver les filtres actifs.

## 8. Découpage en sessions

| # | Session | Sortie | Durée |
|---|---|---|---|
| S1 | Helpers génériques + LigneArticle (pilote) | xlsx.py, pdf.py, templates, lignearticle.py, modifs LigneArticleAdmin, tests | 1-2 j |
| S2 | Membership + Ticket (custom_form dynamique) | membership.py, ticket.py, modifs admins, tests | 1 j |
| S3 | Event + scinder EventResource → EventImportResource | event.py, modifs EventAdmin, EventResource renommée + nettoyée | 1 j |
| S4 | Cleanup : retrait des exports plugin | Suppression Resources export, ajustement `ImportExportModelAdmin` → `ImportModelAdmin` où pertinent | 0.5 j |

**Validation entre chaque session** : maintainer teste manuellement dans le
navigateur (Tableur + PDF, avec/sans filtre, comparaison au CSV plugin tant
qu'il est encore actif).

## 9. Vérifications à passer à chaque session

```bash
# Check Django
docker exec lespass_django poetry run python /DjangoFiles/manage.py check

# Tests pytest exports (ciblés)
docker exec lespass_django poetry run pytest tests/pytest/test_export_*.py -v

# Tests anti-N+1 (focus)
docker exec lespass_django poetry run pytest tests/pytest/test_export_*.py -k "n_plus_1" -v
```

## 10. Tests

### 10.1 Par module métier (4 fichiers)

`tests/pytest/test_export_<modele>.py` :

```python
def test_colonnes_retourne_liste_attendue(...)
def test_aplatir_produit_dict_avec_toutes_les_colonnes(...)
def test_aplatir_respecte_select_related_pas_de_n_plus_1(django_assert_num_queries)
def test_aplatir_inclut_cles_custom_form_dynamiques(...)  # Membership, Ticket
def test_optimiser_applique_select_related_attendu(...)
```

### 10.2 Helpers (1 fichier)

`tests/pytest/test_export_helpers.py` :

```python
def test_generer_xlsx_avec_liste_vide_retourne_fichier_avec_en_tetes(...)
def test_generer_xlsx_avec_donnees_produit_fichier_ouvrable_openpyxl(...)
def test_generer_pdf_renvoie_pdf_valide_paysage(...)  # parser pdfinfo
def test_meta_en_tete_pdf_affiche_filtres_actifs(...)
```

### 10.3 Intégration admin (1 fichier)

`tests/pytest/test_export_admin_integration.py` :

```python
def test_admin_export_tableur_membership_redirige_si_queryset_vide(...)
def test_admin_export_tableur_membership_modal_si_pas_de_filtre(...)
def test_admin_export_tableur_membership_telecharge_si_filtre_actif(...)
def test_admin_export_pdf_ticket_respecte_filtre_event(...)
```

### 10.4 Anti-régression (temporaire, supprimé en S4)

Comparaison ligne à ligne du nouvel export Tableur avec le CSV produit par le
plugin sur le même queryset. Test jeté en session 4 (le plugin n'expose plus
d'export après cleanup).

## 11. Risques + mitigations

| Risque | Niveau | Mitigation |
|---|---|---|
| Méthodes modèle cachées avec FK (`user_email()`, `paiement_stripe_uuid()`, etc.) → N+1 silencieux | Moyen | Tests `django_assert_num_queries` obligatoires + audit case-par-case en S1 |
| `EventResource` fait import + export dans une classe → casse possible à la scission | Faible | Tests d'import event existants (à vérifier) + renommage explicite `EventImportResource` |
| `ChangeList` API privée Django peut changer | Faible | Copier le pattern exact du plugin `django-import-export` (déjà éprouvé sur cette version Django) |
| Volume d'export énorme sur DB chargée (millions de tickets) | Moyen | Garde-fou modal "pas de filtre" + maintenir le maintainer informé que la stratégie reste synchrone (cf. décision 3) |
| `custom_form` avec clés inhabituelles (espaces, caractères spéciaux) | Faible | Pattern actuel des Resources sanitise déjà ; reprendre le même comportement |

## 12. Rollback

### Avant session 4

- Retirer le dossier `Administration/exports/` complètement
- Retirer les `get_urls()` ajoutés sur les 4 admins
- Retirer `changelist_before_template` sur les 4 admins
- Le plugin `django-import-export` reste fonctionnel comme avant

### Après session 4

- `git revert` du commit de cleanup S4 → restaure les Resources d'export
  supprimées + remet `ImportExportModelAdmin` au lieu de `ImportModelAdmin`
- `git revert` des commits S1-S3 → retire le sous-module exports/

## 13. Estimation totale

| Métrique | Valeur |
|---|---|
| Volume code + tests | ~1380 lignes |
| Durée dev | ~4 jours (S1: 1-2j, S2: 1j, S3: 1j, S4: 0.5j) |
| Nombre de fichiers nouveaux | ~14 (4 modules métier + 2 helpers + 5 templates + 3-4 fichiers de tests) |
| Nombre de fichiers modifiés | ~6 (4 admins + admin_tenant.py + pyproject inchangé) |
| Nombre de fichiers supprimés (en S4) | 2 (`lignearticle_exporter.py`, `ticket_exporter.py`) |

## 14. Statut

- [x] 0.1 Exploration code existant (`django-import-export` Resources)
- [x] 0.2 Validation scope (B — tous exports, imports conservés)
- [x] 0.3 Validation formats (Tableur + PDF, pas de CSV)
- [x] 0.4 Validation volumétrie (queryset filtré visible)
- [x] 0.5 Validation anti-régression (audit colonne par colonne fait)
- [x] 0.6 Validation décisions techniques (N+1, modal sans filtre, queryset vide)
- [x] 0.7 Rédaction de la spec (ce document)
- [ ] 0.8 Validation maintainer (lecture finale + go pour planning)
- [ ] S1 — Helpers + LigneArticle pilote
- [ ] S2 — Membership + Ticket
- [ ] S3 — Event + scinder Resource
- [ ] S4 — Cleanup retrait exports plugin

## 15. Liens

- Référence pattern compta : [`comptabilite/services.py`](../../../comptabilite/services.py)
  (`aplatir_detail_ventes`, `enrichir_rapport_pour_affichage`)
- Référence helpers exports compta : [`comptabilite/excel_export.py`](../../../comptabilite/excel_export.py),
  [`comptabilite/pdf.py`](../../../comptabilite/pdf.py)
- Resources existantes à remplacer :
  - [`Administration/importers/membership_importers.py`](../../../Administration/importers/membership_importers.py)
  - [`Administration/importers/ticket_exporter.py`](../../../Administration/importers/ticket_exporter.py)
  - [`Administration/importers/lignearticle_exporter.py`](../../../Administration/importers/lignearticle_exporter.py)
  - `Administration/admin_tenant.py` (EventResource ligne 1982)
- Plugin Unfold : `unfold.contrib.import_export.forms.ExportForm` (conservé
  pour les imports uniquement)

---

## Notes pour les sessions

1. **S1 ouvrira la voie** : roder le pattern sur LigneArticle (modèle sans
   custom_form, FK simples). Les helpers `xlsx.py` et `pdf.py` produits en S1
   seront réutilisés tels quels en S2/S3.

2. **S2 ajoutera la complexité custom_form** : extraire un helper
   `_collecter_cles_custom_form(qs, path)` mutualisé entre Membership et Ticket
   (le `path` est `"custom_form"` pour Membership, `"reservation__custom_form"`
   pour Ticket).

3. **S3 a un piège** : `EventResource` est à la fois `ImportModelAdmin` ET
   `ExportModelAdmin`. Le `Meta.fields` est utilisé pour matcher les colonnes
   du CSV à l'import — si on le modifie, on casse l'import. **NE PAS** toucher
   au `Meta.fields` ; juste renommer la classe et retirer la partie export
   (le plugin Unfold expose import-only via `has_export_permission = False`).

4. **S4 doit être commit isolé** pour permettre un `git revert` ciblé en cas
   de problème en prod après mise en production.
