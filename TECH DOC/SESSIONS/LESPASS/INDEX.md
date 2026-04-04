# Lespass — Index des tâches

> Suivi simplifié de l'avancement. Le détail complet est dans [`PLAN_LESPASS.md`](PLAN_LESPASS.md).
> Les specs sont dans `specs/`.
>
> Dernière mise à jour : 2026-04-03 (sous-projet 1 terminé — 4 sessions)

---

## Sous-projet 1 — Bilan billetterie interne ✅

> **Design spec :** [`specs/2026-04-03-bilan-billetterie-design.md`](specs/2026-04-03-bilan-billetterie-design.md)

### Fait

- [x] **Session 01** — Migration `scanned_at` + `RapportBilletterieService` (8 méthodes) + 13 tests pytest
- [x] **Session 02** — Admin Unfold : page bilan, Chart.js natif, liens changelist/changeform + 3 tests
- [x] **Session 03** — Exports PDF (WeasyPrint) + CSV (`;` UTF-8 BOM) + 4 tests
- [x] **Session 04** — Polish UX (canvas vide, ligne total, hauteur chart), a11y (scope/caption), i18n (30+ traductions FR), edge cases

**Bilan :** 398 tests passent, 0 régression. 15 fichiers créés, 4 modifiés.

### Extension : Dashboard Billetterie

> **Design spec :** [`specs/2026-04-03-dashboard-billetterie-design.md`](specs/2026-04-03-dashboard-billetterie-design.md)

- [x] **Session 05** — Dashboard billetterie : page dédiée sidebar, cartes miniatures events, query annotée + cache 2min, 2 tests
- [x] **Session 06** — Exports par période (CSV/PDF/Excel) via formulaire HTMX sur dashboard + Excel sur bilan event

---

## Sous-projet 2 — Export SIBIL

> **Spec de référence :** [`../IDEAS/SIBIL_API_reference_TiBillet.md`](../../IDEAS/SIBIL_API_reference_TiBillet.md)
> **Statut :** exploré, à concevoir après sous-projet 1

- [ ] Brainstorming + design spec
- [ ] Sessions à définir

---

## Sous-projet 3 — Calculs fiscaux (CNM/ASTP/TVA)

> **Statut :** à concevoir après sous-projet 1

- [ ] Brainstorming + design spec
- [ ] Sessions à définir
