# Bugs constatés pendant le chantier 05 (hors chantier, à corriger plus tard)

> **Status :** constats vérifiés dans le code, **non corrigés**. Chacun est **figé** par
> un test de caractérisation (`tests/pytest/test_caracterisation_*.py`) : la correction
> modifie ce test **dans le même commit**, avec la raison au CHANGELOG.
> **Date :** 2026-09-29 (fiche 05-A′, tests de caractérisation). Décision du mainteneur :
> bugs, hors du chantier 05 « montants entiers ».
> **Pré-requis :** aucun. Les numéros de ligne (`~l.`) sont indicatifs.

| # | Bug | Où | Figé par |
|---|---|---|---|
| 1 | **Adhésion créée dans l'admin → mail de connexion non voulu.** Si l'adresse de l'adhérente n'est pas confirmée, un mail de connexion (`connexion_celery_mailer`) part. `MembershipAddForm.clean_email` appelle `get_or_create_user(email, send_mail=False)`, mais `MembershipAddForm.save()` le rappelle **sans** `send_mail=False` (défaut `True`). | `Administration/admin_tenant.py` ~l.1381 (`clean_email`), ~l.1438 (`save`) | `test_caracterisation_admin_api.py::test_adhesion_creee_dans_l_admin_passe_par_trigger_a` |
| 2 | **Deux `webhook_membership` pour un seul événement** (création dans l'admin, renouvellement d'abonnement). `set_deadline()` enregistre l'adhésion, puis un second enregistrement la voit avec son échéance : chaque enregistrement d'une adhésion avec échéance demande un webhook. | `BaseBillet/triggers.py` ~l.137, `Membership.set_deadline` (`BaseBillet/models.py` ~l.4169), `BaseBillet/signals.py` ~l.518-529 | `test_caracterisation_en_ligne.py::test_renouvellement_abonnement_iteration_et_statut_auto`, `test_caracterisation_admin_api.py::test_adhesion_creee_dans_l_admin_passe_par_trigger_a` |
| 3 | **T13 : rejeu `PAID → PAID` repasse les avoirs en `PAID`** (et renvoie webhook + mail des billets). Décision D33. | `BaseBillet/signals.py` ~l.42 (`set_ligne_article_paid`) | `test_caracterisation_en_ligne.py::test_paiement_reste_paye_puis_rejeu_repasse_les_avoirs_en_paye` |
| 4 | **Annuler UN seul billet vendu en caisse échoue toujours** (« Aucun paiement remboursable… »). La ligne de caisse porte un tarif vendu **sans** événement, le billet un tarif vendu **avec** événement : `_lignes_hors_stripe(pricesold_ids=…)` ne trouve rien. Seule l'annulation de toute la réservation marche. | `laboutik/views.py` ~l.5384, ~l.6554 ; `Reservation._lignes_hors_stripe` (`BaseBillet/models.py` ~l.3168) | non figé (constaté par sonde, A′-2) |
| 5 | **Réservation API v2 « payée ailleurs » : aucun mail de billet.** `paymentMethod` cash / card → la réservation passe `CREATED → VALID`, transition absente de `PRE_SAVE_TRANSITIONS` ; le commentaire du code dit le contraire. | `BaseBillet/validators.py` ~l.458 ; `api_v2/serializers.py` ~l.1363 | à figer si un test l'atteint |
| 6 | **À vérifier à l'écran : billet vendu en caisse et payé en NFC / cascade** → lignes de vente créées, mais ni réservation ni billet (`_creer_billets_depuis_panier` n'est appelé que par les chemins à un seul moyen). Une garde de l'interface l'empêche peut-être. | `laboutik/views.py` ~l.7453, ~l.7678 (appels) ; chemins cascade ~l.8457, ~l.9562, ~l.10147 | non figé |

Le détail et le contexte de chaque constat : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-SUIVI.md`
§5 et `CHANTIER-05-montants-entiers.md` §9.
