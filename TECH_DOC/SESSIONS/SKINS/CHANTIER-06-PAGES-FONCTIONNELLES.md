# CHANTIER-06 — Pages fonctionnelles hors des arbos de skin

**Statut :** en cours (2026-07-04).
**Objectif :** vider `BaseBillet/templates/{reunion,faire_festival}/` de tout ce
qui n'est PAS du skin : les pages fonctionnelles (catégorie 5 du plan — compte,
login, caisse qrcode, wizard, register, statuts de paiement) vont dans un
dossier neutre **`BaseBillet/templates/fonctionnel/`** (elles héritent déjà du
shell via `base_template` → elles prennent le look du skin gratuitement) ; les
partials d'HABILLAGE (navbar, footer — catégorie 3, skinnables) vont dans
`pages/<skin>/partials/` ; les emails mal rangés vont dans `emails/`.

## Mappings

### Habillage skinnable → `pages/<skin>/partials/`
| Source | Cible |
|---|---|
| `reunion/partials/navbar.html` | `pages/classic/partials/navbar.html` (avec son JS ?login=1) |
| `reunion/partials/footer.html` | `pages/classic/partials/footer.html` |
| `faire_festival/partials/navbar.html` | `pages/faire_festival/partials/navbar.html` |
| `faire_festival/partials/footer.html` | `pages/faire_festival/partials/footer.html` |
→ mise à jour des includes dans les shells/headless des deux skins + les vues
ff (agenda/evenement/adhesions… incluent le footer ff en dur) + volunteers.

### Fonctionnel → `BaseBillet/templates/fonctionnel/`
| Source (reunion/…) | Cible (fonctionnel/…) |
|---|---|
| `views/account/*` (+ `partials/account/*`) | `compte/*` (+ `compte/partials/*`) |
| `views/login/*` | `connexion/*` |
| `views/qrcode_scan_pay/*` (SAUF email/) | `qrcode_scan_pay/*` |
| `views/register.html` | `register.html` |
| `views/event/wizard/*` | `event_wizard/*` |
| `views/event/formbricks.html`, `reservation_ok.html` | `event/…` |
| `views/membership/formbricks.html`, `payment_*.html` | `adhesion/…` |
| `account_base.html`, `blank_base.html` | `fonctionnel/…` (racine) |
| `partials/field_errors.html`, `picture_url_string.html` | `commun/partials/…` (utilitaires partagés) |

### Emails → `BaseBillet/templates/emails/`
| Source | Cible |
|---|---|
| `reunion/views/qrcode_scan_pay/email/payment_success_{user,admin}.html` | `emails/qrcode_scan_pay/…` (+ maj `BaseBillet/tasks.py` ×2) |
| `reunion/views/tenant/emails/welcome_email.html` (legacy, non branché) | `emails/legacy/welcome_email.html` |

## Règles de sécurité
- Bascule de TOUTES les références (render(), includes, extends, tasks.py) par
  sed exhaustif DEPUIS LA RACINE (leçon lot B), contrôle `rg` à zéro ensuite.
- Les partiels HTMX restent des partiels (piège 9.8) — déplacement pur.
- Ids et attributs hx-* strictement inchangés.
- Statics `static/reunion/…` restants (qr-scanner, leaflet…) : PAS touchés ici
  (namespace static ≠ arbo templates ; hors périmètre du plan).

## Vérification
Snapshots publics 0 diff + pages compte/tirelire/login 200, puis tests complets
via agent Sonnet (groupés C5+C6), E2E complets.
