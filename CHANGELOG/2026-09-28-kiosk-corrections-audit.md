# kiosk : corrections après audit djc + hallmark / kiosk: fixes after djc + hallmark audit

**Date :** 2026-09-28
**Migration :** Non / No

## Résumé / Summary

**Quoi / What :** corrections issues de deux audits en lecture seule (djc : code, hallmark :
design) de la refonte `2026-09-28-kiosk-ecrans-maquette.md`.

**Pourquoi / Why :** le point le plus grave : la borne ne revenait jamais à l'accueil. Le client
suivant pouvait recharger la carte du précédent.

### Sécurité du parcours
- **Retour à l'accueil après 60 s sans geste** quand une carte est affichée (étapes solde,
  récapitulatif, erreur). Délai fixé dans `kiosk/views.py` (`DELAI_INACTIVITE_SECONDES`).
- Le minuteur de l'écran de refus est annulé dès qu'on change d'écran : « Réessayer » ne
  recharge plus la page en plein paiement.
- « Recommencer » et « Admin » sont masqués pendant le paiement au TPE.
- **Pause vérifiée côté serveur** (`la_recharge_est_active`) dans `check_request_card`,
  `recapitulatif` et `refill_with_wisepos`.
- La configuration ouverte par carte primaire **expire après 10 min** (horodatage en session).
- L'écran de refus ne dit « l'argent n'est pas parti » que si Stripe a confirmé l'annulation
  (`statut_certain`). Sinon, texte prudent et pas de « Réessayer ».
- Le consumer WebSocket **relit le contexte de l'écran final en base** : un worker Celery pas
  encore redémarré ne peut plus dégrader l'écran.
- Les erreurs techniques (Stripe, Fedow) ne sont plus montrées au public, seulement journalisées.
- `type_app` échappé (`escapejs`) ; montant en **euros entiers** de 1 à 99 999 € côté serveur (le pavé n'a plus de virgule, les centimes sont refusés) ; l'interrupteur
  envoie l'état voulu (un POST rejoué ne l'inverse plus).

### Lisibilité et accessibilité
- Solde et nouveau solde : dégradé texte `--grad-chaud-texte` (≥ 4,8:1, le jaune tombait à 1,9:1).
- Messages d'erreur : `--color-danger-text` (5,3:1) ; gris discret teinté `#6f6a65` (≥ 4,6:1).
- Interrupteur éteint lisible (contour), états pressé / occupé (`aria-busy`).
- Modales en `showModal()` : focus piégé, fond inerte, Échap ferme. Le simulateur DEMO se pose
  dans la modale ouverte pour rester cliquable.
- Focus déplacé sur la question après « Recharger » ; titres `h1` masqués aux étapes solde et
  récapitulatif ; plus de double annonce en erreur admin ; l'écran final est annoncé
  (swap `innerHTML` de `#tb-kiosque`).
- Bouton du récapitulatif « Payer X € » ; bouton « Valider · 5,50 € » avec deux décimales.
- Glyphes `←` / `⌫` remplacés par des SVG.

### Tailles d'écran
- 1024×600 : aucun écran du parcours ne défile ; configuration sur une rangée de 4 tuiles.
- Téléphones : plus de débordement horizontal. 1920×1080 : échelle agrandie.
- Écran TPE : tient en 1280×800.

## Fichiers / Files

| Fichier | Changement |
|---|---|
| `kiosk/views.py` | Helpers `la_recharge_est_active`, `contexte_des_modules`, session horodatée, gardes de pause, URLs via `reverse`, messages d'erreur publics |
| `kiosk/models.py` | `contexte_ecran_final` : `statut_certain` |
| `kiosk/validators.py` | `max_value`, erreurs de lecture journalisées |
| `wsocket/consumers.py` | `template()` relit le contexte en base |
| `kiosk/static/kiosk/css/tokens.css`, `kiosk.css` | Contrastes, états, responsive, jetons d'ombre |
| `kiosk/static/kiosk/js/main.js` | Inactivité, minuteur final, `showModal`, focus, `aria-busy` |
| `kiosk/static/kiosk/js/nfc.js` | Simulateur dans la modale ouverte, couleurs des jetons |
| `kiosk/templates/kiosk/…` | `etat_final.html`, `base.html`, partials (voir ci-dessus) |
| `tests/pytest/test_kiosk_ecrans.py` | Test de pause découpé + 13 nouveaux tests |

## Déploiement
- `collectstatic` ; **redémarrer le worker Celery** (le consumer compense, mais autant l'aligner).
- Nouveaux textes traduisibles : `makemessages` non lancé.

## Reste à trancher
- Repli DEMO sur le lecteur d'une autre borne : `status` / `cancel` en 404 (antérieur à la refonte).
- Phrases de position « au-dessus de l'écran » / « à droite de l'écran » : fixes ou par borne ?
