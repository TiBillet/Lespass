# PLAN_LESPASS.md — Référence unifiée

> **Ce fichier est la source unique** pour le chantier Lespass (billetterie, rapports, conformité SIBIL).
> Équivalent de `PLAN_LABOUTIK.md` pour le module laboutik.
>
> Dernière mise à jour : 2026-04-03 (démarrage — design bilan billetterie validé)

---

## Sommaire

1. [Vision et périmètre](#1-vision-et-périmètre)
2. [Découpage en sous-projets](#2-découpage-en-sous-projets)
3. [Sous-projet 1 — Bilan billetterie interne](#3-sous-projet-1--bilan-billetterie-interne)
4. [Sous-projet 2 — Export SIBIL](#4-sous-projet-2--export-sibil)
5. [Sous-projet 3 — Calculs fiscaux](#5-sous-projet-3--calculs-fiscaux)
6. [Décisions architecturales](#6-décisions-architecturales)
7. [Règles de travail](#7-règles-de-travail)

---

## 1. Vision et périmètre

### Contexte

TiBillet/Lespass est un moteur de billetterie multi-tenant (django-tenants). La billetterie fonctionne — on vend des billets, on scanne des QR codes, on rembourse via Stripe. Mais il n'y a **aucun rapport de synthèse**. L'organisateur n'a pas de vue d'ensemble de ses ventes.

En parallèle, il y a une obligation légale (SIBIL) de déclarer trimestriellement les données de billetterie au Ministère de la Culture.

Le module laboutik (caisse/POS) a déjà 21 sessions de rapports comptables riches. Ce chantier vise à apporter le même niveau de qualité côté billetterie.

### Ce qu'on construit

Un système de rapports pour la billetterie, décomposé en 3 sous-projets indépendants :
1. Bilan interne pour l'organisateur (le socle)
2. Export SIBIL (consomme le socle)
3. Calculs fiscaux informatifs (consomme le socle)

### Ce qu'on ne construit pas

- Pas de dashboard public (tout est dans l'admin Unfold)
- Pas de rapport comptable (c'est le job de laboutik)
- Pas de temps réel WebSocket (reload classique)
- Pas d'agrégation multi-events dans un premier temps

---

## 2. Découpage en sous-projets

| # | Sous-projet | Dépend de | Statut |
|---|-------------|-----------|--------|
| 1 | **Bilan billetterie interne** | — | ⏳ Design validé |
| 2 | **Export SIBIL** | Sous-projet 1 (réutilise le service) | 📋 Exploré (spec SIBIL reconstituée) |
| 3 | **Calculs fiscaux** (CNM/ASTP/TVA) | Sous-projet 1 (réutilise les montants) | 📋 À concevoir |

Chaque sous-projet suit le cycle : spec → plan → sessions → tests.

Le sous-projet 1 est le socle. Le `RapportBilletterieService` sera réutilisé par les deux autres — le service SIBIL consommera les mêmes données (ventilation par tarif, recettes TTC) pour construire la déclaration trimestrielle.

---

## 3. Sous-projet 1 — Bilan billetterie interne

> **Design spec :** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-03-bilan-billetterie-design.md`

### Sessions prévues

| Session | Titre | Contenu | Dépend de |
|---------|-------|---------|-----------|
| **01** | Migration + service de calcul | `scanned_at` sur Ticket, `RapportBilletterieService` (8 méthodes), tests pytest | — |
| **02** | Admin Unfold — page bilan | `get_urls()`, template bilan, composants Unfold (cards, charts, progress bar), lien changelist/changeform | 01 |
| **03** | Exports PDF + CSV | WeasyPrint, CSV `;` UTF-8 BOM, boutons dans la page bilan | 02 |
| **04** | Tests E2E + polish | Tests Playwright, data-testid, a11y, i18n, edge cases (event vide, 0 scans) | 03 |

### Fichiers à créer / modifier

| Fichier | Session | Action |
|---|---|---|
| `BaseBillet/reports.py` | 01 | Créer — `RapportBilletterieService` |
| `BaseBillet/models.py` | 01 | Modifier — `scanned_at` sur Ticket |
| `BaseBillet/migrations/` | 01 | Créer — migration `scanned_at` |
| Code de scan | 01 | Modifier — `scanned_at = timezone.now()` |
| `Administration/admin/events.py` | 02 | Modifier — `get_urls()`, colonne, template before |
| `Administration/templates/admin/event/bilan*.html` | 02 | Créer — page + partials (8 fichiers) |
| `Administration/templates/admin/event/bilan_pdf.html` | 03 | Créer — template PDF |
| `tests/pytest/test_rapport_billetterie*.py` | 01 | Créer — tests service |
| `tests/pytest/test_bilan_admin*.py` | 02 | Créer — tests vues admin |
| `tests/e2e/test_bilan_billetterie.py` | 04 | Créer — tests E2E |

---

## 4. Sous-projet 2 — Export SIBIL

> **Spec de référence :** `TECH DOC/IDEAS/SIBIL_API_reference_TiBillet.md`
> **Exploration :** `TECH DOC/IDEAS/exploration-bilan-billetterie.md`
> **À concevoir** — brainstorming dédié après le sous-projet 1.

### Ce qu'on sait déjà

- SIBIL = obligation légale (loi LCAP 2016, décret 2017)
- Déclaration trimestrielle (avant le 10 du 1er mois du trimestre suivant)
- API REST JWT ou CSV — la spec complète (`SIBIL-SFD-002 v2.4`) est à demander à `sibil.dgca@culture.gouv.fr`
- 4 sections par déclaration : Description, Lieu, Date, Billetterie
- Mapping TiBillet → SIBIL : tarifs réduits dans "plein tarif", adhésions dans "abonnements"
- Modèle `SibilDeclaration` à créer (FK→Event)

### Ce qui reste à explorer

- Obtenir la spec officielle SIBIL-SFD-002 v2.4
- Accès sandbox de test SIBIL
- Décider : API REST ou CSV d'abord ?
- Mapping exact des catégories Event TiBillet → domaines SIBIL
- Gestion des séries de représentations (Event avec parent)

---

## 5. Sous-projet 3 — Calculs fiscaux

> **À concevoir** — brainstorming dédié.

### Ce qu'on sait déjà

- Taxe spectacles variétés (CNM) : 3,5% de la recette HT billetterie
- Taxe spectacles dramatiques (ASTP) : 3,5% aussi, autre organisme
- TVA spectacle : 5,5% (ou 2,1% pour les 140 premières représentations)
- Droits SACEM/SACD : obligation séparée
- Seuil d'exonération CNM : 80€/an cumulé

### Rôle dans le bilan

Affichage **informatif** dans la page bilan — pas de déclaration automatique. L'organisateur voit "Taxe CNM estimée : 134,50 €" et sait ce qu'il doit déclarer. C'est un helper, pas un outil de conformité.

---

## 6. Décisions architecturales

| # | Décision | Justification |
|---|----------|---------------|
| 1 | `RapportBilletterieService` dans `BaseBillet/reports.py` | Même pattern que `laboutik/reports.py` — méthodes qui retournent des dicts |
| 2 | Source principale : `LigneArticle` filtrées par `reservation__event` | C'est là que sont les montants, moyens de paiement, canaux |
| 3 | `Ticket` en complément pour les scans | Status K/S/R + nouveau `scanned_at` |
| 4 | Admin Unfold : page dédiée via `get_urls()` | Plus d'espace qu'une `TableSection`, permet les exports |
| 5 | Pas de snapshot — calcul temps réel | Les données d'un event terminé ne bougent plus |
| 6 | Graphiques natifs Unfold (Chart.js inclus) | Line chart ventes, bar chart affluence, progress bar jauge |
| 7 | `scanned_at` nullable | Migration simple, rétrocompatible (anciens scans = None) |

---

## 7. Règles de travail

Mêmes règles que le chantier laboutik (cf. `PLAN_LABOUTIK.md` section 14) :

- **1 session = 1 livrable testable.** Ne jamais enchaîner 2 sessions.
- **Règle des 3 fichiers** : max 3 fichiers modifiés avant de lancer check + tests.
- **Anti-hallucination** : toujours Read avant Edit, vérifier les API Django si doute.
- **Anti-sur-ingénierie** : si le plan ne le mentionne pas, ne pas le faire.
- **S'arrêter et demander** : avant de toucher `settings.py`, `urls.py`, `PaiementStripe`, `AuthBillet`, JS, ou ajouter une dépendance.
- **FALC** : code verbeux, commentaires bilingues FR/EN, noms explicites.
- **Tests** : lancer pytest après chaque session.
