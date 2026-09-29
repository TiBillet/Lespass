# Admin : bornes dans le module Kiosk, historique unique des tirages

## Ce qui a été fait

- Module Kiosk : entrée « Bornes » (proxy `kiosk.Borne` de `laboutik.Terminal`, rôle Kiosk forcé).
  Réglages de la borne en bloc dans la fiche. « Paiements » dans l'onglet Analyser.
- Module Tireuses : « Sessions » et « Historique cartes » retirés du menu, il reste
  « Historique des tirages ». « Kiosk dashboard » renommé « Écran public des tireuses ».
- Correctif : une session de tirage facturée ne se supprime plus depuis les historiques.
- Libellés : Réservations / Réservations de ressources / Clôtures de caisse (tickets Z) /
  Clôtures comptables / Réseaux de monnaie.

Détail des fichiers : `CHANGELOG/2026-09-29-admin-sidebar-kiosk-bornes-historique-tirages.md`.

## Tests à réaliser

### Test 1 : créer une borne depuis le module Kiosk
1. Activer le module Kiosk sur le lieu `lespass`.
2. Sidebar → Lémachines → Kiosk. Onglet Gérer : « Bornes ». Onglet Analyser : « Paiements ».
3. Bornes → Ajouter. Le champ « Type d'appareil » n'apparaît pas. Un bloc « Réglages de la borne » est présent.
4. Enregistrer. La colonne « État » affiche un code PIN.
5. Aller dans Terminaux matériels → Terminaux : la borne y est, type « Kiosk / self-service ».
6. Vérifier que le rail surligne bien « Kiosk » sur `/admin/kiosk/borne/`, et que le fil d'Ariane nomme Kiosk.

### Test 2 : appairer la borne
1. Taper le code PIN sur une borne (ou `/api/discovery/claim/`).
2. La colonne État passe à « Appairé ». Les actions « Révoquer » et « Nouveau code PIN » fonctionnent depuis la liste des bornes.

### Test 3 : historique des tirages
1. Activer le module Tireuses. Onglet Analyser : « Historique des tirages » et « Historique maintenance » seulement.
2. Chercher un UID de carte : on retrouve ses tirages.
3. Sélectionner une session facturée + une non facturée → Supprimer : seule la non facturée disparaît, un message prévient.
4. Les anciennes URL `/admin/controlvanne/rfidsession/` et `/admin/controlvanne/historiquecarte/` répondent toujours.

### Tests automatiques
```bash
poetry run pytest tests/pytest/test_admin_sidebar_kiosk_tireuses.py -v
```

## Compatibilité

- Migration proxy uniquement : aucune table, aucune donnée déplacée.
- Nouvelles chaînes à traduire en EN (makemessages non lancé).
