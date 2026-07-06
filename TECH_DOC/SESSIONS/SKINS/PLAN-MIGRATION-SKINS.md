# Migration Skins — unifier tout le templating public sous `pages/<skin>/`

> **Statut : PLAN (pas de code écrit).** Objectif : rendre la création de skin
> **facile pour tout le monde** — un seul dossier à connaître, des blocs clairement
> identifiés, un fallback de sécurité automatique.

---

## 0. TL;DR

Aujourd'hui il y a **deux systèmes de skin parallèles** (BaseBillet `get_skin_template`
avec socle `reunion` ; app pages `select_template` avec socle `classic`). On **unifie
tout sous l'app pages** :

- **Un seul endroit** : un skin = un dossier `pages/<skin>/`.
- **Un seul fallback** : si un gabarit manque dans le skin → on retombe sur
  `pages/classic/` (via `select_template`, comme le moteur de blocs).
- **Une frontière nette** : le skin possède la **mise en page** ; BaseBillet garde le
  **comportement** (modals, offcanvas, tunnels de paiement/réservation, filtres HTMX).
- **Tout ne déménage pas** : les pages fonctionnelles (compte, login, caisse) **restent
  dans BaseBillet** et héritent simplement du squelette du skin → elles adoptent le look
  sans copie par skin.

---

## 1. Objectif & principe directeur

**Créer un skin doit se résumer à :** copier `pages/classic/` → `pages/<mon-skin>/`,
restyler ce qu'on veut, laisser tomber le reste (fallback). **Zéro code Python.**

Principe : **le skin décrit À QUOI ÇA RESSEMBLE, jamais CE QUE ÇA FAIT.**
Le comportement (requêtes, formulaires, paiement, filtres, HTMX) reste côté BaseBillet.

---

## 2. État actuel (le point de départ)

### 2.1 Deux systèmes
| Système | Socle | Résolution | Où |
|---|---|---|---|
| BaseBillet (agenda, adhésions, compte…) | `reunion` | `get_skin_template(config, "views/…")` → `<skin>/views/…` sinon `reunion/…` | `BaseBillet/views.py:124` |
| App pages (pages de blocs) | `classic` | `select_template(["pages/<skin>/…", "pages/classic/…"])` | `pages/views.py:57` |

Le **même** champ `pages.ConfigurationSite.skin` pilote les deux (`get_skin_courant()`,
`BaseBillet/views.py:107`).

### 2.2 Inventaire du templating public BaseBillet
**Skin-aware aujourd'hui** (via `get_skin_template`) : `base.html`, `headless.html`,
`views/home.html`, `views/infos_pratiques.html`, `views/le_faire_festival.html`,
`views/event/list.html`, `views/event/retrieve.html`, `views/event/partial/list.html`,
`views/event/partial/list_append.html`, `views/membership/list.html`,
`views/federation/explorer.html`.

**Rendus `reunion/…` en dur** (fonctionnel, non skinné aujourd'hui) : `views/account/*`,
`views/login/*`, `views/qrcode_scan_pay/*`, `views/register.html`,
`views/event/wizard/*`, `views/event/formbricks.html`, `views/membership/{form,404,…}.html`.

### 2.3 Le vrai point dur : chrome et contenu sont **mélangés**
- `event/list.html` : SEO + `{% include carousel %}` + `{% include search %}` +
  **filtres tags HTMX** + `{% include partial/list.html %}`.
- `membership/list.html` : la grille **+ un `offcanvas #subscribePanel` embarqué**
  (le tunnel d'adhésion est DANS le template de contenu).
- `event/retrieve.html` : détail **+ tunnel de réservation**.

→ La migration = **extraire le chrome**, puis déplacer le contenu.

---

## 3. Architecture cible

### 3.1 Les 5 catégories de templates
| # | Catégorie | Exemple | Skinnable ? | Où (cible) |
|---|---|---|---|---|
| 1 | **Squelette** (shell) | `<html><head>…<body>` + slots | ✅ | `pages/<skin>/shell.html` |
| 2 | **Vues de contenu** | accueil, agenda, événement, adhésions, réseau | ✅ | `pages/<skin>/vues/*.html` |
| 3 | **Composants d'habillage** | navbar, footer, carte événement, carte adhésion | ✅ | `pages/<skin>/partials/*.html` |
| 4 | **Chrome interactif** | modals, offcanvas, tunnels, filtres HTMX | ❌ (comportement) | `BaseBillet/templates/chrome/*` |
| 5 | **Pages fonctionnelles** | compte, login, caisse, wizard, register | ❌ (restent) | `BaseBillet/…` (héritent du shell du skin) |

**Insight clé :** seules les catégories 1-2-3 migrent. La 4 est extraite vers un dossier
`chrome/` partagé. La 5 **ne bouge pas** — elle continue de faire `{% extends shell %}`,
donc elle prend le look du skin gratuitement (navbar/footer/CSS), sans copie par skin.

### 3.2 Arborescence cible
```
pages/templates/pages/
├── classic/                     ← SOCLE par défaut (fallback universel)
│   ├── shell.html               (ex base.html : head, CSS, slots)
│   ├── vues/
│   │   ├── accueil.html
│   │   ├── agenda.html
│   │   ├── evenement.html
│   │   ├── adhesions.html
│   │   ├── reseau.html          (federation explorer)
│   │   └── page.html            (page de blocs — existe déjà)
│   └── partials/
│       ├── navbar.html
│       ├── footer.html
│       ├── carte_evenement.html
│       ├── carte_adhesion.html
│       └── bloc_*.html          (moteur de blocs — existe déjà)
└── faire_festival/              ← SURCHARGE (uniquement ce qui diffère)
    ├── shell.html
    ├── vues/{accueil,agenda,evenement,adhesions}.html
    └── partials/{navbar,footer,carte_evenement,bloc_*}.html

BaseBillet/templates/chrome/     ← COMPORTEMENT partagé (non skinnable)
├── modals/
│   ├── connexion.html           (login offcanvas)
│   ├── contact.html             (contact offcanvas)
│   ├── adhesion_tunnel.html     (ex #subscribePanel)
│   └── reservation.html         (tunnel de réservation)
└── agenda/
    └── filtres.html             (recherche + tags HTMX — la LOGIQUE)
```

### 3.3 Le resolver unifié
Une **seule** fonction remplace `get_skin_template` pour tout le public :
```
pages.services.gabarit_skin(nom) -> select_template([
    f"pages/{skin}/{nom}",
    f"pages/classic/{nom}",
])
```
- `skin = get_skin_courant()` (inchangé).
- `select_template` gère le fallback natif Django → **c'est la sécurité demandée**.
- `skin = "reunion"` : `pages/reunion/` n'existe pas → tombe sur `pages/classic/`.
  (Donc **le contenu `reunion/views/*` actuel devient le socle `pages/classic/`.**)

---

## 4. LE CONTRAT DE SKIN (blocs bien identifiés) — le cœur du plan

C'est CE document qui rend le skinning accessible. Un skin = remplir/surcharger des
**blocs Django nommés**. Trois niveaux d'effort :
- **rien** → tout vient de `classic` (fallback) ;
- **surcharger un bloc** → petit tweak (`{% extends "pages/classic/…" %}` + override) ;
- **fichier complet** → redesign total.

### 4.1 Squelette — `pages/<skin>/shell.html`
```django
<!doctype html><html>
<head>
  {% block tete %}{# CSS du skin, meta, polices #}{% endblock %}
</head>
<body>
  {% block entete %}{% include "pages/<skin>/partials/navbar.html" %}{% endblock %}
  {% block main %}{# rempli par chaque vue #}{% endblock %}
  {% block pied %}{% include "pages/<skin>/partials/footer.html" %}{% endblock %}
  {% block modals %}{# chrome partagé, injecté par BaseBillet #}
    {% include "chrome/modals/connexion.html" %}
    {% include "chrome/modals/contact.html" %}
  {% endblock %}
</body></html>
```
| Bloc | Rôle |
|---|---|
| `tete` | CSS/polices/meta propres au skin |
| `entete` | navbar (habillage skin) |
| `main` | **le seul que chaque vue remplit** |
| `pied` | footer |
| `modals` | offcanvas/modals globaux (login, contact) — includes BaseBillet |

### 4.2 Vue Agenda — `pages/<skin>/vues/agenda.html`
`{% extends shell %}` puis remplit `main` avec des sous-blocs :
| Bloc | Contenu | Skinnable | Comportement |
|---|---|---|---|
| `agenda_entete` | titre + SEO | ✅ | — |
| `agenda_carrousel` | carrousel events | ✅ habillage | données en contexte |
| `agenda_filtres` | `{% include "chrome/agenda/filtres.html" %}` | zone, pas la logique | **BaseBillet** (HTMX) |
| `agenda_liste` | boucle → `{% block carte_evenement %}` | ✅ | — |
| `carte_evenement` | `{% include "pages/<skin>/partials/carte_evenement.html" %}` | ✅ | — |
| `agenda_pagination` | pagination | zone | **BaseBillet** (HTMX) |

### 4.3 Vue Événement (détail) — `pages/<skin>/vues/evenement.html`
| Bloc | Contenu | Comportement |
|---|---|---|
| `event_entete` | titre, date, lieu | — |
| `event_media` | image/vidéo | — |
| `event_description` | texte riche | — |
| `event_tarifs` | grille de prix (habillage) | données en contexte |
| `event_reservation` | `{% include "chrome/modals/reservation.html" %}` | **BaseBillet** (form + POST) |

### 4.4 Vue Adhésions — `pages/<skin>/vues/adhesions.html`
| Bloc | Contenu | Comportement |
|---|---|---|
| `adhesions_entete` | titre + intro | — |
| `adhesions_grille` | boucle → `{% block carte_adhesion %}` | — |
| `carte_adhesion` | `{% include partial carte_adhesion %}` | — |
| `adhesions_tunnel` | `{% include "chrome/modals/adhesion_tunnel.html" %}` | **BaseBillet** (ex #subscribePanel) |

### 4.5 Le contexte fourni (variables du contrat)
À documenter noir sur blanc pour chaque vue (les vues BaseBillet les fournissent) :
- **Agenda** : `dated_events`, `paginated_info`, `tags`, `thematiques`, `search`,
  `carrousel_event_list`.
- **Événement** : `event`, `prices`, formulaires de réservation.
- **Adhésions** : `products` (produits d'adhésion + tarifs).
- **Partout** : `config`, `base_template`/`shell`, `main_nav`, `skin_courant`.

---

## 5. Découpage chrome / contenu (récap décisionnel)

**Va dans le skin** (`pages/<skin>/`) : shell, navbar, footer, vues accueil/agenda/
événement/adhésions/réseau, carte événement, carte adhésion, carrousel (habillage).

**Reste dans BaseBillet** (`chrome/`, partagé) : login panel, contact panel, tunnel
d'adhésion (subscribePanel), tunnel de réservation, panier, **la logique** des filtres
tags/recherche/pagination (HTMX endpoints).

**Ne bouge pas** (BaseBillet, hérite du shell) : compte, login pages, caisse
(qrcode_scan_pay), wizard event, formbricks, register, emails.

---

## 6. Plan de migration par chantiers

> Ordre pensé pour **ne jamais casser le skin par défaut** (le plus utilisé).

- **CHANTIER-01 — Resolver + squelette.** Créer `gabarit_skin()`. Porter
  `reunion/base.html` → `pages/classic/shell.html` (+ FF). Faire pointer `base_template`
  dessus. *Sécurité : iso-rendu sur tous les tenants.*
- **CHANTIER-02 — Extraction du chrome.** Sortir modals/offcanvas/filtres des templates
  actuels vers `BaseBillet/templates/chrome/*`. *Zéro changement visible, testable seul.*
  **← le vrai point dur, à faire tôt.**
- **CHANTIER-03 — Agenda + détail événement.** Porter vers `pages/classic/vues/` +
  partials cartes + blocs identifiés. Brancher la vue sur `gabarit_skin`. Puis FF.
- **CHANTIER-04 — Adhésions.** Idem.
- **CHANTIER-05 — Accueil / infos / réseau.** Porter home, infos_pratiques,
  le_faire_festival, federation explorer.
- **CHANTIER-06 — Pages fonctionnelles.** Les faire `{% extends %}` le shell du skin
  (elles restent dans BaseBillet). Retirer les vieux `<skin>/views/*` de BaseBillet.
- **CHANTIER-07 — Doc + amorçage.** Écrire le « contrat de skin » (ce doc, affiné) +
  commande `demarrer_skin <nom>` (copie `pages/classic/` → `pages/<nom>/`).
- **CHANTIER-08 — Nettoyage.** Supprimer `get_skin_template` et l'arbo
  `BaseBillet/templates/{reunion,faire_festival}/` devenue vide.

---

## 7. Créer un skin en 5 minutes (la DX cible)
```bash
python manage.py demarrer_skin mon-skin      # copie pages/classic/ -> pages/mon-skin/
```
1. Édite `pages/mon-skin/shell.html` (CSS, polices, layout global).
2. Restyle `partials/navbar.html`, `footer.html`, `carte_evenement.html`.
3. Surcharge une vue si besoin (`vues/agenda.html`) — sinon supprime le fichier,
   ça retombe sur classic.
4. Active le skin : admin → *Configuration du site → Thème graphique = mon-skin*.
5. Tout le comportement (paiement, réservation, filtres, login) **marche déjà**.

---

## 8. Risques ouverts
- ⚠️ **Iso-rendu du socle** : porter `reunion/*` → `pages/classic/*` sans régression
  (skin par défaut). Tests Playwright agenda/adhésions/paiement obligatoires.
- ⚠️ **CHANTIER-02 (extraction chrome)** = 60-70 % de l'effort/risque. À faire proprement.

## 8bis. Décisions PRISES (verrouillées)
1. **Valeur du skin par défaut = `reunion`** (inchangée). `pages/reunion/` n'existe pas
   → fallback automatique sur `pages/classic/`. **Zéro migration de données** sur
   `ConfigurationSite.skin`. Le contenu `reunion/views/*` actuel devient le socle
   `pages/classic/`.
2. **Nommage des blocs = FIXE, documenté une fois** (CHANTIER-07). Une fois publié, on
   ne renomme plus un bloc ni une variable de contexte (sinon on casse les skins tiers).
   Le contrat est versionné.
3. **Chrome NON skinnable par template** (pas de slots d'habillage dans les modals/
   tunnels). Le chrome reste des **includes partagés monolithiques** dans BaseBillet.
   *Raison :* des slots alourdiraient le refacto (surface de contrat qui gonfle, risque
   de casser les flux paiement/réservation, couplage refacto↔API skin).
   **Échappatoire :** le chrome expose des **classes CSS sémantiques** ; un skin qui veut
   retoucher un modal le fait en **CSS global** depuis son `shell.html`, sans toucher aux
   templates. → décision réévaluable plus tard si un vrai besoin émerge, mais **hors de
   ce chantier**.

---

## 9. Compatibilité / rétro
- Pendant la migration, `get_skin_template` et `gabarit_skin` **coexistent** (chantier
  par chantier). Aucun big-bang.
- Fallback universel `pages/classic/` = filet de sécurité permanent (une page manquante
  n'affiche jamais une erreur, elle rend la version classic).
- Les skins tiers (une fois le contrat figé) survivent aux montées de version tant que
  les **noms de blocs** et le **contexte** ne changent pas → d'où l'importance de figer
  le contrat au CHANTIER-07 et de le versionner.
