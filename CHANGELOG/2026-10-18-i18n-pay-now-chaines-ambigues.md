# Bouton « Pay now » en anglais sur le site français + chaînes courtes non traduites / "Pay now" shown in English on the French site + untranslated short strings

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Les boutons de paiement direct (réservation d'événement, adhésion sans texte de bouton personnalisé) utilisent le msgid français `"Payer maintenant"` (déjà traduit FR/EN) au lieu de `"Pay now"`. / The direct-payment buttons now use the French msgid "Payer maintenant" (already translated) instead of "Pay now".
- Skill `i18n-translate`, mode SYNC : les msgid de langue « ambiguë » (courts, sans mot-outil : « Pay now », « Download CSV », « Cost ») dont un msgstr est vide sont désormais envoyés aux agents, qui tranchent la langue. Une sortie identique au msgid est écrite quand même (msgstr == msgid) : l'item n'est plus renvoyé au run suivant. Toutes les commandes du skill passent par `docker exec lespass_django`, dossier de travail `var/i18n_translate` (ignoré par git). / SYNC mode now handles ambiguous-language msgids; identical outputs are written so they are not re-extracted; every command runs in the container.
- `.po` FR/EN : passe SYNC complète, en deux tours (801 puis 165 entrées, après le `makemessages`). / Full SYNC pass on the FR/EN .po files.

**Pourquoi / Why :** le `.po` FR avait `msgid "Pay now"` / `msgstr ""` : gettext retombait sur l'anglais. La détection SYNC classait ces chaînes courtes « ambiguës » et ne les traitait jamais (414 entrées FR concernées). / The FR .po had an empty msgstr for "Pay now", so gettext fell back to English; SYNC never handled such ambiguous short strings.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/commun/formulaires/reservation.html` | Bouton `booking-submit` : `{% translate "Payer maintenant" %}` |
| `BaseBillet/templates/commun/adhesion/form.html` | Bouton `membership-submit` (sans texte perso) : `{% translate 'Payer maintenant' %}` |
| `TECH_DOC/SKILLS/i18n-translate/scripts/extract_sync.py` | Items `amb` avec msgstr vide envoyés aux agents |
| `TECH_DOC/SKILLS/i18n-translate/scripts/apply_sync.py` | Compteur `dont_identiques_au_msgid` (sorties identiques au msgid, écrites) |
| `TECH_DOC/SKILLS/i18n-translate/references/workflow_sync.js` | Consigne explicite pour le cas `amb` |
| `TECH_DOC/SKILLS/i18n-translate/SKILL.md` | Documentation du cas `amb` ; toutes les commandes dans le conteneur (`<workdir>` / `<workdir_hote>`) |
| `locale/fr/LC_MESSAGES/django.po`, `locale/en/LC_MESSAGES/django.po` | Traductions SYNC |

---

## Comment tester (a la main) / Manual test
Prérequis : le mainteneur lance `compilemessages`.

### Test 1 — réservation d'événement
1. Site en français, connecté, panier vide, ouvrir un événement payant, ouvrir le panneau de réservation.
2. Le bouton de paiement direct affiche « Payer maintenant ».
3. Passer le site en anglais : « Pay now ».

### Test 2 — adhésion
1. Produit adhésion SANS texte de bouton personnalisé, connecté : le bouton affiche « Payer maintenant » (FR) / « Pay now » (EN).

### Test 3 — chaînes courtes de l'admin
1. Admin en français : vérifier quelques libellés auparavant en anglais (rapport de clôture : « Sales detail », « Cost », « Profit » ; export : « Download CSV »).
