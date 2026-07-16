# Dashboard & menu admin : ordre, titres, cartes BETA, familles de menu, onglets Paramètres / Admin dashboard & menu: order, titles, BETA cards, menu families, Settings tabs

**Date :** 2026-07-15
**Migration :** **Non**

## Résumé / Summary

**Quoi / What :**
- **Dashboard — cartes** : les cartes de modules sont **réordonnées et renommées** (Site web personnalisé,
  Agenda et Billetterie, Adhésion abonnement et pass, Fédération et agenda participatif, Financement
  participatif & budgets contributifs, Caisse & Restaurant, Monnaies locales temps et cashless, Kiosk,
  Tireuses connectées). La carte **POS** est désormais **intégrée dans le flux ordonné** (6ᵉ) au lieu
  d'être rendue à part.
- **Inventaire** n'est plus un module activable : sa carte est retirée et la section menu « Inventaire »
  **suit la caisse** (`module_caisse`).
- Nouvelle section dashboard **« Outils externes »** : carte **Newsletter** + carte **Réseaux sociaux**
  (Postiz, grisée, « En cours de développement »).
- **Carte Newsletter** : texte d'invitation restauré (piloter sa newsletter à partir des évènements de
  l'agenda), complété par « Propulsée par un serveur Ghost ou par Brevo ».
- **Badge BETA** : encart « accès anticipé » (icône + texte d'appel aux retours) sur les cartes des
  modules marqués BETA (Caisse, Newsletter), repris dans la modal d'activation dont le bouton devient
  **« J'ai compris et je teste ! »**.
- **Bandeau d'accueil** : l'encart « Are you looking for a custom dashboard? » est recentré sur
  **documentation + contact** (« Besoin d'un coup de main ? »).
- **Menu latéral — nettoyage** : « Global information » → **« Configuration générale »** ; titres de
  sections alignés sur les noms des cartes ; **Formbricks retiré** du menu ; **Brevo déplacé** dans
  « Newsletter » ; **Clé API + Webhook** retirés du menu et regroupés en **onglets** sur la page
  « Paramètres » (via `UNFOLD["TABS"]`).
- **Menu latéral — familles** : les sections sont **regroupées par famille** (pilotage · vitrine &
  communication · billetterie & adhésions · point de vente · comptabilité · réseau). Le filet séparateur
  n'apparaît **qu'au début de chaque famille** : les sections d'une même famille apparaissent collées.

**Pourquoi / Why :** clarifier le tableau de bord (ordre logique, un couple carte/section homogène),
signaler honnêtement les modules en accès anticipé, et dégraisser/ranger la sidebar en centralisant la
configuration technique (clés API, webhooks) dans la page Paramètres et en groupant les sections par thème.

**Comment / How :** l'ordre et les libellés des cartes vivent dans `MODULE_FIELDS` (ordre des clés = ordre
d'affichage). `_build_modules_context` produit une liste unique où chaque carte porte un `type`
(`"pos"` / `"generic"`) lu par le gabarit ; `_build_external_cards_context` fournit la 2ᵉ grille.
Un flag `"beta": True` déclenche l'encart `BETA_NOTICE` (carte + modal). Les onglets Paramètres utilisent
la fonctionnalité Unfold `TABS` (regroupement de changelists de modèles **sans FK**). Le rangement du menu
en familles utilise un champ `_order` (X.Y : X = famille, Y = position) : une passe finale dans
`get_sidebar_navigation` trie les sections et recalcule les séparateurs (Unfold n'a pas de catégories
imbriquées natives).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `MODULE_FIELDS` réordonné/renommé + `BETA_NOTICE` ; `_build_modules_context` (POS intégrée, `type`, `beta`) ; `_build_external_cards_context` (nouveau) ; `_build_pos_card_context` (+beta) ; `dashboard_callback` (external_cards) ; `get_sidebar_navigation` (renommages, Inventaire→caisse, Brevo→Newsletter, section External tools supprimée, familles via `_order` + passe de tri/séparateurs) |
| `Administration/admin_tenant.py` | `module_toggle_modal` passe `is_beta` + `BETA_NOTICE` à la modal ; import `BETA_NOTICE` |
| `Administration/templates/admin/dashboard.html` | Boucle unique (POS + générique), grille « Outils externes », carte « coming_soon » |
| `Administration/templates/admin/partials/dashboard_module_card.html` | Nouveau : carte module générique réutilisable |
| `Administration/templates/admin/partials/dashboard_beta_notice.html` | Nouveau : encart BETA partagé (carte + modal) |
| `Administration/templates/admin/dashboard_module_modal.html` | Encart BETA à l'activation + bouton « J'ai compris et je teste ! » |
| `Administration/templates/admin/service.html` | Bandeau d'accueil recentré doc + contact |
| `TiBillet/settings.py` | `UNFOLD["TABS"]` : onglets Paramètres / Clés API / Webhooks |

### Migration
- **Migration nécessaire / Migration required :** Non *(le champ `module_inventaire` du modèle est conservé, simplement plus utilisé pour l'affichage)*

### i18n
- Cette refonte ajoute ~18 chaînes traduisibles neuves (msgid en FR). **Workflow i18n à lancer** par le
  mainteneur (`makemessages`). Non lancé côté assistant.

---

## Comment tester (à la main) / Manual test

### Test 1 — Ordre et titres des cartes du dashboard
1. Se connecter à l'admin (`admin@admin.com`), aller sur `/admin/` (Dashboard).
2. Vérifier l'ordre de la grille **« Modules »** : Site web personnalisé, Agenda et Billetterie, Adhésion
   abonnement et pass, Fédération et agenda participatif, Financement participatif & budgets contributifs,
   **Caisse & Restaurant** (carte POS, au milieu), Monnaies locales temps et cashless, Kiosk : borne
   libre-service, Tireuses connectées.
3. Vérifier qu'il n'y a **plus de carte « Inventaire »**.

### Test 2 — Section « Outils externes »
1. Sous la grille Modules, un titre **« Outils externes »**.
2. Carte **Newsletter** : texte d'invitation (piloter sa newsletter depuis les évènements de l'agenda) +
   « Propulsée par un serveur Ghost ou par Brevo », avec interrupteur.
3. Carte **Réseaux sociaux** grisée, badge **« En cours de développement »** (Postiz), sans interrupteur.

### Test 3 — Badge BETA (carte + modal)
1. Sur les cartes **Caisse & Restaurant** et **Newsletter** : encart « accès anticipé » (icône fiole + texte
   d'appel aux retours).
2. Cliquer l'interrupteur d'un module BETA **inactif** (ex. Newsletter) → la **modal** affiche l'encart BETA
   et le bouton devient **« J'ai compris et je teste ! »**.
3. Sur un module **non BETA** (ex. Site web) → modal normale, bouton **« Confirm »**.
4. À la **désactivation** d'un module BETA → pas d'encart, bouton normal.

### Test 4 — Bandeau d'accueil
1. En haut du dashboard, le bandeau titre **« Besoin d'un coup de main ? »** (plus de « custom dashboard »).
2. Deux boutons : **Contacter l'équipe** (mailto) + **Lire la documentation** (lien doc).

### Test 5 — Menu latéral : renommages + Inventaire
1. La 1ʳᵉ section du menu s'appelle **« Configuration générale »**.
2. Chaque section liée à un module porte **le même nom que sa carte**.
3. Section **« Inventaire »** : visible **dès que Caisse & Restaurant est activée**.

### Test 6 — Menu latéral : Outils externes démantelés
1. **Formbricks** n'apparaît **plus** dans le menu.
2. **Brevo** apparaît dans la section **« Newsletter »** (à côté de « Serveur Ghost »), module Newsletter actif.
3. **Clé API** et **Webhook** n'apparaissent **plus** comme entrées de menu.

### Test 7 — Onglets de la page Paramètres (UNFOLD TABS)
1. Ouvrir **Configuration générale → Paramètres**.
2. Vérifier la **barre d'onglets** : **Paramètres** / **Clés API** / **Webhooks**, et la navigation entre eux.
3. ⚠️ **À confirmer visuellement** : la page Paramètres est un **singleton** (django-solo) dont le changelist
   redirige vers le formulaire. Vérifier que la barre d'onglets s'affiche bien **sur le formulaire** de
   Configuration (pas seulement sur les changelists Clés API / Webhooks).

### Test 8 — Menu rangé en familles
1. Activer plusieurs modules et observer les **filets séparateurs** : ils n'apparaissent qu'**au début de
   chaque famille**. Les sections d'une même famille (ex. Caisse + Inventaire + Monnaies + Kiosk + Tireuses +
   Terminaux) sont **collées** sans filet entre elles.
2. Ordre attendu des familles : Configuration générale · [Site web · Fédération · Newsletter] · [Agenda et
   Billetterie · Adhésions · Financement] · [Caisse · Inventaire · Monnaies · Kiosk · Tireuses · Terminaux] ·
   Ventes & comptabilité · Root.

### Vérifs automatiques déjà faites
- `pytest tests/pytest/test_module_newsletter_activation.py` → **5 passed**.
- Rendu du template `admin/dashboard.html` dans un contexte tenant → OK (9 cartes ordonnées, section Outils
  externes, encart BETA).
- Simulation `get_sidebar_navigation` tous modules actifs → familles correctes, aucun `_order` résiduel.

## Compatibilité
- Aucune migration. Le champ modèle `module_inventaire` est **conservé** (plus utilisé pour l'affichage).
- Le `ModelAdmin` Formbricks reste **enregistré** (accessible par URL directe) : seul l'item de menu est retiré.
- Le champ `_order` posé sur les sections de menu est **retiré avant le rendu** (Unfold ne le voit jamais).
