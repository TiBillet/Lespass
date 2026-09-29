# kiosk : nouveaux écrans d'après la maquette / kiosk: new screens from the mock-up

**Date :** 2026-09-28
**Migration :** Oui / Yes — `kiosk/migrations/0003_refonte_ecrans.py`
(`migrate_schemas`, tenant app)

## Résumé / Summary

**Quoi / What :** la borne reprend les écrans de la maquette
`TEMP-tibillet-kiosk-main/` (DA Tibillet v1 : Unbounded + Luciole, couleur du
lieu `--place`). Le parcours commence désormais par la carte :

1. posez votre carte (lecture NFC automatique) ;
2. solde de la carte, lu chez Fedow ; modale « carte non enregistrée » si la
   carte est anonyme ;
3. choix du montant : montants rapides + pavé numérique (décimales possibles) ;
4. récapitulatif : le nouveau solde est calculé par le serveur ;
5. paiement au TPE (inchangé : websocket + sondage de secours + Annuler) ;
6. succès avec le montant ajouté et le nouveau solde, puis écran « Merci ! »,
   puis retour à l'accueil. En cas de refus : bouton « Réessayer ».

Un **écran de configuration** (accueil opérateur) s'ouvre avec le bouton Admin
et une **carte primaire** (`laboutik.CartePrimaire`). On y coupe ou rallume la
recharge. Adhésion, Réservation et Caisse sont affichées « bientôt ». Quand la
recharge est coupée, la borne affiche « La borne est en pause. »

**Pourquoi / Why :** nouvelle maquette validée. On passe du « montant d'abord »
au « carte d'abord », pour montrer le solde avant de recharger.

**Retiré / Removed :** SweetAlert2, le mode nuit, les boutons additifs +1/+5…

## Fichiers / Files

| Fichier | Changement |
|---|---|
| `kiosk/models.py` | `PaymentsIntent.solde_avant_centimes`, `contexte_ecran_final()`. Nouveau modèle `ReglagesBorne` (OneToOne `laboutik.Terminal`) + `obtenir_reglages_de_la_borne()` |
| `kiosk/migrations/0003_refonte_ecrans.py` | Nouveau champ + nouveau modèle |
| `kiosk/carte.py` | **Nouveau.** `lire_la_carte_pour_la_borne()` : solde (jetons TLF + FED), carte enregistrée ou non, fin du numéro imprimé |
| `kiosk/validators.py` | Garde la carte lue (`carte_lue`), `RecapitulatifSerializer` |
| `kiosk/views.py` | `list` → `recharge.html` ; `check_request_card` → solde ; nouvelles actions `recapitulatif`, `acces_admin`, `configuration`, `basculer_module`, `demarrer` |
| `kiosk/tasks.py`, `wsocket/consumers.py` | L'écran final reçoit montant ajouté + nouveau solde (aussi au rejeu d'état) |
| `kiosk/templatetags/kiosk_tags.py` | **Nouveau.** Filtre `euros` (centimes → « 34,50 ») |
| `kiosk/admin.py`, `Administration/admin/dashboard.py` | Admin « Réglages des bornes » + entrée de menu |
| `kiosk/templates/kiosk/` | Nouveaux : `recharge.html`, `configuration.html`, `partial/etape_*.html`, `etat_final.html`, `modale_admin*.html`, `modules_borne.html`, `entete_parcours.html`, `marque_du_lieu.html`, `borne_en_pause.html`. Réécrits : `base.html`, `waiting_credit_card_terminal.html`, `success.html`, `cancel.html`. **Supprimés :** `select_amount.html`, `select_amount_content.html`, `sweet_scan_button.html`, `partial/topbar.html`, `partial/state_screen.html` |
| `kiosk/static/kiosk/css/tokens.css`, `kiosk.css` | Réécrits d'après `style.css` de la maquette (couches « AJUSTEMENTS » fusionnées) |
| `kiosk/static/kiosk/js/main.js` | Réécrit : lecture NFC par écran, pavé numérique, modales `<dialog>` |
| `tests/pytest/test_kiosk_flow.py` | Adapté au nouveau template |
| `tests/pytest/test_kiosk_ecrans.py` | **Nouveau.** 12 tests |

## Points d'attention / Caveats

- **`collectstatic` obligatoire** après déploiement (CSS, JS, police Unbounded
  lue depuis `V2/fonts/`).
- **Traductions :** nouveaux `{% translate %}` ajoutés, `makemessages` **non**
  lancé.
- Le nouveau solde affiché au succès est **annoncé** (solde avant + montant) :
  Fedow crédite par webhook, parfois quelques secondes après.
- Hors périmètre : historique de la carte, écran « carte retirée », bascule
  vers la caisse LaBoutik.
