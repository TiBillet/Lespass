# TODO — Spécifications futures, en attente

> Dossier hub des features **non commencées** mais déjà spécifiées.
> Chaque fichier = 1 future session, avec contexte, motivation, design.
>
> Convention : `<DOMAINE>-<slug-court>.md` (ex: `COMPTABILITE-inter-tenants.md`).
> Quand une session démarre vraiment, déplacer le fichier dans le hub
> permanent de l'app correspondante (`TECH_DOC/SESSIONS/<APP>/CHANTIER-NN-*.md`).

## Specs en attente

| # | Fichier | Domaine | Pré-requis |
|---|---|---|---|
| 1 | [`COMPTABILITE-inter-tenants.md`](COMPTABILITE-inter-tenants.md) | Compta — versements et monnaies locales fédérées | Chantier Fedow V2 mature |
| 2 | [`PANIER-en-base-commande-draft.md`](PANIER-en-base-commande-draft.md) | Panier — en base (`Commande.DRAFT`) au lieu de la session | Aucun |
| 3 | [`AUTH-connexion-par-code-achat-connecte.md`](AUTH-connexion-par-code-achat-connecte.md) | Auth — connexion par code à 6 chiffres, réservation et adhésion réservées aux connectés | Aucun |
| 4 | [`BENEVOLAT-planning-besoins.md`](BENEVOLAT-planning-besoins.md) | Bénévolat — planning de besoins façon Framadate dans `booking`, répétition des besoins en admin | Aucun |
| 5 | [`USERS-etiquettes.md`](USERS-etiquettes.md) | Étiquettes sur les personnes (par lieu), synchro vers Ghost pour écrire à des groupes (Brevo plus tard) | Aucun |
| 6 | [`CAISSE-mode-gerant-et-tag-nfc-en-post.md`](CAISSE-mode-gerant-et-tag-nfc-en-post.md) | Caisse — mode gérant à deux niveaux (OFFRIR), tag NFC jamais dans une URL (session / POST) — **idée, spec à écrire** | Aucun |
| 7 | [`BUGS-constats-chantier-05.md`](BUGS-constats-chantier-05.md) | Bugs constatés par les tests de caractérisation du chantier 05 (mail de connexion à l'adhésion admin, double webhook, T13, annulation d'un billet caisse, « payée ailleurs » sans mail, billet caisse NFC) | Aucun |
| 8 | [`COMPTABILITE-certification-NF525.md`](COMPTABILITE-certification-NF525.md) | Compta — sécuriser la chaîne des ventes (ancre de fin de chaîne, début de chaîne, clé) et certification NF525 — **idée, spec à écrire** | Chantier 05 terminé |
| 9 | **PRIORITÉ** — [`PRIORITE-KIOSK-recharge-fed-ancien-fedow.md`](PRIORITE-KIOSK-recharge-fed-ancien-fedow.md) | Kiosque — la recharge crédite de la TLF en local (commit `f47023f4`) au lieu d'un FED sur l'ancien Fedow ; risque de double crédit, ligne sans vente | **Juste après le chantier 05** |
| 10 | [`CHARGE-forte-affluence-festivals.md`](CHARGE-forte-affluence-festivals.md) | Charge — 3 festivals, ~100 points de vente, paiements simultanés sur le Fedow local et l'ancien Fedow : rien ne se perd, rien ne bloque (mesurer d'abord) — **idée, spec à écrire** | Chantier 05 terminé, kiosque PRIORITÉ traité |
| 11 | [`CAISSE-migration-caisse-v1-nouveau-modele.md`](CAISSE-migration-caisse-v1-nouveau-modele.md) | Caisse — migrer LaBoutik V1 sur le modèle Vente / Règlement du chantier 05 (une seule comptabilité par lieu) — **idée, spec à écrire** | Chantier 05 terminé |
