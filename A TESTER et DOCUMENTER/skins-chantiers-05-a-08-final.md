# Migration skins — CHANTIERS 05 à 08 : fin de la migration

## Ce qui a été fait
Voir le CHANGELOG (entrée « CHANTIERS-05→08 ») et les specs
`TECH_DOC/SESSIONS/SKINS/CHANTIER-0{5,6}-*.md` + `CHANTIER-07-08-*.md`.
En résumé : plus une seule vue publique résolue hors de
`pages/<skin>/ → pages/classic/` ; le fonctionnel vit dans
`BaseBillet/templates/fonctionnel/` et hérite du shell ; le contrat de skin
est publié (`CONTRAT-DE-SKIN.md` v1.0) avec la commande `demarrer_skin` ;
les arborescences `reunion/` et `faire_festival/` de BaseBillet ont disparu.

## Tests à réaliser à la main (mainteneur)

### Parcours public (déjà validés par snapshots + E2E + Chrome, à re-survoler)
1. lespass (reunion) : home, agenda (+recherche, tags), détail événement +
   réservation Stripe 4242, adhésions + tunnel Stripe, /federation/, pages CMS.
2. chantefrein (faire_festival) : mêmes parcours + /infos-pratiques/ +
   /le-faire-festival/ + les embeds (/event/embed/, /memberships/embed/).

### Parcours FONCTIONNELS (templates déplacés vers fonctionnel/ — zone la moins
couverte par les E2E, à tester en priorité)
1. **Compte** : /my_account/ connecté — index, tirelire (recharge en ligne),
   réservations (ouvrir un billet via #ticketPanel), adhésions, carte TiBillet,
   préférences, badgeuse (punchclock si activée).
2. **Connexion** : déconnexion → connexion par email (lien magique →
   fonctionnel/connexion/confirmation), page fullpage /login si utilisée.
3. **Caisse QR** : initier un paiement (générateur), scanner (403 si non admin),
   payer par lien QR, fonds insuffisants (payer un montant > solde),
   confirmation. Vérifier l'email de confirmation (emails/qrcode_scan_pay/).
4. **Wizard événement** : « Ajouter un évènement » (staff) et « Proposer »
   (public) — les 10 gabarits sont dans fonctionnel/event_wizard/.
5. **Statuts de paiement adhésion** : rouvrir un lien de paiement déjà réglé /
   en attente / invalide (fonctionnel/adhesion/payment_*.html).
6. **Register** : le flux qui rend fonctionnel/register.html (invitation).
7. **404/500** : une URL inexistante rend la 404 avec navbar/footer du skin.

### Nouveau skin (contrat)
1. `python manage.py demarrer_skin test-skin` → dossier créé + instructions.
2. Supprimer le dossier après le test (les choices du champ skin ne changent pas).

## Points d'attention / assumés
- `static/reunion/…` et `static/faire_festival/…` existent toujours (statics
  spécifiques : qr-scanner, leaflet, media de démo, css/fonts ff) — seuls les
  TEMPLATES ont migré ; renommage des namespaces statics = décision future.
- Les emails qrcode ont changé de chemin dans `tasks.py` — tester un paiement
  QR réel et vérifier la réception des 2 mails (user + admin).
- La maquette statique ff est archivée dans
  `TECH_DOC/SESSIONS/SKINS/maquette-faire-festival/`.
