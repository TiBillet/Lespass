# v1.7.7 — Unification actions admin Membership dans MembershipMVT

**Date :** Mars 2026
**Migration :** Non

---

### Unification des actions admin sur les adhésions / Membership admin actions unified

**FR :**
Les actions admin sur les adhésions sont désormais centralisées dans `MembershipMVT` (viewset DRF),
exposées via HTMX dans un panneau inline affiché avant le formulaire admin.

- **Supprimé** : `actions_detail` / `actions_row` Unfold dans `MembershipAdmin` (5 méthodes `@action`)
- **Supprimé** : `has_custom_actions_row_permission`, `has_custom_actions_detail_permission`
- **Supprimé** : templates orphelins `cancel_confirm.html` et `ajouter_paiement.html`
- **Ajouté** : `change_form_before_template = "admin/membership/actions_panel.html"` sur `MembershipAdmin`
- **Ajouté** : 3 nouvelles actions dans `MembershipMVT` : `send_invoice`, `ajouter_paiement`, `cancel`
- **Ajouté** : `PaiementHorsLigneSerializer` dans `BaseBillet/validators.py`
- **Ajouté** : 4 nouveaux partials HTMX dans `admin/membership/partials/`

**EN :**
Admin actions on memberships are now centralised in `MembershipMVT` (DRF viewset),
exposed via HTMX in an inline panel displayed before the admin change form.

**Fichiers modifiés :**
- `BaseBillet/validators.py` : + `PaiementHorsLigneSerializer`
- `BaseBillet/views.py` : + imports `get_or_create_price_sold`, `dec_to_int`, `reverse`, `PaiementHorsLigneSerializer` + 3 actions + update `get_permissions`
- `Administration/admin_tenant.py` : - 5 `@action` Unfold + enrichissement `changeform_view` + `change_form_before_template`
- `Administration/templates/admin/membership/actions_panel.html` : Nouveau — panneau HTMX
- `Administration/templates/admin/membership/partials/send_invoice_success.html` : Nouveau
- `Administration/templates/admin/membership/partials/cancel_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_success.html` : Nouveau

---
