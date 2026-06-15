# Plan d'implémentation — S5 (Chantier 01 / App `comptabilite`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.
>
> **Hub :** [`INDEX.md`](INDEX.md) — **Spec :** [`SPEC.md`](SPEC.md) §2.4, §6.5, §7, §9
>
> **Garde-fous projet :**
> - **JAMAIS d'opération `git`**.
> - **Pas de `runserver_plus`** — serveur byobu sur port 8002.
> - **Pas de `ruff format` sur fichiers existants** — uniquement sur fichiers neufs.

**Goal :** Compléter l'écosystème comptable V1 avec :
1. **Plan comptable paramétrable** par tenant (modèles `CompteComptable` + `MappingMoyenDePaiement` + seed PCG français).
2. **Framework profils CSV comptables** + 3 premiers profils : Sage 50, EBP, Paheko.
3. **Génération auto Celery beat** des clôtures J/H/M/A.
4. **Email automatique** du rapport (PDF en pièce jointe) selon `Configuration.rapport_periodicite`.

**Tech Stack :** Django ORM, openpyxl, SMTP (via `CeleryMailerClass` existant V1), Celery beat (pattern `cron_morning`), data migration.

---

## File structure produite par S5

```
comptabilite/
├── models.py                                      # MODIFIÉ : +2 modèles
├── migrations/
│   └── 0002_compte_comptable_mapping.py           # nouveau (avec data migration seed PCG)
├── profils_csv.py                                 # nouveau (config 3 profils)
├── csv_comptable.py                               # nouveau (génération CSV via profil)
├── tasks.py                                       # MODIFIÉ : +envoyer_email_cloture
├── admin.py                                       # MODIFIÉ : 2 ModelAdmin + URL export CSV comptable
└── templates/comptabilite/admin/
    └── export_csv_comptable_form.html             # nouveau (form HTMX)

Administration/admin/dashboard.py                  # MODIFIÉ : +2 sidebar entries
TiBillet/celery.py                                 # MODIFIÉ : +4 wrappers cron J/H/M/A
tests/pytest/
├── test_comptabilite_models.py                    # nouveau (modèles + seed)
├── test_comptabilite_csv_comptable.py             # nouveau (3 profils)
└── test_comptabilite_celery.py                    # nouveau (tâches + email mock)
```

---

## Découpage en 4 blocs subagent

| Bloc | Tasks | Tests cible |
|---|---|---|
| **B1** | Modèles `CompteComptable` + `MappingMoyenDePaiement` + migration 0002 avec data migration de seed PCG (9 comptes + 13 mappings) + admin Unfold pour les 2 modèles + sidebar entries | 4 tests modèles |
| **B2** | `profils_csv.py` (3 profils Sage50/EBP/Paheko) + `csv_comptable.py` (ventilation lignes : débits trésorerie + crédits 706/756 + crédits TVA) | 3 tests (1 par profil) |
| **B3** | URL admin `<uuid>/exporter-csv-comptable/` (GET form HTMX, POST génère CSV) + template HTMX + bouton dans `change_form_before.html` | 2 tests smoke |
| **B4** | Wrappers `cron_cloture_*` dans `TiBillet/celery.py` (J/H/M/A) + `envoyer_email_cloture` task + intégration avec `Configuration.rapport_emails` / `rapport_periodicite` | 3 tests (1 task + 1 email mock + 1 idempotence) |

---

## Bloc B1 — Modèles CompteComptable + MappingMoyenDePaiement

### Modèles (à ajouter dans `comptabilite/models.py`)

```python
class CompteComptable(models.Model):
    """
    Compte comptable utilise pour la ventilation des ecritures (FEC, CSV comptable).
    / Accounting account used for entry dispatch (FEC, accounting CSV exports).
    """

    TYPE_VENTE = "V"
    TYPE_TVA = "T"
    TYPE_TRESORERIE = "B"
    TYPE_CLIENT = "C"
    TYPE_AUTRE = "X"
    TYPE_CHOICES = [
        (TYPE_VENTE, _("Sales")),
        (TYPE_TVA, _("VAT collected")),
        (TYPE_TRESORERIE, _("Cash / Bank")),
        (TYPE_CLIENT, _("Customers")),
        (TYPE_AUTRE, _("Other")),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid_lib.uuid4, editable=False)
    numero = models.CharField(max_length=12, unique=True, verbose_name=_("Account number"))
    libelle = models.CharField(max_length=120, verbose_name=_("Label"))
    type_compte = models.CharField(max_length=1, choices=TYPE_CHOICES)
    actif = models.BooleanField(default=True, verbose_name=_("Active"))

    class Meta:
        ordering = ["numero"]
        verbose_name = _("Accounting account")
        verbose_name_plural = _("Accounting accounts")

    def __str__(self):
        return f"{self.numero} — {self.libelle}"


class MappingMoyenDePaiement(models.Model):
    """
    Mappage d'un moyen de paiement (PaymentMethod) vers un compte comptable.
    / Maps a PaymentMethod code to an accounting account.
    """
    payment_method = models.CharField(
        max_length=2, unique=True, verbose_name=_("Payment method"),
        help_text=_("PaymentMethod code from BaseBillet (CC, CA, CH, TR, SF, ...)"),
    )
    compte = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        verbose_name=_("Accounting account"),
        limit_choices_to={"type_compte__in": ["B", "C"]},
    )

    class Meta:
        ordering = ["payment_method"]
        verbose_name = _("Payment method mapping")
        verbose_name_plural = _("Payment method mappings")

    def __str__(self):
        return f"{self.get_payment_method_display()} → {self.compte}"
```

### Data migration seed PCG français

Dans `comptabilite/migrations/0002_compte_comptable_mapping.py`, utiliser `RunPython` pour créer les 9 comptes + 13 mappings par défaut (cf. SPEC §2.4 pour les valeurs exactes).

**Guard schema public** : la migration doit `return` si `connection.schema_name == "public"` (modèle TENANT_APP).

### Admin Unfold

2 `ModelAdmin` simples dans `admin.py` avec :
- `compressed_fields=True`, `warn_unsaved_form=True`
- 4 permissions via `TenantAdminPermissionWithRequest`
- `list_display`, `list_filter` (type_compte), `search_fields`

### Sidebar

Dans `Administration/admin/dashboard.py`, section *Sales & accounting*, après « Entries » (=LigneArticle), décommenter et adapter les 2 items :

```python
{
    "title": _("Accounting accounts"),
    "icon": "account_balance",
    "link": reverse_lazy("staff_admin:comptabilite_comptecomptable_changelist"),
    "permission": admin_permission,
},
{
    "title": _("Payment method mapping"),
    "icon": "swap_horiz",
    "link": reverse_lazy("staff_admin:comptabilite_mappingmoyendepaiement_changelist"),
    "permission": admin_permission,
},
```

---

## Bloc B2 — Profils CSV comptables (Sage 50 + EBP + Paheko)

### `comptabilite/profils_csv.py`

```python
PROFILS = {
    "sage_50": {
        "nom_affiche": "Sage 50",
        "separateur": ";",
        "decimal": ".",
        "encodage": "utf-8-sig",
        "mode_montant": "DEBIT_CREDIT",
        "format_date": "%d/%m/%Y",
        "colonnes": ["JournalCode", "EcritureDate", "CompteNum", "CompteLib",
                     "PieceRef", "EcritureLib", "Debit", "Credit"],
        "extension": ".csv",
    },
    "ebp": {
        "nom_affiche": "EBP Compta",
        "separateur": ",",
        "decimal": ".",
        "encodage": "cp1252",
        "mode_montant": "MONTANT_SENS",
        "format_date": "%d/%m/%Y",
        "colonnes": ["Date", "Journal", "Compte", "Libelle", "Montant", "Sens"],
        "extension": ".txt",
    },
    "paheko": {
        "nom_affiche": "Paheko / Garradin",
        "separateur": ";",
        "decimal": ",",
        "encodage": "utf-8",
        "mode_montant": "MONTANT_UNIQUE",  # compte_debit + compte_credit + montant
        "format_date": "%Y-%m-%d",
        "colonnes": ["date", "libelle", "compte_debit", "compte_credit", "montant"],
        "extension": ".csv",
    },
}
```

### `comptabilite/csv_comptable.py`

Fonction `generer_csv_comptable(cloture, profil_slug) -> (bytes, filename, content_type, avertissements)`.

Pipeline :
1. Charger config via `PROFILS[profil_slug]`
2. Calculer les écritures comptables (ventilation) :
   - 1 débit trésorerie par moyen de paiement utilisé (via `MappingMoyenDePaiement` → compte)
   - 1 crédit `706000` (Prestations - Billets) pour total billets HT
   - 1 crédit `756000` (Cotisations - Adhesions) pour total adhésions HT
   - 1 crédit `4457X` par taux TVA
3. Rendre selon le `mode_montant` du profil :
   - `DEBIT_CREDIT` : 2 colonnes (Debit, Credit)
   - `MONTANT_SENS` : 1 colonne montant + 1 colonne sens (D/C)
   - `MONTANT_UNIQUE` : compte_débit + compte_crédit + 1 colonne montant
4. Encoder selon `encodage` du profil
5. Retourner `(bytes, filename, content_type, avertissements)`.
   - `avertissements` = liste de strings flaggant les paiements/catégories sans mapping (utilise les comptes par défaut PCG).

### Tests

3 tests : 1 par profil. Pour chacun :
- Vérifier que le contenu est non vide
- Vérifier que le séparateur est correct
- Vérifier que le format de date est correct
- Vérifier que les colonnes attendues sont présentes

---

## Bloc B3 — Vue admin + form HTMX

### URL admin

Dans `ClotureCaisseAdmin.get_urls()`, ajouter :

```python
path(
    "<uuid:object_id>/exporter-csv-comptable/",
    self.admin_site.admin_view(self.exporter_csv_comptable),
    name="comptabilite_cloturecaisse_csv_comptable",
),
```

### Vue `exporter_csv_comptable`

- **GET** : retourne le partial form HTMX (select profil + champs date optionnels) — pour l'instant on ignore les dates (juste profil)
- **POST** : génère le CSV avec le profil choisi, retourne le fichier

```python
def exporter_csv_comptable(self, request, object_id):
    """
    Export CSV comptable avec choix du profil (Sage50 / EBP / Paheko).
    GET = form HTMX. POST = telecharge le CSV genere.
    / Accounting CSV export with profile choice. GET = HTMX form. POST = download.
    """
    from django.shortcuts import get_object_or_404, render
    from comptabilite.csv_comptable import generer_csv_comptable
    from comptabilite.profils_csv import PROFILS

    cloture = get_object_or_404(ClotureCaisse, pk=object_id)

    if request.method == "POST":
        profil_slug = request.POST.get("profil", "sage_50")
        if profil_slug not in PROFILS:
            profil_slug = "sage_50"
        bytes_data, filename, content_type, avertissements = generer_csv_comptable(
            cloture, profil_slug
        )
        # Si avertissements, on les logue (et un futur S6 pourra les afficher dans un toast)
        if avertissements:
            import logging
            logging.getLogger(__name__).warning(
                f"CSV comptable {profil_slug} pour cloture #{cloture.numero_sequentiel}: "
                f"{len(avertissements)} avertissement(s)"
            )
        return _telecharger(bytes_data, filename, content_type)

    # GET : retourne le form HTMX
    return render(
        request,
        "comptabilite/admin/export_csv_comptable_form.html",
        {
            "cloture": cloture,
            "profils": [(slug, p["nom_affiche"]) for slug, p in PROFILS.items()],
        },
    )
```

### Template `export_csv_comptable_form.html`

```html
{% load i18n %}

<div class="bg-base-100 dark:bg-base-800 border border-base-200 dark:border-base-700 rounded-md p-4">
    <h3 class="text-base font-semibold mb-2">
        {% translate "Accounting CSV export" %}
    </h3>
    <p class="text-sm text-base-500 mb-3">
        {% translate "Choose the format matching your accounting software." %}
    </p>
    <form method="post"
          action="../exporter-csv-comptable/"
          data-testid="comptabilite-form-csv-comptable">
        {% csrf_token %}
        <div class="flex flex-row gap-2 items-end flex-wrap">
            <div class="flex flex-col">
                <label for="profil-select" class="text-sm font-medium mb-1">
                    {% translate "Accounting software" %}
                </label>
                <select name="profil"
                        id="profil-select"
                        data-testid="comptabilite-select-profil"
                        class="border border-base-200 dark:border-base-700 rounded-md px-3 py-2 bg-base-0 dark:bg-base-900">
                    {% for slug, label in profils %}
                        <option value="{{ slug }}">{{ label }}</option>
                    {% endfor %}
                </select>
            </div>
            <button type="submit"
                    data-testid="comptabilite-bouton-telecharger-csv-comptable"
                    class="bg-primary-600 hover:bg-primary-700 text-white px-4 py-2 rounded-md font-medium">
                {% translate "Download" %}
            </button>
        </div>
    </form>
</div>
```

### Bouton dans `change_form_before.html`

Le bouton utilise HTMX pour charger le form dans une zone dédiée :

```html
<button type="button"
        data-testid="comptabilite-bouton-csv-comptable"
        hx-get="exporter-csv-comptable/"
        hx-target="#zone-csv-comptable"
        hx-swap="innerHTML"
        class="bg-base-100 hover:bg-base-200 dark:bg-base-800 dark:hover:bg-base-700 px-3 py-2 rounded-md text-sm font-medium border border-base-200 dark:border-base-700">
    📑 {% translate "CSV comptable" %}
</button>
```

Et ajouter une zone vide en dessous du bandeau :

```html
<div id="zone-csv-comptable" class="mt-2"></div>
```

⚠️ HTMX doit être chargé dans la fiche admin. **Vérifier** s'il est inclus par Unfold ou ajouter `<script src="{% static 'mvt_htmx/js/htmx.min.1.9.12.js' %}"></script>` dans le template.

### Tests

```python
def test_export_csv_comptable_get_retourne_form(admin_client_avec_cloture):
    """GET .../exporter-csv-comptable/ retourne le form HTMX avec select profil."""
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    response = client.get(
        f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-csv-comptable/"
    )
    assert response.status_code == 200
    contenu = response.content.decode("utf-8")
    assert 'data-testid="comptabilite-form-csv-comptable"' in contenu
    assert 'data-testid="comptabilite-select-profil"' in contenu
    assert "Sage" in contenu  # au moins un profil dans le select


def test_export_csv_comptable_post_telecharge(admin_client_avec_cloture):
    """POST .../exporter-csv-comptable/?profil=sage_50 telecharge le CSV."""
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    response = client.post(
        f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-csv-comptable/",
        {"profil": "sage_50"},
    )
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
```

---

## Bloc B4 — Celery beat + email

### Wrappers dans `TiBillet/celery.py`

Ajouter après les wrappers existants :

```python
@app.task
def cron_cloture_quotidienne():
    logger.info(f"call_command generer_cloture --niveau=J START")
    call_command("generer_cloture", "--niveau=J")
    logger.info(f"call_command generer_cloture --niveau=J END")


@app.task
def cron_cloture_hebdomadaire():
    logger.info(f"call_command generer_cloture --niveau=H START")
    call_command("generer_cloture", "--niveau=H")
    logger.info(f"call_command generer_cloture --niveau=H END")


@app.task
def cron_cloture_mensuelle():
    logger.info(f"call_command generer_cloture --niveau=M START")
    call_command("generer_cloture", "--niveau=M")
    logger.info(f"call_command generer_cloture --niveau=M END")


@app.task
def cron_cloture_annuelle():
    logger.info(f"call_command generer_cloture --niveau=A START")
    call_command("generer_cloture", "--niveau=A")
    logger.info(f"call_command generer_cloture --niveau=A END")
```

Et dans `setup_periodic_tasks()` :

```python
    # Clotures comptables periodiques (cf. comptabilite/tasks.py)
    # / Periodic accounting closures
    logger.info(f"setup_periodic_tasks cron_cloture_quotidienne at 6:00 UTC")
    sender.add_periodic_task(
        crontab(hour=6, minute=0),
        cron_cloture_quotidienne.s(),
        name="cron_cloture_quotidienne",
    )
    sender.add_periodic_task(
        crontab(day_of_week=1, hour=6, minute=15),
        cron_cloture_hebdomadaire.s(),
        name="cron_cloture_hebdomadaire",
    )
    sender.add_periodic_task(
        crontab(day_of_month=1, hour=6, minute=30),
        cron_cloture_mensuelle.s(),
        name="cron_cloture_mensuelle",
    )
    sender.add_periodic_task(
        crontab(month_of_year=1, day_of_month=1, hour=6, minute=45),
        cron_cloture_annuelle.s(),
        name="cron_cloture_annuelle",
    )
```

### Tâche `envoyer_email_cloture` dans `comptabilite/tasks.py`

```python
@shared_task
def envoyer_email_cloture(schema_name, cloture_uuid):
    """
    Envoie un email de cloture aux destinataires configures dans
    Configuration.rapport_emails, avec le PDF en piece jointe.
    Active uniquement si Configuration.rapport_periodicite matche le niveau.
    / Send a closure email to recipients configured in Configuration.rapport_emails,
    with PDF attached. Active only if Configuration.rapport_periodicite matches niveau.
    """
    from Customers.models import Client
    tenant = Client.objects.get(schema_name=schema_name)

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        from comptabilite.pdf import generer_pdf_cloture
        from BaseBillet.models import Configuration
        from BaseBillet.tasks import CeleryMailerClass

        try:
            cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        except ClotureCaisse.DoesNotExist:
            logger.warning(f"[{schema_name}] Cloture {cloture_uuid} introuvable, skip email.")
            return False

        config = Configuration.get_solo()

        # Verifications : emails configures + periodicite matche le niveau
        # / Checks: emails configured + periodicity matches niveau
        if not config.rapport_emails or not config.rapport_emails.strip():
            return False
        if config.rapport_periodicite != cloture.niveau:
            return False

        # Liste d'emails (separateur virgule, on trim chaque entree)
        # / Email list (comma-separated, trim each)
        emails = [e.strip() for e in config.rapport_emails.split(",") if e.strip()]
        if not emails:
            return False

        # Genere le PDF en piece jointe
        # / Generate PDF as attachment
        pdf_bytes, pdf_filename, _ = generer_pdf_cloture(cloture)

        # Sujet et corps de l'email
        # / Email subject + body
        subject = f"[{config.organisation}] Cloture {cloture.get_niveau_display()} #{cloture.numero_sequentiel}"
        context = {
            "config": config,
            "cloture": cloture,
        }

        mailer = CeleryMailerClass(
            email=emails,
            title=subject,
            template="comptabilite/email/cloture_rapport_email.html",
            context=context,
            attached_files={pdf_filename: pdf_bytes},
        )
        return mailer.send()
```

### Template email

`comptabilite/templates/comptabilite/email/cloture_rapport_email.html` (HTML simple) :

```html
{% load i18n %}<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; color: #222; max-width: 600px; margin: auto;">
    <h1 style="font-size: 18pt;">{% blocktrans with org=config.organisation %}{{ org }} — Closure report{% endblocktrans %}</h1>
    <p>
        {% blocktrans with niveau=cloture.get_niveau_display num=cloture.numero_sequentiel %}
        Periodic accounting closure: {{ niveau }} #{{ num }}.
        {% endblocktrans %}
    </p>
    <p>
        <strong>{% translate "Period" %}:</strong> {{ cloture.datetime_debut|date:"d/m/Y H:i" }} → {{ cloture.datetime_fin|date:"d/m/Y H:i" }}<br>
        <strong>{% translate "Transactions" %}:</strong> {{ cloture.nombre_transactions }}<br>
        <strong>{% translate "Total TTC" %}:</strong> {{ cloture.total_general|floatformat:0 }}c
    </p>
    <p>{% translate "Full report attached as PDF." %}</p>
    <hr>
    <p style="font-size: 8pt; color: #888;">
        {% translate "Sent automatically by the accounting module. Reply to update your preferences." %}
    </p>
</body>
</html>
```

### Intégration dans `generer_cloture_pour_tenant`

Après création de la `ClotureCaisse`, déclencher l'email **async** :

```python
# Email automatique si periodicite configurée
# / Auto email if periodicity is configured
if config.rapport_periodicite == niveau and config.rapport_emails:
    envoyer_email_cloture.delay(schema_name, str(cloture.uuid))
```

### Tests

```python
def test_cron_cloture_quotidienne_appelle_command(mocker):
    """Le wrapper @app.task appelle bien generer_cloture --niveau=J."""
    from TiBillet.celery import cron_cloture_quotidienne
    mock_call = mocker.patch("TiBillet.celery.call_command")
    cron_cloture_quotidienne()
    mock_call.assert_called_with("generer_cloture", "--niveau=J")


def test_envoyer_email_cloture_skip_si_pas_de_config(tenant_lespass):
    """Sans rapport_emails ou rapport_periodicite mismatch, l'email est skip."""
    # ... (mock CeleryMailerClass, vérifier que .send() n'est PAS appelé)


def test_envoyer_email_cloture_envoie_si_config_ok(tenant_lespass, mocker):
    """Avec rapport_emails configuré ET periodicite matchante, l'email est envoyé."""
    # ... (mock CeleryMailerClass.send, vérifier qu'il est appelé avec le PDF en attachement)
```

---

## Vérifications finales (sortie B4)

```bash
# Tests comptabilite complets
API_KEY=$(docker exec lespass_django poetry run python /DjangoFiles/manage.py test_api_key 2>/dev/null | tail -1) && docker exec -e "API_KEY=$API_KEY" lespass_django bash -c "cd /DjangoFiles && /home/tibillet/.cache/pypoetry/virtualenvs/lespass-LcPHtxiF-py3.11/bin/pytest tests/pytest/test_comptabilite_*.py -v"

# Check + migrations
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
```

## Pièges anticipés

1. **Data migration cross-schema** : la migration 0002 doit retourner si `connection.schema_name == "public"` (modèles TENANT_APP). Cf. djc.md §multi-tenancy.
2. **Encodage CP1252 pour EBP** : caractères non encodables remplacés par `?` (acceptable).
3. **`CeleryMailerClass.attached_files`** : dict `{filename: bytes}`. Le type MIME est hardcodé en `application/pdf` ligne 122 de `BaseBillet/tasks.py` — c'est ce qu'on veut pour le rapport PDF.
4. **`Configuration.rapport_emails` parsing** : séparateur `,` (espaces autour OK). Vérifier qu'aucun email vide n'est passé à `mailer.email`.
5. **Tests Celery beat** : utiliser `mocker.patch` (pytest-mock) — déjà dispo dans le projet.
6. **HTMX dans `change_form_before.html`** : Unfold inclut son propre HTMX. Vérifier avant d'ajouter un `<script>` duplicate.
7. **`MappingMoyenDePaiement` `unique=True` sur payment_method** : protège contre les doublons mais empêche la migration de seed si la valeur existe déjà. Utiliser `get_or_create` dans la data migration.
8. **Sidebar position** : insérer les 2 nouvelles entrées APRÈS « Entries » dans la section *Sales & accounting*, en remplaçant les commentaires TODO V2 existants dans `dashboard.py`.

## Estimation

- B1 (modèles + migration + admin) : ~45 min
- B2 (profils + CSV comptable) : ~50 min
- B3 (vue + form HTMX) : ~30 min
- B4 (Celery + email) : ~40 min

**Total : ~2h45** (hors validation maintaineur).

## Commit final suggéré (B4)

```
feat(comptabilite): S5 — Celery beat + email + comptes paramétrables + 3 profils CSV

- comptabilite/models.py : +CompteComptable, +MappingMoyenDePaiement
- migrations/0002 : data migration seed PCG français (9 comptes + 13 mappings)
- comptabilite/admin.py : 2 nouveaux ModelAdmin + URL `exporter-csv-comptable/`
- comptabilite/profils_csv.py : 3 profils (Sage 50, EBP, Paheko)
- comptabilite/csv_comptable.py : ventilation comptable + génération CSV par profil
- comptabilite/tasks.py : envoyer_email_cloture (PDF en pièce jointe via CeleryMailerClass)
- comptabilite/templates/comptabilite/admin/export_csv_comptable_form.html
- comptabilite/templates/comptabilite/email/cloture_rapport_email.html
- TiBillet/celery.py : 4 wrappers cron_cloture_J/H/M/A + add_periodic_task
- Administration/admin/dashboard.py : +2 sidebar entries (Accounting accounts, Payment mapping)
- tests pytest : 8+ tests (modèles, 3 profils CSV, vue admin, email mock)

Référence : SPEC.md §2.4, §6.5, §7.
Plan : PLAN-S5-celery-csv-comptable.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```
