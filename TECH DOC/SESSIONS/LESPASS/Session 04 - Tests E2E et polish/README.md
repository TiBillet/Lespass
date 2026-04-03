# Session 04 — Tests E2E + Polish

> **Chantier :** Bilan billetterie interne (sous-projet 1/3)
> **Spec :** `../specs/2026-04-03-bilan-billetterie-design.md`
> **Plan global :** `../plans/2026-04-03-bilan-billetterie-plan.md`
> **Dépend de :** Sessions 01, 02, 03 (tout le bilan doit être fonctionnel)
> **Produit :** Tests E2E Playwright + polish a11y/i18n + edge cases

---

## Objectif

Valider le bilan de bout en bout dans un navigateur réel. Vérifier l'accessibilité, l'internationalisation, et les cas limites (event vide, event futur, event passé sans scans).

---

## Contexte technique

### Tests E2E dans le projet

- Outil : Playwright Python (`pytest-playwright`)
- Dossier : `tests/e2e/`
- Conftest séparé : `tests/e2e/conftest.py` (fixtures navigateur)
- Prérequis : serveur Django actif via Traefik (`https://lespass.tibillet.localhost`)
- Les tests E2E ne font pas de ROLLBACK DB (pas de LiveServer éphémère avec django-tenants)

**Commande :**
```bash
docker exec lespass_django poetry run pytest tests/e2e/test_bilan_billetterie.py -v -s
```

### Pièges E2E connus

- `{% translate %}` change le texte → tester avec `'Bilan' in contenu or 'Report' in contenu`
- IDs avec `__` (double underscore) invalides en sélecteur CSS `#` → utiliser `[id="..."]`
- `DJANGO_SETTINGS_MODULE` redondant (déjà dans `pyproject.toml`)
- Utiliser `data-testid` (posés en Session 02) pour localiser les éléments

### data-testid posés en Session 02

```
bilan-synthese
bilan-ventes-tarif
bilan-moyens-paiement
bilan-canaux-vente
bilan-scans
bilan-codes-promo
bilan-link  (dans la changelist)
```

---

## Tâches

### 4.1 — Tests E2E Playwright

**Fichier :** `tests/e2e/test_bilan_billetterie.py`

```python
"""
Tests E2E du bilan de billetterie.
Verifie la navigation, l'affichage des sections, et les exports.
/ E2E tests for the ticketing report.

LOCALISATION : tests/e2e/test_bilan_billetterie.py

PREREQUIS :
- Serveur Django actif (Traefik)
- Au moins 1 event avec des reservations dans la DB
- Admin connecte

DEPENDENCIES :
- tests/e2e/conftest.py pour les fixtures navigateur
- Le bilan doit etre fonctionnel (Sessions 01-03)
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestBilanBilletterie:

    def test_navigation_changelist_vers_bilan(self, page: Page, admin_login):
        """
        Depuis la changelist events, cliquer sur le lien Bilan.
        La page bilan s'affiche avec la section synthese.
        / From events changelist, click Report link. Bilan page shows with synthese.
        """
        page.goto("/admin/basebillet/event/")
        page.wait_for_load_state("domcontentloaded")

        # Cliquer sur le premier lien bilan visible
        # / Click on the first visible report link
        bilan_link = page.locator("[data-testid='bilan-link']").first
        expect(bilan_link).to_be_visible()
        bilan_link.click()

        # Verifier qu'on est sur la page bilan
        # / Verify we're on the report page
        page.wait_for_url("**/bilan/")
        expect(page.locator("[data-testid='bilan-synthese']")).to_be_visible()

    def test_sections_presentes(self, page: Page, admin_login, url_bilan_event_avec_ventes):
        """
        La page bilan affiche toutes les sections attendues.
        / Report page displays all expected sections.
        """
        page.goto(url_bilan_event_avec_ventes)
        page.wait_for_load_state("domcontentloaded")

        # Sections toujours presentes
        # / Sections always present
        expect(page.locator("[data-testid='bilan-synthese']")).to_be_visible()
        expect(page.locator("[data-testid='bilan-ventes-tarif']")).to_be_visible()
        expect(page.locator("[data-testid='bilan-moyens-paiement']")).to_be_visible()

    def test_export_pdf_declenche_telechargement(self, page: Page, admin_login, url_bilan_event_avec_ventes):
        """
        Cliquer sur Export PDF declenche un telechargement.
        / Clicking Export PDF triggers a download.
        """
        page.goto(url_bilan_event_avec_ventes)
        page.wait_for_load_state("domcontentloaded")

        with page.expect_download() as download_info:
            page.locator("text=Export PDF").click()

        download = download_info.value
        assert download.suggested_filename.endswith(".pdf")

    def test_export_csv_declenche_telechargement(self, page: Page, admin_login, url_bilan_event_avec_ventes):
        """
        Cliquer sur Export CSV declenche un telechargement.
        / Clicking Export CSV triggers a download.
        """
        page.goto(url_bilan_event_avec_ventes)
        page.wait_for_load_state("domcontentloaded")

        with page.expect_download() as download_info:
            page.locator("text=Export CSV").click()

        download = download_info.value
        assert download.suggested_filename.endswith(".csv")

    def test_bilan_event_sans_donnees(self, page: Page, admin_login, url_bilan_event_vide):
        """
        La page bilan s'affiche meme pour un event sans ventes.
        Un message "Aucune donnee" ou equivalent est visible.
        / Report page displays even for an event without sales.
        """
        page.goto(url_bilan_event_vide)
        page.wait_for_load_state("domcontentloaded")

        # La page se charge sans erreur
        # / Page loads without error
        expect(page.locator("[data-testid='bilan-synthese']")).to_be_visible()
```

Les fixtures `url_bilan_event_avec_ventes` et `url_bilan_event_vide` sont à créer dans `tests/e2e/conftest.py` — elles retournent l'URL complète vers la page bilan d'un event existant.

---

### 4.2 — Vérification a11y

**Fichiers :** modifier les templates partials créés en Session 02

**Checklist :**

- [ ] `aria-label` sur chaque section/carte : `aria-label="{% translate 'Synthèse du bilan' %}"`
- [ ] `aria-live="polite"` inutile ici (pas de contenu dynamique HTMX sur cette page)
- [ ] `aria-hidden="true"` sur toutes les icônes décoratives (`<span class="material-symbols-outlined">`)
- [ ] `visually-hidden` pour les données visuelles uniquement (progress bar → texte caché "84,6 %")
- [ ] Tableaux : `<th scope="col">` sur les en-têtes de colonnes
- [ ] Tableaux : `<caption class="visually-hidden">` pour chaque tableau
- [ ] Contraste texte : vérifier que les inline styles respectent un ratio 4.5:1 minimum

---

### 4.3 — Vérification i18n

**Fichiers :** tous les templates + `BaseBillet/reports.py`

**Checklist :**

- [ ] Tous les textes visibles dans les templates utilisent `{% translate %}` ou `{% blocktrans %}`
- [ ] Les labels du service (noms de sections, en-têtes CSV) utilisent `_()` ou sont des données de la DB (pas à traduire)
- [ ] Lancer `makemessages` pour extraire les chaînes :
  ```bash
  docker exec lespass_django poetry run django-admin makemessages -l fr
  docker exec lespass_django poetry run django-admin makemessages -l en
  ```
- [ ] Remplir les `msgstr` manquants dans `locale/fr/LC_MESSAGES/django.po`
- [ ] Supprimer les flags `#, fuzzy`
- [ ] Compiler :
  ```bash
  docker exec lespass_django poetry run django-admin compilemessages
  ```

---

### 4.4 — Edge cases

**Fichier :** `tests/pytest/test_rapport_billetterie_service.py` (ajouter des tests)

```python
def test_synthese_event_jauge_zero(self, event_jauge_zero):
    """
    Un event avec jauge_max=0 ne provoque pas de division par zero.
    / An event with jauge_max=0 doesn't cause division by zero.
    """
    service = RapportBilletterieService(event_jauge_zero)
    synthese = service.calculer_synthese()
    assert synthese["taux_remplissage"] == 0.0

def test_courbe_ventes_event_vide(self, event_without_sales):
    """
    La courbe de ventes d'un event vide retourne des listes vides.
    / Sales curve for an empty event returns empty lists.
    """
    service = RapportBilletterieService(event_without_sales)
    courbe = service.calculer_courbe_ventes()
    assert courbe["labels"] == []
    assert courbe["datasets"][0]["data"] == []

def test_scans_sans_scanned_at(self, event_with_old_scans):
    """
    Des tickets scannes avant la migration (scanned_at=None)
    retournent tranches_horaires=None.
    / Tickets scanned before migration return tranches_horaires=None.
    """
    service = RapportBilletterieService(event_with_old_scans)
    scans = service.calculer_scans()
    assert scans["scannes"] > 0
    assert scans["tranches_horaires"] is None

def test_remboursements_event_sans_remboursement(self, event_without_sales):
    """
    Pas de remboursements = nombre 0, taux 0.
    / No refunds = count 0, rate 0.
    """
    service = RapportBilletterieService(event_without_sales)
    remb = service.calculer_remboursements()
    assert remb["nombre"] == 0
    assert remb["montant_total"] == 0
    assert remb["taux"] == 0.0
```

---

## Vérification finale

```bash
# Tests du service (y compris les edge cases ajoutés)
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_billetterie_service.py -v

# Tests admin
docker exec lespass_django poetry run pytest tests/pytest/test_bilan_admin_views.py -v

# Tests exports
docker exec lespass_django poetry run pytest tests/pytest/test_bilan_exports.py -v

# Tests E2E (serveur actif requis)
docker exec lespass_django poetry run pytest tests/e2e/test_bilan_billetterie.py -v -s

# Suite complète — 0 régression
docker exec lespass_django poetry run pytest tests/ -q
```

---

## Résultat attendu

- `tests/e2e/test_bilan_billetterie.py` : ~5 tests E2E
- ~4 tests edge cases ajoutés aux pytest
- Templates conformes a11y (aria-label, visually-hidden, th scope)
- i18n complet (makemessages + compilemessages)
- **Tous les tests passent : pytest + E2E, 0 régression**
- Le sous-projet 1 "Bilan billetterie interne" est **TERMINÉ**

---

## Après cette session

Mettre à jour :
- `TECH DOC/SESSIONS/LESPASS/INDEX.md` — cocher les 4 sessions
- `TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md` — statut "TERMINÉ" sur le sous-projet 1
- Mémoire Claude Code si pertinent

Prochain chantier : brainstorming du sous-projet 2 (Export SIBIL) ou du sous-projet 3 (Calculs fiscaux).
