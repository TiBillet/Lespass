# 05-R — Relecture Fable de cohérence (2026-10-04) — à intégrer dans la réécriture de la fiche R

> Relecture en lecture seule : décisions Q-R1 à Q-R15 (SUIVI §5) × fiche R × code de la
> branche × code de la production (`origin/main` `a7734099`, préfixe `main:`). Numéros de
> ligne approximatifs, à relire au moment d'écrire.

## BLOQUANT

**B-1 — La production a peut-être déjà des clôtures `comptabilite.ClotureCaisse` (ancien calcul).**
Vérifié par l'orchestrateur sur `main` : `comptabilite` est dans TENANT_APPS
(`main:TiBillet/settings.py:196`) et Celery beat lance des clôtures J (6 h UTC), H, M, A
(`main:TiBillet/celery.py:89-109`), depuis mai 2026 (`568b5c5a`). D'après le relecteur,
une clôture par lieu à billetterie ou adhésion actives, **même sans vente**
(`main:comptabilite/tasks.py:115-199`). **Contredit la réponse Q-F1** (« aucune clôture en
production ») — à confirmer par le mainteneur et par R-0 (copie de la prod).
Si elles existent, sur la branche : la J « reprise » partirait de la fin de l'ancienne J
(`comptabilite/tasks.py:447`), le total perpétuel reprendrait l'ancien (`l.340-348`), le
rattrapage H/M/A partirait des anciennes (`l.744-748`), la fiche admin d'une ancienne
clôture plante (`presentation.py:454` `rapport["en_tete"]`), `verify_clotures` en anomalie.
Défaut proposé : **exporter en JSON hors base, puis purger** les anciennes clôtures la nuit
de la bascule (ancien calcul jamais chaîné, remplacé par les H/M/A recalculées).

**B-2 — Paiement Stripe `R` (remboursé) absent de Q-R8.** Les lignes d'origine restent
VALID, des lignes REFUNDED sont créées (`main:BaseBillet/models.py:2396-2418`).
Défaut : **R → vente réglée** + avoir(s) des lignes REFUNDED.

**B-3 — `Paiement_stripe.moyen` à poser par la reprise** (sinon un avoir futur échoue
quand H retire `payment_method` ; billets API v1 sans moyen dès aujourd'hui) :
`.update(moyen=…)` : SP si une ligne porte SP ; SR si `source == INVOICE` ou lignes SR ;
sinon SN. Les ventes en attente le recevront du webhook.

## IMPORTANT

- **I-1** Date d'encaissement : paramètre optionnel `datetime_encaissement=None` sur
  `encaisser_vente` (`services_vente.py` ~l.1417, 1547) ; `Vente.datetime_creation` et
  `Reglement.datetime` (`auto_now_add`) par `.update()`.
- **I-2** La reprise n'appelle pas `ajouter_article` (il crée une ligne) : elle refait
  `calculer_montants_article` + `.update()`, la règle « offert à montant non nul »
  (règlement FREE, `part_offerte`, `source_offert`) et `hors_chiffre_affaires`. La fiche
  dit à tort que le service écrit le FREE.
- **I-3** Marque « reprise » dans `rapport_json["en_tete"]` AVANT le scellement (paramètre de
  `_creer_la_cloture_journaliere` / `_enregistrer_la_cloture`). Lecture unique : J marquée →
  `datetime_fin` = date de mise en service. À brancher : FEC refusé si J reprise ou
  H/M/A avec `datetime_debut` < mise en service (couvre le mois de la bascule et le mois
  de la première vente, où la J reprise serait rangée) ; message de l'admin ; aucun mail
  pour une clôture finie avant la mise en service, ni pour la J reprise.
- **I-4** Plafond par passage du rattrapage : rien dans le code (`tasks.py` ~l.817-831,
  boucle sans limite) → compteur. Les H/M/A d'historique porteront le perpétuel de la
  dernière J (après la bascule) : informatif, à documenter.
- **I-5** Les lignes des ventes en attente et annulées reçoivent aussi leurs montants
  (sinon `encaisser_vente_stripe` ferait de tout le paiement un écart « reçu en plus »).
- **I-6** Paiement `N` (lien jamais généré) → **annulée quel que soit l'âge** (aucun
  webhook ne viendra). L'âge se lit sur `order_date` (`auto_now_add`), jamais sur
  `datetime` / `last_action`.
- **I-7** Date d'une vente à plusieurs lignes : `max(datetime)` du groupe pour
  `datetime_creation` et `datetime_encaissement` ; tri sur cette date ; avoir après sa
  vente à date égale.
- **I-8** Q-R10 « anomalie si Σ parts ≠ montant du QR » : invérifiable (le montant demandé
  n'est gardé nulle part). Σ qty des parts peut faire 0,99 / 1,01 (arrondi à 2 décimales,
  `main:BaseBillet/views.py:1328`) : information, pas anomalie.
- **I-9** `metadata` : dict OU texte JSON selon le producteur : lire les deux.
- **I-10** Admin : « reprise » n'est pas un `re_…` → l'inline afficherait un lien vers le
  paiement ; une ligne pour ne rien lier (`_adresse_stripe_d_un_reglement`).
- **I-11** Nuit : worker ET beat Celery arrêtés jusqu'à la J reprise du dernier lieu ;
  l'application entière coupée (une vente admin / API avec le nouveau code bloquerait la
  reprise du lieu).
- **I-12** Durée : la J reprise passe par une commande synchrone (jamais `.delay`, limite
  30 min) ; répétition chronométrée obligatoire.

## Cas de la production non couverts (défaut proposé)

1. Paiement `R` → réglée (B-2). 2. Paiement `N` → annulée (I-6).
3. Recharge API v2 temps / points (FREE) : restée CREATED → annulée ; validée → vente dans
   l'unité de la monnaie ; monnaie introuvable en base → anomalie.
4. Réservation gratuite API v2 (FREE, FREERES, `amount` parfois > 0) → offert total.
5. Adhésion payée par wallet via webhook Fedow (UK, VALID, origine LB) → une vente, règlement UK.
6-9. Billet « payé ailleurs », vente admin de billets, crowds, avoirs admin : couverts.
10. Ligne CREATED d'adhésion admin dont le passage PAID a échoué → annulée.
11-14. UNPAID hors Stripe, CANCELED, réservation annulée sans remboursement, jetons LG :
   inexistants ou couverts.

## Ordre de la nuit (déduit)

0. Avant : copie de prod, R-0 (dont anciennes clôtures B-1), répétition chronométrée.
1. Soir : application coupée ; worker + beat Celery arrêtés ; Stripe rejoue ses webhooks
   jusqu'à 3 jours.
2. Postgres redémarré avec `max_locks_per_transaction=512` (`max_connections` à vérifier
   pour `--executor=multiprocessing`).
3. Export JSON des anciennes clôtures (B-1). 4. `migrate_schemas` (durée à mesurer).
5. Purge des anciennes clôtures. 6. Passage à blanc, zéro anomalie bloquante.
7. `--executer` par lieu, puis `verify_integrity`. 8. J reprise par lieu (synchrone,
   marquée, sans mail ; lieu sans vente : aucune J).
9. Réouverture, Celery relancé (filet J à `heure_de_fermeture` + 2 h ; rattrapage
   plafonné sans mail). 10. La migration de vérification de H n'est PAS dans cette nuit.

## Sections de la fiche R à réécrire

En-tête, §1 (B-1), §2.4, §3.1 (retirer `uuid_transaction` ; QR par `metadata`), §3.2
(Q-R8 + B-2 + I-6 + I-5), §4.1 (Q-R10, Q-R11, Q-R12, I-2), §4.2 (B-3, Q-R4, Q-R6, I-2,
retirer `verifier_egalites`), §5 (Q-R14, I-1, I-7), §6 (I-3, I-4, B-1 à la place de
`laboutik.ClotureCaisse`), §7.1 (garde : vente réglée hors `reprise-…`), §7.2 (ordre
ci-dessus), §7.3 (anomalies : monnaie introuvable, origine introuvable, Σ qty ≠ 1 =
information), §8 (formes réelles de `main` + tests des points ci-dessus), §9 (renvoi à
Q-R1..15 + B-1, B-2, I-6, cas 3 et 10), §10.
