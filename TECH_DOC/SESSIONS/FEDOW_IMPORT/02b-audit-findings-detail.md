# Audit profond — Annexe : détail des 68 findings

Date : 2026-06-10. Générée automatiquement depuis le workflow `audit-fedow-import`
(42 agents, ~700 lectures de code, contre-expertise adversariale).
Synthèse et verdict : voir `02-audit-profond.md`.

Légende statut : ✅ confirmé par contre-expertise · ❌ réfuté · ⏳ non contre-expertisé (limite de session atteinte).


---

## Concurrence & intégrité financière (fedow_core V2)

**Synthèse de l'auditeur :** Le cœur du fedow_core V2 corrige bien le bug DRIFT de prod : crediter/debiter verrouillent la ligne Token (select_for_update) sous transaction.atomic, le contrôle de solde est re-fait SOUS verrou (pas de check-then-act), et l'abandon du chaînage previous_transaction élimine structurellement les 320 forks de hash. Le webhook de recharge Stripe est correctement sérialisé côté caller (verrou Paiement_stripe + re-check status + anti-tampering), et les conversions Decimal→centimes utilisent majoritairement int(round(prix*100)) conformément à la décision n°8. Les points sains vérifiés : pas de lost-update dans le chemin nominal, double-remboursement bloqué par le re-check de solde sous verrou (rollback complet), scanner_carte protégé par double-check locking sur la carte.

En revanche : (1) BLOQUANT — verify_transactions duplique les règles débit/crédit et les a désynchronisées (REFILL/BANK_TRANSFER), donc --fix-tokens créditerait les wallets des lieux du montant des virements bancaires reçus : l'outil de réconciliation fabrique de la monnaie ; il écrit en plus sans verrou (lost-update réintroduit). (2) Le pattern « lire le solde, puis débiter ce montant figé, puis détacher le wallet éphémère » (fusion et rembourser_en_especes) peut orphaniser un reliquat crédité concurremment — le garde-fou V1 « amount == token.value au save » a disparu. (3) L'idempotence de process_cashless_refill repose sur le verrou du caller, pas sur une contrainte DB. (4) La création de Wallet user n'est pas sérialisée (doublons possibles, tokens invisibles). (5) Plus largement, toutes les validations métier par action du Transaction.save() V1 (carte↔wallet, receiver=lieu, asset accepté/fédéré, checkout obligatoire) ont disparu du service : la défense en profondeur du moteur financier n'existe plus qu'a posteriori. Le hash individuel promis n'est calculé nulle part et aucune formule n'est définie.


### ✅ [BLOQUANT] verify_transactions : règles débit/crédit désynchronisées de services.py — --fix-tokens corrompt les soldes

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/management/commands/verify_transactions.py:204`

La commande recalcule le solde attendu avec actions_sans_debit=[FIRST, CREATION] (l.204) alors que services.py l.768-773 ne débite PAS non plus REFILL ni BANK_TRANSFER ; côté crédit, la commande compte TOUTES les transactions où le wallet est receiver (l.212-216) alors que services.py l.792 ne crédite PAS BANK_TRANSFER. Conséquence : dès qu'un tenant a reçu un virement (BANK_TRANSFER, receiver=wallet du lieu, créé par enregistrer_virement l.1112 avec receiver_wallet renseigné), la commande déclare une fausse divergence et --fix-tokens CRÉDITE le wallet du lieu du montant des virements bancaires → création de monnaie fantôme par l'outil de réconciliation lui-même. Idem si le wallet_origin d'un asset possède un Token : tous les REFILL seraient comptés comme débits. De plus _fix_tokens (l.332-363) écrit une valeur absolue calculée AVANT, sans select_for_update ni transaction.atomic : exécuté sur un système en production, il réintroduit exactement le lost-update du DRIFT V1.

**Recommandation :** Importer/partager la définition canonique des règles (actions_sans_debit/actions_sans_credit) depuis services.py au lieu de la dupliquer ; exclure BANK_TRANSFER côté crédit et REFILL/BANK_TRANSFER côté débit ; dans _fix_tokens, recalculer le solde attendu SOUS verrou (select_for_update + atomic) au moment de l'écriture. Ajouter un test pytest qui crée un BANK_TRANSFER puis lance verify_transactions et exige 0 erreur.

**Contre-expertise (confiance haute)** : confirmé.
> Problème confirmé par lecture du code, impossible à réfuter. (1) Désync avérée : verify_transactions.py:204 exclut seulement FIRST/CREATION des débits alors que services.py:768-773 n'en débite pas non plus REFILL ni BANK_TRANSFER ; côté crédit, la commande (verify_transactions.py:212-216) compte toutes les transactions receiver sans exclusion alors que services.py:792 ne crédite pas BANK_TRANSFER. Le commentaire périmé « cf. services.py ligne 429 » (verify_transactions.py:202) prouve que la commande référence une version antérieure de services.py. (2) Scénario BANK_TRANSFER certain : enregistrer_virement (services.py:1112-1117) crée la transaction avec receiver=wallet du tenant sans mutation Token ; or un virement exige une dette > 0 donc un REFUND préalable, et le REFUND crédite ce même wallet (services.py:590-595, REFUND absent de actions_sans_credit), donc le Token existe toujours (get_or_create dans crediter, services.py:292) → la commande compte le virement comme crédit manquant → fausse ERROR → --fix-tokens (verify_transactions.py:354-357) écrit le solde gonflé = création de monnaie fantôme. (3) Scénario REFILL également déclenchable : crediter_depuis_stripe (services.py:1232-1233) envoie les REFILL avec sender=asset_fed.wallet_origin ; dès que ce wallet a un Token (premier crédit SALE/REFUND), la commande sur-compte les débits → fausse divergence inverse, --fix-tokens raboterait le solde du lieu. (4) Aucune garde ni test protecteur : test_verify_transactions.py et test_charge_festival.py n'utilisent que CREATION et SALE, jamais REFILL/BANK_TRANSFER. (5) _fix_tokens (verify_transactions.py:350-357) : Token.objects.get sans select_for_update ni atomic, écriture d'une valeur absolue calculée avant dans _verifier_soldes → lost-update confirmé sur système en production. Atténuants mineurs (commande manuelle, confirmation interactive, libellé DANGEREUX) mais ils n'empêchent rien : la commande est l'outil officiel d'intégrité du projet et tout tenant avec recharges Stripe ou virements générera de fausses erreurs incitant l'opérateur à lancer le fix corrupteur. Sévérité « bloquant » justifiée pour un outil de réconciliation monétaire qui corrompt les soldes qu'il est censé vérifier.


### ✅ [MAJEUR] process_cashless_refill : idempotence non garantie par contrainte DB (double-livraison webhook)

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:1208`

Le check d'idempotence est un filter(checkout_stripe=..., action=REFILL).first() non verrouillé à l'intérieur d'un atomic, et il n'existe AUCUNE contrainte d'unicité sur Transaction.checkout_stripe (models.py l.615 : UUIDField nullable, pas unique). Deux exécutions concurrentes voient toutes deux « rien » et créent deux REFILL → double crédit. Aujourd'hui le seul caller (ApiBillet/views.py:1097-1147 traiter_paiement_cashless_refill) sérialise via select_for_update sur Paiement_stripe + re-check status=PAID, donc le bug est masqué. Mais la docstring promet « idempotent interne », ce qui est faux : tout futur caller (autre PSP, cf. PSP_INTERFACE.md, ou tâche Celery) sans verrou externe double-crédite sous double-livraison Stripe.

**Recommandation :** Ajouter une UniqueConstraint partielle sur Transaction (fields=['checkout_stripe'], condition=Q(action='RFL', checkout_stripe__isnull=False)) + catch IntegrityError → re-get. L'idempotence devient une garantie DB, plus une convention de caller.

**Contre-expertise (confiance haute)** : confirmé. Sévérité réévaluée : moyen.
> Confirmé par lecture. (1) Aucune contrainte DB : fedow_core/models.py:615-620, checkout_stripe = UUIDField(null=True, blank=True) sans unique=True ; Meta (l.650-664) ne contient que des Index. Les champs uniques de Transaction ne protègent pas : uuid a un default uuid4 neuf à chaque insert (l.423-425) et hash est null à la création ('Phase 2 — pas de calcul', services.py:804-806 ; Postgres accepte plusieurs NULL en colonne unique). (2) Race check-then-act : services.py:1208-1213, filter(...).first() non verrouillé dans atomic() ; sous READ COMMITTED deux exécutions concurrentes voient toutes deux 'rien' et créent deux REFILL ; le select_for_update sur Token dans TransactionService.creer sérialise seulement le crédit, pas l'insert → double crédit. (3) MAIS non déclenchable aujourd'hui : l'unique caller traiter_paiement_cashless_refill (ApiBillet/views.py:1097-1112) sérialise via select_for_update sur Paiement_stripe + re-check status==PAID après lock, et les deux chemins (webhook l.1160+ et retour user) passent par cette fonction. (4) Le contrat est néanmoins faux : la docstring (services.py:1194-1199) et surtout PSP_INTERFACE.md:22-27 assignent l'idempotence à RefillService, et la checklist nouveau PSP (l.60-67) n'exige aucun verrou externe — un futur PSP suivant ce contrat double-créditerait sous double-livraison webhook. Le test tests/pytest/test_refill_service.py:113-139 est séquentiel uniquement. Problème réel mais latent : sévérité 'majeur' excessive, 'moyen' plus juste (fix trivial : UniqueConstraint conditionnelle sur (checkout_stripe, action) + get_or_create/gestion IntegrityError).


### ✅ [MAJEUR] fusionner_wallet_ephemere : montant lu hors verrou puis détachement — solde résiduel orphelin

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:401`

tokens_avec_solde est lu SANS verrou (l.401-404), puis chaque FUSION débite le montant figé token_a_transferer.value (l.410). debiter() re-lit sous verrou mais débite exactement ce montant figé. Si une recharge concurrente crédite le wallet éphémère entre la lecture et le débit (terminal A recharge la carte pendant que terminal B fait l'adhésion/fusion, ou webhook), le reliquat reste sur le wallet éphémère qui est ensuite détaché de la carte (l.424 wallet_ephemere=None) → argent du client définitivement inaccessible. Le Fedow standalone avait le garde-fou « assert self.amount == token_sender.value » au moment du save (Fedow/fedow_core/models.py l.700) qui revérifiait l'égalité sous l'écriture ; ce garde-fou a disparu en V2. Le caller POS (laboutik/views.py:4346 via _creer_adhesions_depuis_panier) ne verrouille pas la ligne carte, contrairement à lier_a_user (l.1394).

**Recommandation :** Dans la boucle de fusion, verrouiller d'abord le Token (select_for_update) et utiliser sa value fraîche comme montant (ou re-lister les tokens sous verrou de la carte). Verrouiller la ligne CarteCashless en tête de fusionner_wallet_ephemere comme le fait lier_a_user.

**Contre-expertise (confiance haute)** : confirmé.
> Problème confirmé par lecture du code, je n'ai pas pu le réfuter. (1) fedow_core/services.py:401-404 : le queryset tokens_avec_solde est lu SANS verrou. (2) services.py:410 : chaque FUSION débite le montant figé token_a_transferer.value ; debiter() (services.py:476-498) verrouille la ligne Token mais ne vérifie que `value < montant` (l.489) — un crédit concurrent intercalé laisse un reliquat silencieusement. (3) services.py:423-425 : wallet_ephemere=None posé sans re-vérifier que le solde résiduel est nul. (4) Le garde-fou du Fedow standalone existe bien et a disparu en V2 : Fedow/fedow_core/models.py:698 `assert self.amount == token_sender.value` revérifiait l'égalité au moment de l'écriture sous verrou. (5) L'appelant POS laboutik/views.py:4327 charge la carte sans select_for_update avant la fusion (l.4346) ; le bloc atomic englobant (views.py:5182) ne protège pas en READ COMMITTED. lier_a_user verrouille la carte (services.py:1394) mais le chemin recharge ne la verrouille jamais (views.py:5215-5216 et _obtenir_ou_creer_wallet l.987 lisent wallet_ephemere sans verrou), donc aucune sérialisation. (6) Aggravation non signalée par l'auditeur : la recharge résout wallet_client=carte.wallet_ephemere en début de requête sans verrou (views.py:5216) — si la fusion commit entre-temps, la recharge ENTIÈRE est créditée sur le wallet déjà détaché (crediter, services.py:292-303, fait un get_or_create qui recrée même le Token), fenêtre de course bien plus large que snapshot→débit. Aucun test pytest ne couvre cette concurrence (test_scan_qr_carte_v2.py et test_retour_carte_recharges.py testent la fusion en séquentiel). Nuance sur l'énoncé : « définitivement inaccessible » vaut pour les flux applicatifs (vider_carte views.py:6313 et rembourser_en_especes services.py:556-560 ne voient plus le wallet orphelin) ; les fonds restent en base avec audit trail (Transaction REFILL) et sont récupérables manuellement par un admin. Sévérité majeur justifiée : perte d'argent client dans un système cashless, même si la probabilité est faible (même carte physique impliquée dans deux opérations concurrentes — requête HTTP retardée, double terminal, ou recharge en vol pendant l'adhésion).


### ✅ [MAJEUR] rembourser_en_especes : tokens lus hors atomic + vider_carte → reliquat orphelin, pas de verrou carte

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:567`

tokens_eligibles est matérialisé (list) AVANT le transaction.atomic() (l.567-580 vs l.588) et les montants REFUND utilisent ces valeurs figées (l.594). Le double remboursement simultané est bien bloqué (debiter re-vérifie sous verrou → SoldeInsuffisant → rollback complet), mais : (1) un crédit concurrent (recharge POS pendant le vider-carte) laisse un reliquat non remboursé, et si vider_carte=True sur une carte anonyme, le wallet_ephemere est détaché avec ce reliquat → argent client perdu, même classe de bug que la fusion ; (2) aucune ligne carte n'est verrouillée, donc carte.save(update_fields=['user','wallet_ephemere']) (l.667) peut écraser un lier_a_user concurrent (last-write-wins sur la carte) ; (3) la SoldeInsuffisant levée au 2e clic concurrent n'est catchée ni dans Administration/views_cards.py:177 ni dans laboutik/views.py:7439 (seul NoEligibleTokens l'est) → 500 brut au POS.

**Recommandation :** Déplacer la sélection des tokens DANS l'atomic avec select_for_update() sur les Token (et sur la carte), utiliser les valeurs verrouillées comme montants ; catcher SoldeInsuffisant dans les deux vues avec un toast « solde modifié, rescannez ».

**Contre-expertise (confiance haute)** : confirmé.
> Les 3 sous-problèmes sont confirmés par lecture du code. (1) fedow_core/services.py:567-577 : tokens_eligibles matérialisé en list AVANT le transaction.atomic() (l.588), montants REFUND figés (l.594) ; debiter() (l.476-495) re-vérifie sous select_for_update mais débite le montant figé → un crédit concurrent (ex. webhook Stripe de recharge en ligne, sans présence de la carte) laisse un reliquat ; avec vider_carte=True (l.656-667) le wallet_ephemere est détaché avec ce reliquat — le wallet reste en base mais devient injoignable depuis la carte anonyme. (2) Pas de verrou carte dans rembourser_en_especes (carte.save l.667 sur objet lu sans lock), alors que scanner_carte (l.1322-1323) et lier_a_user (l.1393-1394) verrouillent explicitement la ligne carte pour ce motif exact (commentaire l.1287-1293 sur le last-write-wins) — divergence du pattern établi du codebase. (3) SoldeInsuffisant hérite d'Exception brute (fedow_core/exceptions.py:9) et n'est catchée ni dans Administration/views_cards.py:176-192 ni dans laboutik/views.py:7438-7451 (seul NoEligibleTokens l'est), alors qu'elle EST catchée ailleurs dans le même fichier (laboutik/views.py:5868, 6740, 7094) → 500 brut déclenchable par double POST réellement concurrent (le 2e bloque sur le verrou Token, le 1er commit, le 2e re-lit value=0). Aucune garde amont, aucun test couvrant ces races. Sévérité "majeur" justifiée : probabilité faible pour la perte d'argent (fenêtre courte) mais impact monétaire dans un moteur cashless + 500 au POS trivialement déclenchable. Point positif confirmé : le double remboursement est bien bloqué (rollback complet via SoldeInsuffisant), il n'y a pas de double-payout possible.


### ✅ [MAJEUR] Création concurrente du Wallet user : doublons possibles, tokens sur le wallet perdant

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:371`

fusionner_wallet_ephemere (l.371-378) et process_cashless_refill (l.1220-1225) font tous deux « if user.wallet is None: Wallet.objects.create(...); user.save(update_fields=['wallet']) » sans verrou sur la ligne user. TibilletUser.wallet est un OneToOneField(SET_NULL) côté user (AuthBillet/models.py l.135) — il n'y a pas de contrainte empêchant deux Wallets créés en parallèle. Scénario : un user sans wallet fait une recharge en ligne (webhook crée walletA, fuse/crédite dessus) pendant qu'un caissier lie sa carte au POS (crée walletB, fusionne les tokens éphémères dessus). Le dernier user.save() gagne ; les tokens crédités sur l'autre wallet deviennent invisibles (le wallet existe mais n'est plus référencé par user.wallet). Perte d'argent réelle, silencieuse.

**Recommandation :** Centraliser dans un helper get_or_create_wallet_user(user) qui fait select_for_update sur la ligne TibilletUser (ou refresh sous verrou) avant le test user.wallet is None ; à terme, contrainte/convention 1 wallet par user.

**Contre-expertise (confiance haute)** : confirmé.
> Problème confirmé par lecture du code. Trois sites font un check-then-act non verrouillé « if user.wallet is None: Wallet.objects.create(); user.save(update_fields=['wallet']) » : fedow_core/services.py:371-378 (fusionner_wallet_ephemere), fedow_core/services.py:1220-1225 (process_cashless_refill, fallback), et un troisième que l'auditeur n'a pas cité : BaseBillet/views.py:1942-1948 (refill_wallet_submit, exécuté hors atomic). TibilletUser.wallet est OneToOneField(SET_NULL, null=True) (AuthBillet/models.py:133) ; l'unicité porte sur user.wallet_id côté user, et le modèle Wallet (AuthBillet/models.py:104-120) n'a aucune FK vers user : rien n'empêche deux Wallets créés en parallèle, le dernier user.save() gagne. Les verrous existants ne couvrent pas le user : select_for_update porte sur Token (services.py:300, 466) et sur CarteCashless dans lier_a_user (services.py:1394), jamais sur la ligne user. Aucun test de concurrence sur ce cas (test_traiter_paiement_cashless_refill.py teste le verrou Paiement_stripe, pas la création de wallet). Nuance sur le scénario exact : le fallback webhook (l.1220) est rarement atteint car refill_wallet_submit crée le wallet AVANT le checkout Stripe (views.py:1942) — mais cela déplace la course sans l'éliminer : la course réellement déclenchable est entre refill_wallet_submit (views.py:1942, hors atomic) et la fusion POS (services.py:371 via lier_a_user services.py:1426 ou _creer_adhesions_depuis_panier laboutik/views.py:4346). Conséquence confirmée : les tokens FUSION crédités sur le wallet perdant restent en base mais deviennent inaccessibles via user.wallet (invisibles pour tous les affichages de solde) — perte silencieuse, récupérable uniquement par audit DB manuel. Sévérité « majeur » justifiée par l'impact financier silencieux, même si la fenêtre est étroite (user sans wallet + deux flux simultanés, plausible en événement : premier scan de carte au POS pendant une recharge en ligne depuis le téléphone). Fix simple : verrouiller la ligne user (select_for_update) ou centraliser la création via un helper get_or_create idempotent.


### ✅ [MAJEUR] Garde-fous métier du Transaction.save() V1 disparus dans TransactionService.creer

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:760`

Le Fedow standalone validait par action dans Transaction.save() (Fedow/fedow_core/models.py l.559-788) : SALE → card obligatoire + card.wallet == sender + primary_card appartenant au lieu + asset accepté par le lieu + receiver est un lieu ; REFILL → receiver n'est ni lieu ni primary + checkout_stripe obligatoire pour le FED + (TLF) wallet_origin == sender ; FUSION → amount == solde total + carte non liée ; datetime monotone. En V2, creer() (l.760-823) n'effectue AUCUNE de ces validations : n'importe quel caller peut créer une SALE vers un wallet user, une transaction sur un asset d'un tenant non fédéré (le check tenant/asset n'existe qu'a posteriori dans verify_transactions check 3), un montant 0 (transaction de bruit), ou passer une card sans rapport avec le sender. Les contrôles sont remontés dans les vues POS (carte primaire/PV), mais la défense en profondeur au niveau du moteur financier a disparu — exactement la couche qui protège quand une vue a un bug.

**Recommandation :** Ajouter dans creer() un bloc de validations FALC par action : montant int > 0, cohérence card↔sender, asset accessible au tenant (réutiliser la logique de obtenir_assets_accessibles), receiver=wallet du lieu pour SALE/QRCODE_SALE. Lever des exceptions métier dédiées. Cela rend aussi verify_transactions check 3 quasi toujours vert par construction.

**Contre-expertise (confiance haute)** : confirmé.
> Confirmé par lecture croisée des deux codebases.

V1 (Fedow/fedow_core/models.py:559-788) : Transaction.save() contient bien les garde-fous décrits — SALE : card obligatoire + card.get_wallet()==sender + primary_card in receiver.place.primary_cards + asset in accepted_assets() + receiver.is_place() (l.655-675) ; REFILL : receiver ni place ni primary + checkout_stripe obligatoire pour l'asset stripe primary + wallet_origin==sender sinon + previous CREATION (l.631-652) ; FUSION : amount==solde total + carte non liée à un user (l.699-704) ; datetime monotone (l.590).

V2 (lespass-main/fedow_core/services.py:707-832) : TransactionService.creer() ne fait AUCUNE de ces validations — uniquement débit/crédit/insert dans un atomic. Le modèle Transaction V2 (fedow_core/models.py:333-667) n'a ni save() override ni clean() ; seules protections résiduelles : amount PositiveIntegerField (models.py:506, bloque le négatif mais pas 0), SoldeInsuffisant dans WalletService.debiter (services.py:481-495), et le check tenant/asset uniquement a posteriori dans verify_transactions check 3 (management/commands/verify_transactions.py:10,98) — exactement comme annoncé.

Point aggravant non souligné par l'auditeur : REFILL est dans actions_sans_debit (services.py:768-773) et crediter() fait get_or_create du Token (services.py:292-296). Donc creer(action=REFILL, asset=<asset d'un autre tenant non fédéré>, receiver=<n'importe quel wallet>) crée de la monnaie ex nihilo sans checkout_stripe, sans vérif wallet_origin, sans vérif fédération — création monétaire non gardée là où V1 l'interdisait (models.py:631-649). Montant 0 passe aussi (debiter : 0 <= solde toujours vrai).

Atténuations réelles : (1) creer() n'est pas exposé à des entrées non fiables directement — V1 était un serveur HTTP standalone où save() était la dernière ligne de défense derrière les serializers, V2 est une couche service interne dont les callers (laboutik/views.py:5793-5830, controlvanne/billing.py:177, vérifiés) font les contrôles POS/carte/montant>0 en amont ; (2) certains checks V1 ont été abandonnés par décision explicite (hash chain individuelle, suppression sequence_number — cf. décisions du projet), donc le check datetime monotone lié à la chaîne n'a plus de sens en V2 ; (3) l'invariant financier le plus critique (solde suffisant) est conservé.

Mais la sévérité « majeur » reste justifiée : c'est le moteur financier, il y a ~15 sites d'appel de creer_vente/creer_recharge, et un seul bug de vue suffit pour créer une SALE vers un wallet user, débiter un asset non fédéré, ou pire, minter via REFILL sans aucun contrôle. La défense en profondeur a bien disparu de la couche moteur.


### · [MINEUR] REFUND crédite le wallet du lieu pour TOUTES les catégories (V1 brûlait les TLF)

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:792`

Dans le Fedow V1 (models.py l.710-729), un REFUND décrémentait le payeur mais ne créditait le lieu QUE pour l'asset fédéré (et lieu non-primary) ; les tokens locaux remboursés étaient détruits (« le lieu a remboursé en espèce, il ne stocke plus l'asset »). En V2, creer() crédite le receiver pour tout REFUND (actions_sans_credit ne contient que BANK_TRANSFER, l.792). Les TLF remboursés s'accumulent donc indéfiniment sur le Token du wallet lieu sans jamais être réutilisés (REFILL ne débite pas l'émetteur). Pas de perte d'argent, mais la masse monétaire « en circulation » devient fausse, le Token du lieu gonfle sans signification, et tout import V1→V2 suivi d'un verify_transactions produira des écarts si on rejoue l'historique avec les règles V2. Idem DEPOSIT/VOID : V1 ne créditait jamais le receiver d'un DEPOSIT (« ça part à la banque ») et ne touchait pas aux tokens pour VOID ; en V2 ces actions suivent la règle générique débit+crédit — inutilisées aujourd'hui (aucun caller trouvé) mais piégeuses pour la Phase 6 d'import.

**Recommandation :** Décider et documenter explicitement la sémantique V2 par action (qui est crédité, qui est débité) dans un tableau unique partagé entre services.py et verify_transactions ; pour DEPOSIT, ajouter l'action à actions_sans_credit avant tout usage ; prévoir la transposition de règles lors de l'import des transactions V1.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] enregistrer_virement : re-check de dette non sérialisé, max(0) masque les sur-versements

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:1100`

Le commentaire « re-check de la dette dans l'atomic (race guard) » (l.1102) est trompeur : calculer_dette est un aggregate en lecture, sans verrou. Deux saisies superuser concurrentes du même virement calculent toutes deux dette=X et enregistrent chacune X → sur-versement double. Pire, calculer_dette retourne max(0, dette) (l.977), donc l'anomalie devient invisible au dashboard au lieu d'alerter. Probabilité faible (action manuelle superuser) mais c'est de l'argent réel sortant en banque.

**Recommandation :** Sérialiser par verrou (select_for_update sur l'Asset ou pg_advisory_xact_lock sur (tenant_id, asset_id)) avant le calcul de dette ; logger/alerter si la dette brute est négative au lieu de la clamper silencieusement.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Hash d'intégrité jamais calculé : promesse non vérifiable, immutabilité non protégée

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/models.py:446`

Transaction.hash (SHA256 individuel, unique=True nullable) n'est calculé NULLE PART : aucun hashlib/create_hash dans fedow_core (grep vide), services.py écrit hash=null partout, et verify_transactions ne vérifie aucun hash malgré son nom — la « Phase 3 consolidation » (recalcul + NOT NULL) n'a ni formule canonique définie, ni command. Conséquences : (1) tant que Phase 3 n'existe pas, l'immutabilité repose uniquement sur l'admin readonly — une mutation ORM/SQL d'une Transaction est indétectable (le V1 avait verify_hash() à chaque save) ; (2) attention au design futur : avec unique=True, deux transactions au contenu identique (même montant, mêmes wallets, même seconde — fréquent au POS) auront le même hash si la formule n'inclut pas id/uuid → IntegrityError en production.

**Recommandation :** Définir dès maintenant la formule de hash (incluant id ou uuid) dans un module unique, même si le calcul reste différé ; ajouter le check de hash dans verify_transactions (skip si null) ; planifier la command de consolidation Phase 3 avant tout import.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Conversions résiduelles non conformes : dround via float, int() sans round()

`/home/jonas/TiBillet/dev/lespass-main/fedow_connect/utils.py:20`

Trois écarts à la décision n°8 (« centimes int partout, jamais int() seul, jamais via float ») sur le chemin de l'argent : (1) dround() fait Decimal(value / 100) — division FLOAT int/int — avant quantize ; le quantize répare l'erreur float pour 2 décimales, donc pas de bug aujourd'hui, mais c'est exactement le pattern fragile interdit ; (2) ApiBillet/views.py:1115 fait int(paiement_lock.total() * 100) — int() tronquant sur un Decimal issu de dround — utilisé pour l'anti-tampering ET comme montant crédité du REFILL : si total() change de représentation (3 décimales, float), le montant crédité diverge silencieusement de Stripe ; (3) laboutik/views.py:2946 int(prix_unitaire_centimes * ligne.qty) tronque au lieu d'arrondir sur les qty fractionnaires (vrac/cascade) — affichage ticket, écart max 1 centime. Le reste du code utilise correctement int(round(prix * 100)) (l.518, 3466, 8072...).

**Recommandation :** Remplacer dround par une division Decimal exacte (Decimal(value) / 100), utiliser int(round(...)) aux deux points cités ; idéalement centraliser euros↔centimes dans un util unique testé.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Signal post_save Asset : pas de garde `raw` (loaddata) et effets de bord cross-app dans la transaction

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/signals.py:49`

creer_ou_mettre_a_jour_product_recharge ne teste pas kwargs.get('raw') : un loaddata de fixtures Asset exécuté dans un schema tenant déclenchera la création de Product/Price/CategorieProduct et l'attachement aux PV pendant le chargement de fixtures — piège classique Django, particulièrement dangereux pour la Phase 6 (import des 500 lieux V1 : si l'import passe par save() en contexte tenant, chaque Asset importé crée des produits de recharge non désirés). Le skip schema public (l.73-75) protège seulement les tests fedow_core. Par ailleurs le signal s'exécute de façon synchrone dans la transaction du save de l'Asset (pas de on_commit) : un échec côté laboutik.PointDeVente fait échouer la création d'Asset — couplage acceptable mais à connaître pour le portage vers Lespass V1 où laboutik n'existe pas (l'import `from laboutik.models import PointDeVente` lèverait ImportError au premier save d'Asset).

**Recommandation :** Ajouter `if kwargs.get('raw'): return` en tête du receiver ; pour le portage vers la branche main-fedow-import, conditionner l'import laboutik (try/except ou check apps.is_installed) ; pour l'import V1, utiliser bulk_create ou désactiver le signal explicitement.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] get_or_create_wallet_tenant : course possible sur la création du wallet lieu (pas de contrainte d'unicité)

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:253`

Wallet n'a aucune contrainte unique sur (origin, name) (AuthBillet/models.py l.104-121), donc le get_or_create(origin=tenant, name='Lieu ...') n'est pas protégé : deux premiers remboursements simultanés sur un tenant neuf peuvent créer DEUX wallets lieu. Les REFUND suivants se répartiraient entre les deux (Token du lieu scindé), faussant les soldes affichés — la dette BANK_TRANSFER reste juste car calculée par champ tenant, pas par wallet. Le code lui-même note « NB : a remplacer par tenant.wallet quand la convention sera formalisee ».

**Recommandation :** Avant la mise en prod V2 : soit UniqueConstraint(origin, name) sur Wallet, soit (mieux) FK wallet sur Customers.Client comme prévu par la note, créé une fois en bootstrap du tenant.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Vente POS sans clé d'idempotence client : un re-POST réseau crée un double débit

`/home/jonas/TiBillet/dev/lespass-main/laboutik/views.py:5771`

uuid_transaction = uuid_module.uuid4() est généré CÔTÉ SERVEUR à chaque requête (l.5771) ; le POST de paiement ne porte aucun identifiant d'opération fourni par le client. Un double-submit (double tap sur écran tactile, retry après timeout sur wifi de festival, bouton HTMX non désactivé) rejoue la requête entière : deux séries de TransactionService.creer_vente débitent deux fois la carte tant que le solde suffit — chaque exécution est individuellement atomique et valide, donc aucune protection ne se déclenche. Le bug DRIFT V1 montre que la concurrence POS en événement est le cas NORMAL, pas l'exception.

**Recommandation :** Générer l'uuid d'opération côté client POS (champ hidden dans le formulaire HTMX) et le rendre unique en base (contrainte sur LigneArticle.uuid_transaction ou table d'idempotence) ; a minima désactiver les boutons de paiement pendant la requête (hx-disable).

_Non contre-expertisé (sous le seuil majeur)._


### · [INFO] Ordre de verrouillage sender→receiver : deadlock possible si TRANSFER croisés, contention sur le token du lieu

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:776`

creer() verrouille toujours le Token du sender puis celui du receiver (l.776-800). Pour les flux actuels (SALE/REFUND : user→lieu ; FUSION : éphémère→user ; REFILL : un seul verrou côté receiver), les ordres ne se croisent jamais → pas de deadlock aujourd'hui. Mais l'action TRANSFER (wallet↔wallet, l.390 du modèle) existe et n'a aucun caller : le jour où des virements user↔user sont branchés, deux transferts croisés A→B et B→A donneront un deadlock PostgreSQL (40P01, une des deux requêtes avorte en 500). Par ailleurs, toutes les ventes d'un lieu sérialisent sur la même ligne Token du lieu pendant toute la durée de l'atomic appelant (qui inclut LigneArticle, Membership, tickets...) — sous forte charge festival, c'est le goulot de débit à surveiller (correct financièrement, mais latence en pointe).

**Recommandation :** Documenter l'invariant d'ordre de verrouillage ; si TRANSFER est activé un jour, trier les acquisitions de verrous par pk de Token. Pour la contention, garder les atomic POS les plus courts possibles (le crédit lieu pourrait passer en F()-update sans verrou puisqu'il n'a pas de check de solde).

_Non contre-expertisé (sous le seuil majeur)._


---

## Isolation multi-tenant & dispatch V1/V2

**Synthèse de l'auditeur :** Audit isolation multi-tenant & dispatch V1/V2 du prototype fedow_core (lespass-main). Points sains vérifiés : les 4 admins fedow_core définissent les has_*_permission avec TenantAdminPermissionWithRequest et filtrent leurs querysets par tenant (Asset via tenant_origin|federated_with, Token via asset__tenant_origin, Transaction via tenant, Federation via tenants|created_by) ; les flows d'invitation (accept_invitation / accept_asset_invitation / remove_member) vérifient l'appartenance à pending et le rôle créateur ; aucun cache n'est utilisé dans fedow_core ni dans les branches V2 (le seul cache cross-tenant, _get_tenant_info_cached, est documenté volontaire) ; les tenant_context imbriqués observés (lier_a_user, peut_recharger_v2, refill_wallet_submit) restaurent correctement le schéma (context manager exception-safe) ; le dispatch server_cashless est présent sur scan QR, link, lost_card, my_cards, refill, return_refill, et les tâches Celery V1 sont gardées par check_serveur_cashless. En revanche, 15 problèmes concrets : 1 bloquant (AssetAdmin.save_model choisit un wallet ARBITRAIRE origin=tenant comme wallet_origin — potentiellement le wallet d'un client, qui encaisserait alors toutes les ventes POS de l'asset) ; 7 majeurs : la fédération est cassée en prod (accept remplit Asset.federated_with mais la caisse lit Federation.assets, jamais peuplé hors demo), le FED n'est dépensable nulle part par défaut (pas de cas spécial dans obtenir_assets_accessibles), le critère de dispatch est incohérent ('' vs None sur URLField blank+null → tenant mixte V1/V2 après migration), tokens_table/transactions_table plantent en FedowAPI pour les verdicts wallet_legacy/feature_desactivee sur tenant V2, enregistrer_virement écrit la LigneArticle comptable dans le mauvais schéma, refund_online n'a aucun dispatch, et le POS duplique scanner_carte sans verrou avec le mauvais origin. Le reste : leaks d'information mineurs (list_filter asset global, historique wallet non filtré, panel V2 chez les V1) et fragilités (redirect par substring, get_or_create_wallet_tenant non contraint).


### ✅ [BLOQUANT] Asset.wallet_origin peut pointer vers le wallet d'un client (ventes créditées à un client)

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/admin.py:339`

AssetAdmin.save_model fait `Wallet.objects.filter(origin=tenant_actuel).first()` sans order_by ni filtre name pour poser wallet_origin. Or les wallets CLIENTS et éphémères ont aussi origin=tenant (services.py:373 fusionner_wallet_ephemere, services.py:1347 scanner_carte, laboutik/views.py:993 _obtenir_ou_creer_wallet). Scénario : un tenant V2 scanne une carte vierge ou identifie un membre AVANT de créer son premier asset → le `.first()` retourne le wallet d'un client. Comme les ventes POS créditent `asset.wallet_origin` (laboutik/views.py:5823, 6683, 7012 : receiver_wallet=asset_a_debiter.wallet_origin), tout le chiffre d'affaires cashless de l'asset crédite le Token d'un client, qui peut ensuite dépenser ce solde à la caisse. Idem pour enregistrer_virement (sender=asset.wallet_origin).

**Recommandation :** Remplacer le `.first()` par WalletService.get_or_create_wallet_tenant(tenant_actuel) (convention origin+name='Lieu <schema>'), et ajouter un test qui crée un wallet client avant le premier asset.

**Contre-expertise (confiance haute)** : confirmé.
> Tentative de réfutation échouée — chaque maillon du scénario est confirmé par lecture du code, et aucune garde amont n'existe.

1) Les wallets clients/éphémères ont bien origin=tenant : (a) fedow_core/services.py:1347-1350 (scanner_carte crée le wallet_ephemere avec origin=tenant_origine), (b) fedow_core/services.py:373-376 (fusionner_wallet_ephemere crée le wallet user avec origin=tenant), (c) laboutik/views.py:992-995 (_obtenir_ou_creer_wallet, origin=connection.tenant). Le champ AuthBillet/models.py:106 (origin FK Client) ne distingue pas lieu/client.

2) Le déclencheur est public et sans prérequis : BaseBillet/views.py:496-514 (_retrieve_v2_fedow_core, route /qr/<uuid>) appelle scanner_carte sur un tenant V2 dès qu'une carte vierge est scannée — aucun asset requis, aucune gate module. Donc un wallet client avec origin=tenant peut parfaitement exister AVANT la création du premier asset.

3) Le bug dans l'admin : fedow_core/admin.py:339-341, save_model fait Wallet.objects.filter(origin=tenant_actuel).first() sans order_by ni filtre name. Dans le scénario déclencheur (seuls des wallets clients existent), .first() retourne FORCÉMENT un wallet client, la branche de création (admin.py:343-349) est sautée, et obj.wallet_origin = wallet client (admin.py:351). Aucune validation au niveau modèle non plus (fedow_core/models.py:134-140, simple FK PROTECT).

4) Les conséquences financières sont confirmées : laboutik/views.py:5823, 6683, 7012 créditent receiver_wallet=asset_a_debiter.wallet_origin lors des ventes POS — le CA cashless irait sur le Token du client, dépensable à la caisse. Idem sender=asset.wallet_origin pour les virements (services.py:1113).

5) Preuve supplémentaire que l'auditeur a raison : la convention correcte existe déjà — WalletService.get_or_create_wallet_tenant (fedow_core/services.py:241-257, filtre origin=tenant ET name=f"Lieu {tenant.schema_name}") est utilisée par les refunds/BANK_TRANSFER (services.py:1109, laboutik/views.py:7436, Administration/views_cards.py:174) mais PAS par AssetAdmin.save_model. Pire : le fallback de l'admin (admin.py:346-349) crée un wallet avec name=tenant_actuel.name, divergent de la convention "Lieu {schema_name}" — même dans le cas heureux, le wallet_origin de l'asset et le wallet receveur des refunds peuvent être deux wallets différents (incohérence secondaire).

Sévérité "bloquant" justifiée : intégrité financière compromise (fonds du lieu crédités à un client et dépensables), déclenchable par une simple visite publique /qr/ avant la création du premier asset, silencieux (aucune erreur), et difficile à corriger après coup (wallet_origin posé une fois, FK PROTECT, nécessite migration de données). Fix évident : utiliser WalletService.get_or_create_wallet_tenant dans save_model.


### ✅ [MAJEUR] Fédération non câblée : federated_with (admin) vs Federation.assets (services) — deux mécaniques disjointes

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:92`

Le flow d'invitation per-asset de AssetAdmin (accept_asset_invitation, admin.py:444) remplit Asset.federated_with. Mais AssetService.obtenir_assets_accessibles (services.py:92-104) — utilisé par la cascade POS (laboutik/views.py:5542, 6505) — ne lit QUE Federation.tenants/Federation.assets. Or Federation.assets n'est JAMAIS peuplé en production : FederationAdmin exclude=['tenants','assets'] et seul demo_data_v2.py:3532 le remplit. Conséquence : accepter une invitation d'asset n'a AUCUN effet réel (la carte chargée au lieu A ne paye pas au lieu B), et l'affichage 'lieux utilisables' (BaseBillet/views.py:914, asset.federations) reste vide. verify_transactions utilise lui federated_with (3e convention).

**Recommandation :** Choisir UNE source de vérité (federated_with semble la plus simple) et faire converger obtenir_assets_accessibles, _lieux_utilisables_pour_asset et verify_transactions dessus ; ou synchroniser federated_with → Federation dans accept_asset_invitation.

**Contre-expertise (confiance haute)** : confirmé.
> Problème confirmé par lecture du code, aucune garde manquée par l'auditeur. (1) accept_asset_invitation (fedow_core/admin.py:444-445) écrit uniquement Asset.federated_with, jamais Federation.assets/tenants. (2) AssetService.obtenir_assets_accessibles (fedow_core/services.py:92-109) ne lit QUE Federation.tenants + Federation.assets, jamais Asset.federated_with ; c'est ce que consomme la cascade POS (laboutik/views.py:5542 et 6505). (3) Federation.assets n'est peuplé nulle part en production : FederationAdmin a exclude=["tenants","assets"] (fedow_core/admin.py:717) et son flow d'invitation ne fait que pending_tenants.remove()/tenants.add() ; seuls demo_data_v2.py:3532,3537 et tests/pytest/test_tokens_table_v2.py:188 font federation.assets.add(), ce qui masque le gap dans les tests/démo. (4) L'affichage "lieux utilisables" (BaseBillet/views.py:913-916) itère asset.federations→federation.tenants, donc ignore aussi federated_with. (5) verify_transactions.py:304 valide via federated_with — 3e convention incohérente avec la cascade. (6) fedow_core/signals.py ne contient aucune synchronisation entre les deux mécaniques. Conséquence vérifiée : accepter une invitation per-asset ne donne que la visibilité dans l'admin (queryset admin.py:215), sans effet sur le paiement cross-lieu ; et le flow Federation est lui-même inopérant pour partager un asset (M2M assets non éditable). Sévérité "majeur" justifiée : fonctionnalité cœur (cashless cross-lieu V2) inopérante en production, masquée par les fixtures de démo et les tests qui peuplent Federation.assets directement.


### ✅ [MAJEUR] Asset FED inaccessible à la vente POS par défaut (aucun cas spécial, aucune Federation bootstrap)

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:102`

obtenir_assets_accessibles ne special-case pas FED, et bootstrap_fed_asset ne crée aucune Federation reliant les tenants au FED (seul demo_data_v2 le fait). Scénario : un user recharge FED en ligne (refill_wallet V2, OK car RefillService prend Asset.objects.get(category=FED)), puis paye au POS d'un tenant V2 → la cascade (ORDRE_CASCADE_FIDUCIAIRE inclut FED, laboutik/views.py:3237) ne trouve pas l'asset FED dans assets_accessibles → SoldeInsuffisant alors que le wallet est plein. Asymétrie : rembourser_en_especes et views_cards._tokens_eligibles prennent FED SANS filtre d'origine (services.py:574) — remboursable partout mais dépensable nulle part.

**Recommandation :** Special-caser FED dans obtenir_assets_accessibles (comme dans rembourser_en_especes et _lieux_utilisables_pour_asset qui le traitent 'partout'), ou créer/maintenir une Federation FED globale au bootstrap et à la création de tenant.

**Contre-expertise (confiance haute)** : confirmé.
> Problème confirmé après lecture exhaustive du code, je n'ai trouvé aucune garde que l'auditeur aurait ratée.

1) Pas de cas spécial FED dans l'accessibilité : `obtenir_assets_accessibles` (fedow_core/services.py:92-111) ne retourne que `Q(tenant_origin=tenant) | Q(uuid__in=Federation.assets)`. L'asset FED a `tenant_origin=federation_fed` (bootstrap_fed_asset.py:79-87), donc il n'est accessible que via une Federation. Note : la méthode ignore aussi le mécanisme parallèle `Asset.federated_with` (models.py:203), mais FED n'y est de toute façon jamais ajouté.

2) Aucune Federation bootstrap : `bootstrap_fed_asset` (fedow_core/management/commands/bootstrap_fed_asset.py) crée tenant + root wallet + asset + Product/Price, mais AUCUNE Federation. `install.py:147` n'appelle que `bootstrap_fed_asset`. Seul `demo_data_v2.py:3507-3532` crée `fed_globale` avec l'asset FED, sur une liste hardcodée SCHEMAS_DEMO — données de démo uniquement. Aucune doc (fedow_core/*.md) ne prescrit de créer cette Federation en production.

3) La recharge n'est pas gardée : `peut_recharger_v2` (BaseBillet/views.py:805-840) ne vérifie que module_monnaie_locale et server_cashless — aucun check de fédération. `RefillService.process_cashless_refill` (services.py:1203, 1232-1241) prend `Asset.objects.get(category=Asset.FED)` et crédite inconditionnellement. Le scénario « wallet plein, dépense impossible » est donc déclenchable.

4) Cascade POS : ORDRE_CASCADE_FIDUCIAIRE inclut FED (laboutik/views.py:3237), mais la boucle (views.py:5551-5561, idem 6505+) fait `assets_accessibles.filter(category=FED).first()` → None pour un tenant non fédéré → le solde FED n'entre jamais dans soldes_cascade → hx_funds_insufficient/SoldeInsuffisant alors que le wallet est plein.

5) Asymétrie confirmée : `rembourser_en_especes` (services.py:567-577) et `vider_carte` (laboutik/views.py:7345-7356) prennent les tokens FED avec `Q(asset__category=Asset.FED)` SANS filtre de fédération — remboursable partout, dépensable nulle part par défaut.

6) Preuve d'intention contredite : `_lieux_utilisables_pour_asset` (BaseBillet/views.py:893-909) documente « Cas special FED : asset global, utilisable dans TOUS les lieux V2 » et affiche un badge « utilisable partout » à l'utilisateur. Le comportement POS contredit la promesse UI.

7) Pas d'échappatoire admin self-service : FederationAdmin exclut le champ assets (fedow_core/admin.py:717) ; AssetAdmin ne montre que les assets du tenant (admin.py:215), n'offre pas la catégorie FED à la création (admin.py:308-315) et rend FED non modifiable (admin.py:177). Seule une intervention shell/superadmin peut fédérer le FED.

Les tests passent uniquement parce que demo_data_v2 crée la fédération ou que test_cascade_nfc crée son propre asset — aucun test ne couvre le chemin production (install.py seul). Sévérité « majeur » justifiée : de l'argent réel encaissé par Stripe devient indépensable au POS sur toute installation fraîche, avec pour seules sorties le remboursement espèces ou une intervention manuelle en base.


### ❌ [MAJEUR] Critère de dispatch V1/V2 incohérent : `is not None` vs `bool()` sur server_cashless

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:829`

peut_recharger_v2 teste `config.server_cashless is not None` (l.829 et 837) alors que TOUS les autres dispatchs testent `bool(config.server_cashless)` (views.py:453, 598, 1143, 1169, 1356 ; dashboard.py:769). server_cashless est URLField(blank=True, null=True) (models.py:713) : un champ vidé via le form admin Django est sauvé comme chaîne vide '' et non NULL. Scénario migration : un tenant V1 migré vers V2 en vidant le champ dans l'admin devient V2 pour scan QR/link/lost_card/my_cards mais reste 'v1_legacy' pour refill/tokens_table/transactions_table → un même tenant exécute les deux moteurs simultanément. Idem 'wallet_legacy' : les users du tenant migré restent bloqués à vie.

**Recommandation :** Normaliser : un seul helper module-level `tenant_est_en_v1(config)` basé sur bool(), utilisé partout (y compris peut_recharger_v2), + une migration de données qui convertit '' en NULL.

**Contre-expertise (confiance haute)** : RÉFUTÉ.
> L'incohérence textuelle est confirmée (views.py:829 et :837 utilisent `is not None` ; views.py:453, 598, 1143, 1169, 1356 et Administration/admin/dashboard.py:769 utilisent `bool()`), MAIS le scénario de déclenchement de l'auditeur est faux. (1) `server_cashless` n'est PAS éditable via l'admin : `ConfigurationAdmin.fieldsets` (Administration/admin/configuration.py:265-314) n'inclut pas ce champ, donc impossible de le « vider via le form admin » et d'obtenir '' — Django ne rend ni ne sauve un champ hors fieldsets. L'admin root ne registre pas Configuration (admin_root.py:79 commenté). (2) Le chemin officiel de migration V1→V2 est la commande `reset_cashless_handshake` qui met explicitement `config.server_cashless = None` (Administration/management/commands/reset_cashless_handshake.py:59), pas ''. (3) Le seul autre écrivain est Onboard_laboutik (ApiBillet/views.py:936) qui écrit l'URL réelle du serveur LaBoutik. (4) Défaut du champ : URLField(blank=True, null=True) sans default → None à la création via get_solo(). Donc toutes les valeurs effectivement produites sont None ou une URL non vide, cas où `is not None` et `bool()` donnent le même verdict. Les tests (tests/pytest/test_peut_recharger_v2.py:120, :148, :166) confirment : V1 simulé avec une URL, V2 avec None, jamais ''. Le double-moteur simultané décrit n'est donc pas déclenchable par les chemins de code existants. Réserve non tranchable par lecture : une donnée historique '' en base de prod — mais ce n'est pas le scénario décrit. Recommandation : harmoniser vers `bool()` par défense en profondeur, sévérité réelle mineure (code smell), pas majeur.


### ❌ [MAJEUR] tokens_table / transactions_table : verdicts non-v2 routés vers FedowAPI → 500 sur tenant pur V2

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:1484`

tokens_table (l.1484) et transactions_table (l.1632) ne prennent la branche V2 que si verdict == 'v2'. Pour 'feature_desactivee' (module_monnaie_locale=False) ou 'wallet_legacy' (user au wallet V1 visitant un tenant V2), la branche V1 exécute FedowAPI() sur le tenant COURANT : sur un tenant pur V2, FedowConfig est vide → get_fedow_place_admin_apikey fait fernet_decrypt(None) / HTTP vers un Fedow inexistant → exception 500 sur la page /my_account/balance/ au lieu du message de migration (que refill_wallet, lui, gère correctement pour wallet_legacy).

**Recommandation :** Traiter explicitement chaque verdict : 'wallet_legacy' → partial message migration (comme refill_wallet), 'feature_desactivee' → table vide ; ne tomber sur FedowAPI que si verdict == 'v1_legacy'.

**Contre-expertise (confiance haute)** : RÉFUTÉ.
> Le routage décrit existe (views.py:1484 et 1632 : seuls les verdicts 'v2' prennent la branche fedow_core, les autres exécutent FedowAPI()), mais le scénario de 500 n'est pas déclenchable car la prémisse 'FedowConfig vide sur tenant pur V2' est fausse dans ce codebase. Tous les chemins de création de tenant exigent un handshake Fedow réussi : BaseBillet/validators.py:1059-1061 (TenantCreateValidator.create_tenant fait FedowAPI() puis raise si can_fedow()=False), install.py:196-198 et demo_data_v2.py:1995-1997 idem. Un tenant 'pur V2' (server_cashless=None, module_monnaie_locale=True) a donc toujours un FedowConfig peuplé, et le Fedow standalone est nécessairement up pendant la coexistence (requis pour créer tout tenant). La branche V1 de tokens_table/transactions_table fonctionne alors normalement — c'est le comportement pré-Session 32/33, documenté comme intentionnel (docstrings views.py:1474-1476 et 1622-1624 : 'Autres verdicts -> flow V1 FedowAPI (inchange)'). Pour wallet_legacy, afficher les tokens via le Fedow V1 est correct en lecture ; seul refill_wallet (écriture) doit bloquer, ce qu'il fait (views.py:1826). De plus, le mécanisme de crash cité est inexact : avec un FedowConfig vide, FedowAPI.__init__ instancie PlaceFedow (fedow_api.py:1074) dont le constructeur (fedow_api.py:659-661) auto-déclenche create_place() avec la clé root (get_fedow_create_place_apikey), pas fernet_decrypt(fedow_place_admin_apikey=None). Caveat : dans l'état cible de la fusion (Fedow standalone supprimé), ce dispatch redeviendra un point de vigilance pour le portage, mais create_tenant (validators.py:1059) casserait en premier — le portage devra traiter FedowConfig globalement. Sévérité réévaluée : non un bug majeur actuel, mais une note de vigilance pour le chantier de portage.


### ✅ [MAJEUR] enregistrer_virement écrit la LigneArticle comptable dans le schéma courant, pas celui du tenant cible

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:1131`

BankTransferService.enregistrer_virement crée la LigneArticle d'encaissement (modèle TENANT_APPS) via le schéma de connexion courant, sans tenant_context(tenant). Or le caller views_bank_transfers.py:98 (dashboard superuser) accepte un tenant_uuid ARBITRAIRE : un superuser qui navigue sur l'admin du lieu A et enregistre un virement pour le lieu B crée la Transaction BANK_TRANSFER avec tenant=B (correct, SHARED) mais la LigneArticle atterrit dans le schéma de A → comptabilité du virement attribuée au mauvais lieu, rapports/exports FEC faussés des deux côtés.

**Recommandation :** Encapsuler la création de la LigneArticle (et get_or_create_product_virement_recu) dans `with tenant_context(tenant):` à l'intérieur de enregistrer_virement.

**Contre-expertise (confiance haute)** : confirmé.
> Confirmé par lecture. (1) BaseBillet est en TENANT_APPS (TiBillet/settings.py:176) donc LigneArticle/Product/PriceSold sont per-schema. (2) BankTransferService.enregistrer_virement (fedow_core/services.py:1100-1146) crée la Transaction BANK_TRANSFER avec tenant=cible (SHARED, correct) mais crée LigneArticle (ligne 1131) + Product système via get_or_create_product_virement_recu (BaseBillet/services_refund.py:90) dans le schéma de connexion courant, sans tenant_context — aucune protection. (3) Le caller views_bank_transfers.py:98 (superuser-only) accepte un tenant_uuid arbitraire : le serializer (Administration/serializers.py:43-47) valide juste l'existence du Client, sans comparer à connection.tenant ; la route est montée sur StaffAdminSite (Administration/admin/site.py:48-57) donc accessible depuis l'admin de N'IMPORTE QUEL tenant, et le dashboard liste les dettes de tous les tenants — la saisie cross-tenant est le flux nominal, pas un abus. (4) Preuve que c'est un oubli et non un design : le même fichier utilise tenant_context(tenant_origine) pour Membership dans CardService.lier_a_user (services.py:1437). (5) Le test existant (tests/pytest/test_bank_transfer_service.py:210-261) masque le bug : il enveloppe tout dans schema_context('lespass') avec le tenant lespass, seul cas où schéma courant == tenant cible. Conséquence : la LigneArticle d'encaissement (wallet=wallet du tenant cible, donc comptablement à lui) atterrit dans les livres du tenant où navigue le superuser → rapports et exports FEC faussés des deux côtés, plus un Product parasite « Virement pot central » créé dans le mauvais schéma. Sévérité « majeur » confirmée : intégrité comptable cassée en usage nominal, mais acteur superuser de confiance et pas de fuite en lecture.


### ✅ [MAJEUR] refund_online sans aucun dispatch V1/V2 (FedowAPI direct)

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:1400`

MyAccount.refund_online appelle directement fedowAPI.wallet.cached_retrieve_by_signature puis refund_fed_by_signature, sans dispatch server_cashless ni peut_recharger_v2. Sur un tenant V2 (FedowConfig vide), l'action crashe ou tente un remboursement sur le Fedow distant alors que les tokens FED V2 sont locaux dans fedow_core. Il n'existe aucun équivalent V2 self-service du refund FED (rembourser_en_especes est admin-only, et le suivi de dette BankTransferService suppose des REFUND admin). Un user V2 qui a rechargé en ligne n'a aucun chemin de remboursement en ligne.

**Recommandation :** Ajouter le dispatch (verdict v1_legacy → code actuel) et soit masquer le bouton côté template pour V2, soit implémenter le refund FED V2 (Transaction REFUND + remboursement Stripe via Paiement_stripe de federation_fed).

**Contre-expertise (confiance haute)** : confirmé.
> Problème confirmé par lecture du code. (1) BaseBillet/views.py:1400-1440 : refund_online appelle FedowAPI().wallet.cached_retrieve_by_signature (l.1404) puis refund_fed_by_signature (l.1417) sans aucun dispatch — aucun appel à peut_recharger_v2 ni lecture de server_cashless, alors que TOUS les endpoints voisins du ViewSet MyAccount en ont un (tokens_table l.1480, my_cards l.1143, declare_lost l.1356, refill_wallet l.1800, refill_wallet_submit l.1882, retour Stripe l.2079). (2) Le bouton est bien exposé aux users V2 : page vivante /my_account/balance/ (views.py:1101) → tirelire_section.html:28-79 et 130-142, conditionné uniquement par config.show_refill_button (BaseBillet/models.py:847, dépend de stripe_payouts_enabled, pas du mode V1/V2) ; le bouton « Send request » fait hx-get /my_account/refund_online/ (tirelire_section.html:67). (3) Sur tenant V2 sans Fedow distant : retrieve_by_signature (fedow_connect/fedow_api.py:536-553) fait un HTTP _get vers fedow_domain → exception re-raise (fedow_api.py:530-531), refund_online n'a aucun try/except → 500. Avec Fedow distant (coexistence), le wallet V2 local n'y existe pas : les tokens FED locaux fedow_core ne sont jamais remboursés. (4) Aucun équivalent V2 self-service : fedow_core/services.py:503 rembourser_en_especes est appelé uniquement depuis Administration/views_cards.py:177 (admin) et laboutik/views.py:7439 (POS). (5) L'asymétrie est réelle : la recharge en ligne V2 existe (refill_wallet branche v2, views.py:1840+) — l'user V2 peut charger de l'argent réel via Stripe mais n'a aucun chemin de remboursement en ligne. (6) Aucun test ne couvre refund_online. La sévérité « majeur » est appropriée : crash user-facing + argent réel non récupérable en self-service, mais pas de corruption de données ni de faille de sécurité.


### ✅ [MAJEUR] _obtenir_ou_creer_wallet (POS) duplique scanner_carte sans verrou et avec origin=tenant scannant

`/home/jonas/TiBillet/dev/lespass-main/laboutik/views.py:965`

Le helper POS crée le wallet éphémère d'une carte vierge SANS transaction.atomic ni select_for_update, contrairement à CarteService.scanner_carte (services.py:1322) qui fait du double-check locking précisément pour éviter la double création (deux scans simultanés → deux wallets, le perdant devient orphelin avec ses éventuels tokens crédités). De plus origin=connection.tenant (lieu qui scanne) au lieu de carte.detail.origine (convention de scanner_carte) : pour une carte du lieu A scannée au POS du lieu B, le wallet est rattaché à B, ce qui fausse ensuite le verdict 'wallet_legacy' de peut_recharger_v2 (basé sur user.wallet.origin) et l'attribution du lieu d'origine.

**Recommandation :** Supprimer le doublon et appeler CarteService.scanner_carte(carte, carte.detail.origine) depuis laboutik.

**Contre-expertise (confiance haute)** : confirmé. Sévérité réévaluée : moyen.
> CONFIRMÉ pour la race, RÉFUTÉ pour l'impact sur peut_recharger_v2.

1) Race de double création : réelle. `_obtenir_ou_creer_wallet` (laboutik/views.py:965-999) lit `carte.wallet_ephemere` puis fait `Wallet.objects.create(...)` + `carte.save(update_fields=["wallet_ephemere"])` sans `select_for_update` ni double-check. Certains appelants sont dans un `transaction.atomic()` (ex: views.py:5182→5216, 5357→5391), mais en READ COMMITTED l'atomic seul n'empêche pas deux requêtes concurrentes de voir toutes deux `wallet_ephemere=None` et de créer deux wallets (dernier save gagne, l'autre devient orphelin avec ses tokens crédités dans la même transaction par `_executer_recharges`). L'appelant check_carte (views.py:7216) n'est même dans aucun bloc atomic. Aucune contrainte DB ne protège : le OneToOne sur wallet_ephemere n'interdit que deux cartes pointant le même wallet, pas deux wallets successifs pour la même carte. Le codebase lui-même considère ce risque comme réel : `CarteService.scanner_carte` (fedow_core/services.py:1322-1333) fait exactement le verrou + double-check pour ce scénario (docstring 1287-1293), et `lier_a_user` verrouille aussi la carte (services.py:1394). Le helper POS est donc une régression de convention par rapport au service V2 existant.

2) Incohérence origin : réelle mais conséquence annoncée fausse. La convention est bien `tenant_origine = carte.detail.origine` (BaseBillet/views.py:438→502) alors que le POS met `origin=connection.tenant` (views.py:993). MAIS le verdict `wallet_legacy` de `peut_recharger_v2` (BaseBillet/views.py:834-838) lit `user.wallet.origin`, et le wallet éphémère ne devient JAMAIS `user.wallet` : `fusionner_wallet_ephemere` (fedow_core/services.py:372-378) crée un NOUVEAU wallet avec `origin=tenant` passé par l'appelant (lier_a_user passe `carte.detail.origine`, services.py:1398+1429), transfère les tokens puis détache l'éphémère. Aucun lecteur de `Wallet.origin` sur les wallets éphémères n'a été trouvé (grep fedow_core + laboutik) : l'impact réel est limité à l'audit/traçabilité du champ, pas au verdict V1/V2.

Sévérité réévaluée : la race est déclenchable uniquement au tout premier scan d'une carte vierge avec deux requêtes simultanées (deux POS ou double-submit HTMX) — fenêtre courte, probabilité faible, tokens orphelins récupérables en DB (transactions tracées). Conséquence financière possible mais rare, et la moitié de l'impact annoncé (peut_recharger_v2) est infondée → moyen plutôt que majeur. Fix trivial : faire déléguer le helper POS à `CarteService.scanner_carte`.


### · [MINEUR] POS V2 : aucune vérification d'origine/fédération de la carte scannée (parc CarteCashless partagé)

`/home/jonas/TiBillet/dev/lespass-main/laboutik/views.py:5520`

Le POS charge CarteCashless.objects.get(tag_id=...) sans vérifier que la carte appartient au tenant courant ou à un lieu fédéré (le flow web /qr/ force lui le redirect vers le domaine d'origine, views.py:443). Scénario : carte d'origine V2-A scannée chez V2-B non fédéré → wallet éphémère créé avec origin=B, recharges/débits possibles chez B sur les assets de B. Carte d'un tenant V1 scannée chez un tenant V2 : si carte.user.wallet existe (miroir local V1), le POS lit des Tokens fedow_core vides → 'carte vide' trompeur alors que le vrai solde vit dans le Fedow distant ; une recharge POS créditerait un wallet dont les soldes V1 sont ailleurs.

**Recommandation :** Au scan POS, vérifier carte.detail.origine ∈ {tenant courant} ∪ fédérés, et refuser (ou avertir) les cartes dont le tenant d'origine est V1 (server_cashless renseigné).

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] list_filter ['asset'] non borné au tenant dans TokenAdmin et TransactionAdmin

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/admin.py:518`

TokenAdmin.list_filter=['asset'] (l.518) et TransactionAdmin.list_filter=['action','asset'] (l.591) utilisent le RelatedFieldListFilter par défaut de Django, qui liste TOUS les Asset de l'instance dans le dropdown (Asset.objects.all()), pas seulement ceux du queryset filtré. Un admin de tenant A voit donc les noms de toutes les monnaies locales des autres lieux (info non publique, contrairement aux noms de tenants). Le queryset des résultats reste correctement filtré.

**Recommandation :** Utiliser admin.RelatedOnlyFieldListFilter ou un SimpleListFilter custom limité à AssetService.obtenir_assets_du_tenant(connection.tenant).

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Panel refund admin : historique des transactions du wallet sans filtre tenant

`/home/jonas/TiBillet/dev/lespass-main/Administration/views_cards.py:84`

_transactions_recentes filtre Q(sender=wallet)|Q(receiver=wallet) sans filtre Transaction.tenant : l'admin du lieu d'origine de la carte voit les 15 dernières transactions du porteur TOUS lieux confondus (montants, assets, horodatages des achats faits chez d'autres tenants fédérés ou non). Le commentaire 'REGLE CRITIQUE : toujours filtrer par tenant' du modèle (models.py:625) n'est pas appliqué ici. Le check d'accès carte (origine == tenant) est lui correct.

**Recommandation :** Décider explicitement : soit filtrer tenant=connection.tenant, soit documenter que l'historique complet du wallet est volontairement visible par le lieu d'origine de la carte (utile au remboursement).

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Redirect /qr/ vers le domaine d'origine par test de sous-chaîne

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:444`

`if primary_domain.domain not in request.build_absolute_uri()` est un test de sous-chaîne : si le domaine primaire du tenant d'origine est un suffixe d'un autre domaine de l'instance (ex. 'art.tibillet.coop' ⊂ 'part.tibillet.coop'), le redirect est sauté et le scan est servi sur le mauvais tenant — le tenant_context(tenant_origine) protège le dispatch et la lecture de Configuration, mais get_context(request), le render et le login(request, user) se font sur le domaine/la session du mauvais tenant.

**Recommandation :** Comparer le host exact : `request.get_host().split(':')[0] != primary_domain.domain` avant de rediriger.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Panneau de remboursement V2 (fedow_core) affiché sans dispatch aux admins de tenants V1

`/home/jonas/TiBillet/dev/lespass-main/Administration/admin/cards.py:234`

CarteCashlessAdmin.change_form_before_template et CardRefundViewSet (panel/modal/confirm) ne dispatchent jamais sur server_cashless : un admin d'un tenant V1 voit le panneau 'Rembourser' basé sur les Tokens fedow_core (vides pour lui, ses soldes vivant dans le Fedow distant) → affichage 'aucun solde remboursable' trompeur sur des cartes pourtant chargées côté V1. NoEligibleTokens empêche heureusement le reset vider_carte de s'exécuter, mais le jour où des tokens V2 apparaissent (carte mixte), le refund local serait exécutable en parallèle du solde V1 distant.

**Recommandation :** Masquer le panneau (ou afficher un message explicite) quand bool(config.server_cashless) est vrai sur le tenant courant.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] get_or_create_wallet_tenant : pas de contrainte d'unicité ni de verrou, et nom dépendant de schema_name

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:253`

Wallet.objects.get_or_create(origin=tenant, name=f'Lieu {schema_name}') sans contrainte unique en base : deux requêtes concurrentes (ex. deux refunds admin simultanés) peuvent créer deux wallets 'Lieu X', puis les appels suivants lèvent MultipleObjectsReturned (get_or_create fait un .get()). De plus la clé fonctionnelle inclut schema_name : un changement de convention de nommage créerait un second wallet lieu et splitterait dette BANK_TRANSFER et REFUND entre deux wallets.

**Recommandation :** Avant le portage : ajouter une vraie convention (ex. FK Client.wallet OneToOne, comme noté dans la docstring) ou au minimum une UniqueConstraint(origin, name) + gestion d'IntegrityError.

_Non contre-expertisé (sous le seuil majeur)._


### · [INFO] admin_my_cards expose tous les soldes multi-lieux d'un user à l'admin du tenant courant

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:1190`

La branche V2 de admin_my_cards liste Token.objects.filter(wallet=user.wallet, asset__active=True, value__gt=0) sans filtre tenant : l'admin du lieu B voit le solde de monnaie locale du lieu A détenu par l'user. C'est la parité avec V1 (le Fedow distant renvoyait aussi tout le wallet), donc probablement assumé — à confirmer comme décision explicite plutôt qu'héritage.

**Recommandation :** Confirmer le choix ; sinon filtrer sur AssetService.obtenir_assets_accessibles(connection.tenant) + FED.

_Non contre-expertisé (sous le seuil majeur)._


---

## Gap fonctionnel — 12 flux V1 vs V2 + sortie adhésions/badges

**Synthèse de l'auditeur :** Matrice des 12 flux V1 → V2 dans lespass-main (base du portage) : PORTÉ avec dispatch propre pour la recharge Stripe FED (peut_recharger_v2 + RefillService + webhook ApiBillet:1141), les cartes NFC côté my_account (scan QR, liaison, perte, liste — CarteService), les soldes/historiques (tokens_table_v2, transactions_table_v2), la fédération V2 (fedow_core.Federation + flow invitation) et l'admin assets V2 (fedow_core/admin.py sous module_monnaie_locale). L'adhésion vendue en caisse V2 est saine : laboutik crée la Membership directement (status LABOUTIK) et la vérifie au scan NFC via Membership.is_valid() — la décision 3 fonctionne pour ce chemin. Les dépôts bancaires V2 sont couverts par BankTransferService (dette pot central + virements). En revanche, 3 flux sont ABSENTS (badge/pointeuse, paiement QR/NFC caisse, rewards/gift) et 4 PARTIELS (remboursement en ligne, adhésion web/admin, wallet — création encore 100% V1 HTTP, webhook transfer.created). Le point le plus structurant : la création de tenant ET de wallet user exige toujours le serveur Fedow distant (can_fedow obligatoire), ce qui contredit la cible « nouveaux tenants V2 autonomes » et crée une comptabilité double (tokens locaux fedow_core + tokens distants Fedow pour le même user). Côté migration, aucune commande d'import n'existe encore et le webhook adhésion de Fedow est fire-and-forget sans retry : la réconciliation SUB ↔ Membership avant suppression des assets SUB/BDG est indispensable pour ne pas perdre d'adhésions payées.


### ⏳ [BLOQUANT] Création de tenant et de wallet user exige toujours le serveur Fedow distant

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/validators.py:1059`

La décision 2 dit 'nouveaux tenants = V2 automatiquement', mais dans lespass-main la création de tenant lève une exception si FedowConfig.can_fedow() est False (validators.py:1059-1060, idem install.py:197-198). De plus MyAccount.dispatch (BaseBillet/views.py:1059-1061) appelle FedowAPI().wallet.get_or_create_wallet() en HTTP vers Fedow distant pour tout user sans wallet, sans dispatch V1/V2 — get_or_create_wallet raise si status != 200/201 (fedow_api.py:597) donc 500 sur /my_account/ dès que Fedow est éteint ou injoignable. Toute la création de Wallet user V2 dépend aujourd'hui de ce chemin V1 : le flux refill V2 (refill_wallet_submit) suppose user.wallet déjà créé par ce passage HTTP. Tant que ce couplage existe, impossible d'avoir un tenant V2 réellement autonome et impossible d'éteindre Fedow.

**Recommandation :** Créer un WalletService.get_or_create_wallet_user() local dans fedow_core (le pattern existe déjà pour le tenant : get_or_create_wallet_tenant) et dispatcher MyAccount.dispatch ; rendre le handshake Fedow optionnel à la création de tenant (uniquement pour les tenants V1).

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Flux 5 badge/pointeuse : ABSENT en V2, aucun remplacement

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:3471`

La vue Badge.badge_in appelle FedowAPI().badge.badge_in(user, product) sans aucun dispatch V1/V2. Or fedow_core V2 a explicitement retiré les catégories BDG et SUB (fedow_core/models.py:61-63) et il n'existe aucun modèle de pointage de remplacement (aucune occurrence 'badge' fonctionnelle dans fedow_core ni laboutik). Scénario : un user d'un tenant V2 clique 'badge in' sur la page punchclock → écriture sur le Fedow distant tant qu'il tourne (données jamais réimportées), puis crash/erreur quand Fedow sera éteint. La fonctionnalité pointeuse n'a pas de chemin V2 du tout.

**Recommandation :** Décider du sort de la pointeuse : soit un modèle BadgeEvent simple dans BaseBillet (user, product, datetime), soit retirer la feature pour les tenants V2 (masquer l'onglet punchclock). Dans tous les cas, exporter l'historique BDG de Fedow avant extinction.

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Flux 7 paiement QR/NFC caisse (to_place_from_qrcode) : ABSENT en V2

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:2265`

Tout le flux QrCodeScanPay est V1-only sans dispatch : fedowAPI.transaction.to_place_from_qrcode (views.py:2265 process_with_nfc et :2462 valid_payment), get_or_create_wallet + get_total_fiducial_and_all_federated_token (views.py:2395-2398 et 2446-2449), et QrCodeScanPayNfcValidator qui appelle NFCcard.card_tag_id_retrieve en HTTP (validators.py:1118). fedow_core a pourtant tout ce qu'il faut (TransactionService.creer_vente, WalletService.obtenir_total_en_centimes, CarteCashless en SHARED_APPS interrogeable par tag_id). Scénario : tenant V2 génère un QR de paiement, le client paye avec son wallet local fedow_core → la transaction part vers le Fedow distant qui ne connaît pas les tokens locaux V2 → solde incohérent ou échec.

**Recommandation :** Porter le flux avec dispatch tenant_est_en_v1 : résolution carte par tag_id en DB directe (CarteCashless + CarteService.scanner_carte), solde via WalletService, débit via TransactionService.creer_vente avec la cascade d'assets.

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Flux 3 remboursement en ligne (refund_fed_by_signature) : pas de branche V2

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:1401`

refund_online appelle cached_retrieve_by_signature puis refund_fed_by_signature en HTTP V1 sans dispatch. Le V2 couvre uniquement le remboursement en espèces au POS/admin (WalletService.rembourser_en_especes, REFUND.md). Or le flux V2 de recharge (RefillService) encaisse les euros sur le pot central Stripe et crédite des tokens FED locaux : un user de tenant V2 qui clique 'remboursement' dans my_account déclenche un appel vers le Fedow distant qui ne connaît pas ses tokens FED locaux → message d'erreur 'You do not have a federated wallet' au mieux. Aucun chemin de remboursement Stripe self-service pour le FED V2, alors que l'argent est bien chez Stripe côté pot central.

**Recommandation :** Implémenter une branche V2 de refund_online : lecture Token FED local, stripe.Refund (ou Transfer reversal) depuis le compte du pot central, Transaction(action=REFUND) via TransactionService, en réutilisant le contrat PSP_INTERFACE.md. Sinon masquer le bouton pour les tenants V2 et documenter 'espèces uniquement'.

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Flux 8 récompenses/gift : aucun équivalent V2 + FK fedow_reward_asset incohérente

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/tasks.py:1869`

Les deux tâches Celery de reward (refill_from_lespass_to_user_wallet_from_price_solded tasks.py:1869, et from_ticket_scanned tasks.py:1820+) sont V1-only, gardées par FedowConfig.can_fedow(). Incohérence de modèle : Price.fedow_reward_asset pointe vers fedow_public.AssetFedowPublic (V1, models.py:1935) alors que Price.asset pointe vers fedow_core.Asset (V2, models.py:1958) — un tenant V2 ne peut donc même pas configurer un reward sur ses assets locaux TNF/FID. En plus, l'endpoint api_v2 de gift refill présent dans le repo cible (Lespass/api_v2/views.py:473-531, ExternalApiKey.gift_asset) n'existe pas du tout dans lespass-main : à la fusion il faudra le dispatcher alors qu'aucun service fedow_core équivalent n'est câblé.

**Recommandation :** Créer le pendant V2 (TransactionService.creer pour transfert wallet_tenant → wallet_user sur asset TNF/FID local), ajouter un second FK fedow_reward_asset_v2 vers fedow_core.Asset (ou migrer le champ), et dispatcher les 2 tâches + l'endpoint api_v2 gift.

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Admin V1 des assets (AssetFedowPublic) toujours visible et crashe sans Fedow

`/home/jonas/TiBillet/dev/lespass-main/Administration/admin/fedow.py:91`

AssetAdmin.get_queryset appelle inconditionnellement FedowAPI().asset.get_accepted_assets() qui fait un GET HTTP et raise Exception si la réponse n'est pas 200 (fedow_api.py:180-189) → la changelist admin renverra 500 pour TOUS les tenants (V1 et V2) dès que Fedow standalone sera éteint. La section sidebar 'Fédération > Assets' est marquée 'Toujours visible' (Administration/admin/dashboard.py:555-580), sans condition server_cashless ni module. Conséquence supplémentaire : un tenant V2 avec module_monnaie_locale voit DEUX systèmes d'assets/fédération concurrents dans la sidebar (Fedow V2 fedow_core_asset + Fédération V1 fedow_public_assetfedowpublic), avec deux flows d'invitation différents — confusion garantie et risque de fédérer dans le mauvais système.

**Recommandation :** Conditionner la section sidebar V1 à bool(config.server_cashless), et dans AssetAdmin.get_queryset entourer get_accepted_assets() d'un try/except non bloquant (la sync distante ne doit jamais casser l'affichage).

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Onboard_laboutik peut basculer silencieusement un tenant V2 actif en V1

`/home/jonas/TiBillet/dev/lespass-main/ApiBillet/views.py:910`

Onboard_laboutik (AllowAny) pose config.server_cashless sur le tenant. Sa seule garde est 'déjà configuré' (server_cashless ou key_cashless déjà présents). Or TOUT le dispatch V1/V2 repose sur bool(config.server_cashless) (peut_recharger_v2, scan carte, tokens_table, etc.). Scénario : un tenant V2 utilise la caisse interne laboutik et a déjà des Token/Transaction fedow_core locaux ; quelqu'un onboarde un LaBoutik externe → server_cashless est posé → le tenant devient 'V1' pour tous les dispatchs, ses tokens fedow_core deviennent invisibles (verdict v1_legacy), et les wallets créés localement passent en wallet_legacy pour les autres tenants. Corruption fonctionnelle silencieuse, difficile à diagnostiquer.

**Recommandation :** Refuser l'onboarding externe (409) si le tenant a module_caisse/module_monnaie_locale actifs ou si des fedow_core.Transaction existent pour ce tenant. Symétrique de la garde déjà présente côté dashboard (carte caisse disabled si server_cashless).

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Adhésion : formulaire admin et trigger web encore 100% V1

`/home/jonas/TiBillet/dev/lespass-main/Administration/admin/membership.py:122`

Le flux adhésion caisse V2 est bien porté (laboutik crée Membership directe, statut LABOUTIK, vérif au scan via Membership.is_valid — laboutik/views.py:4214+, 7256). MAIS : (1) le formulaire admin 'ajouter une adhésion' fait FedowAPI().wallet.get_or_create_wallet + cached_retrieve_by_signature dans clean_email (membership.py:122-124) et card_number_retrieve/linkwallet_card_number (l.143-145, 192) en HTTP sans dispatch → la création manuelle d'adhésion en admin cassera pour tout tenant quand Fedow sera éteint ; (2) Trigger_A (BaseBillet/triggers.py:190-194) appelle fedowAPI.membership.create pour chaque adhésion web — non bloquant (try/except) mais continue de créer des assets/tokens SUB sur le Fedow distant pour les tenants V2, à rebours de la décision 3, et génère un log d'erreur par adhésion une fois Fedow éteint ; idem signal send_membership_product_to_fedow (signals.py:419-436) à chaque save d'un Product ADHESION.

**Recommandation :** Dispatcher clean_email/clean_card_number sur tenant_est_en_v1 (branche V2 : wallet local + CarteCashless en DB directe) ; dans Trigger_A et le signal produit, ne faire l'appel Fedow que si config.server_cashless est renseigné.

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Import V1→V2 : sort des tokens/transactions SUB et BDG indéfini, webhook adhésion non fiable

`/home/jonas/TiBillet/dev/Fedow/fedow_core/signals.py:26`

fedow_core/management ne contient que bootstrap_fed_asset et verify_transactions : aucune commande d'import des données Fedow, et la décision 3 supprime SUB/BDG sans spécifier leur devenir. Risque concret : côté Fedow, l'adhésion vendue en caisse V1 notifie Lespass par un webhook fire-and-forget (signals.py:26-28 — requests.get sans timeout, sans vérification du status, sans retry) ; toute panne réseau ou indisponibilité Lespass au moment de la vente laisse une Transaction SUBSCRIBE dans Fedow SANS Membership correspondante dans Lespass. Si l'import jette les SUB sans réconciliation, ces adhésions payées disparaissent définitivement. Idem pour Membership.asset_fedow (Lespass models.py:3063) qui référence des uuid d'assets SUB voués à disparaître, et pour l'historique de pointage (transactions BADGE) qui n'existe QUE dans Fedow.

**Recommandation :** Spécifier dans le plan d'import : (1) réconciliation Transaction SUBSCRIBE Fedow ↔ BaseBillet.Membership avant suppression, avec création des Membership manquantes ; (2) export d'archive des transactions BDG ; (3) nettoyage/dépréciation de Membership.asset_fedow.


### ⏳ [MAJEUR] Comptabilité double pendant la coexistence : un tenant V2 écrit dans les deux systèmes

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:805`

Conséquence cumulative des flux non dispatchés : un tenant 'V2' (server_cashless vide) écrit ses recharges et ventes caisse dans fedow_core local (Token/Transaction), mais ses rewards, badges, paiements QR, adhésions web (SUB) et wallets users partent encore vers le Fedow distant (tenant créé avec handshake obligatoire, donc can_fedow=True). Le solde affiché par tokens_table_v2 (lecture locale uniquement) ignore les tokens distants, et inversement le Fedow distant ignore les tokens locaux. Un même user peut donc avoir deux soldes disjoints selon la page/flux, sans aucun mécanisme de réconciliation. Ce n'est pas un bug d'un fichier précis mais l'état émergent de la matrice : 5 flux PORTÉ, 4 PARTIEL, 3 ABSENT.

**Recommandation :** Avant d'ouvrir des tenants V2 en prod : soit compléter le dispatch sur TOUS les flux qui écrivent de la valeur (badge, QR pay, rewards, refund, wallet), soit désactiver explicitement ces features pour les tenants V2 (404/feature flag) tant qu'elles ne sont pas portées. Aucun flux ne doit pouvoir écrire dans le mauvais système.


### · [MINEUR] Webhook Stripe transfer.created (dépôts bancaires) sans dispatch V2

`/home/jonas/TiBillet/dev/lespass-main/ApiBillet/views.py:1402`

Le webhook transfer.created appelle fedowAPI.wallet.global_asset_bank_stripe_deposit (HTTP V1) pour le tenant correspondant au compte Stripe Connect, sans vérifier si ce tenant est V1 ou V2. Le mécanisme V2 équivalent existe (BankTransferService : calcul de dette du pot central + enregistrer_virement, câblé dans Administration/views_bank_transfers.py et le dashboard) mais ne traite pas ce webhook. Si un transfert Stripe vise un tenant V2, l'écriture part vers le Fedow distant ; quand Fedow sera éteint, le webhook échouera et Stripe rejouera indéfiniment.

**Recommandation :** Ajouter le dispatch dans le webhook : tenant V2 → BankTransferService.enregistrer_virement (ou no-op documenté si le virement V2 est déclaré manuellement en admin), tenant V1 → flux actuel.

_Non contre-expertisé (sous le seuil majeur)._


### · [INFO] Champs et code morts après la sortie des adhésions/badges des assets

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/models.py:4145`

À cartographier pour le nettoyage post-portage : Membership.asset_fedow (lespass-main models.py:4145, Lespass models.py:3063), webhook entrant Membership_fwh (fedow_connect/views.py:26 — encore nécessaire pour les tenants V1, à supprimer en Phase 7), get_or_create_membership_asset (fedow_api.py:222), signal send_membership_product_to_fedow (signals.py:419), classes BadgeFedow/MembershipFedow de fedow_api.py, et côté Fedow create_membership_asset/create_membership/badge (views.py:211, 267, 719, 1571, 1641). Le filtre .exclude(category in [BADGE, SUBSCRIPTION]) de l'admin V1 (Administration/admin/fedow.py:101) montre que ces assets sont déjà cachés de l'UI — leur suppression ne change rien pour l'admin V1.

**Recommandation :** Lister ces éléments dans le plan Phase 7 (suppression V1) avec, pour chacun, la condition de retrait : 'plus aucun tenant avec server_cashless renseigné'.

_Non contre-expertisé (sous le seuil majeur)._


---

## Migration des données (500 lieux, SQLite → PostgreSQL)

**Synthèse de l'auditeur :** Le découpage tenant-par-tenant du graphe Fedow est partiellement réaliste, mais pas pour la monnaie fédérée. Données prod (snapshot 09/06) : 398 places, 38 159 wallets, 145 763 transactions, 36 870 tokens. Bonne nouvelle : 301 places sur 398 n'ont AUCUNE transaction (rien à importer), et la plupart des places actives n'utilisent que des assets locaux non fédérés — pour elles, la tranche {asset + transactions + tokens + wallets référencés} est extractible proprement tenant par tenant (les wallets/users étant partagés, l'import doit juste être idempotent par uuid). En revanche : (1) l'asset FED est accepté par toutes les places et lie 22 places actives et 2 472 wallets porteurs — sa migration doit être une bascule unique coordonnée, pas incrémentale ; (2) les fédérations locales (CLAFoutils : 36 places) imposent de migrer par fédération entière ; (3) le Fedow prod sert DEUX instances Lespass (.coop et .re) plus 31 places au domaine 'None' — le périmètre même de la DB cible est à trancher avant tout. Prérequis durs : lancer reconcile_tokens en prod (les Token.value sont faux de ~1 400 €, les CORRECTION n'existent pas encore) puis recalculer/vérifier les soldes à l'import ; normaliser la sémantique débit/crédit (REFUND/DEPOSIT V1 ne créditent pas le receiver, le recalcul V2 si) ; mapper les codes action (REF→RFL, BNK→DEP, COR absent de V2) ; affecter un tenant aux ~27 700 transactions sans lieu (pot central, fusions) ; réconcilier le pot central V2 (uuid neuf) avec l'ancien primary wallet. Points vérifiés sains : Wallet.uuid Lespass = uuid Fedow (fedow_api.get_or_create_wallet), emails Fedow normalisés sans doublon, hash/uuid de transactions stables et uniques, forks de chaîne non bloquants (V2 abandonne le chaînage, hash=null + migrated=True), volumes compatibles avec un import ORM en quelques heures. Unité de migration recommandée : vagues tenant-par-tenant pour les lieux à assets locaux purs, vagues par fédération pour les assets partagés, et big-bang final pour le périmètre FED (22 places + pot central + tokens FED), après gel court du standalone.


### ✅ [BLOQUANT] L'asset FED forme un composant connexe global : impossible à découper tenant par tenant

`/home/jonas/TiBillet/dev/Fedow/fedow_core/models.py:970`

federated_with() ajoute automatiquement l'asset STRIPE_FED_FIAT à TOUTES les places (ligne 970) : tout lieu accepte la monnaie fédérée. Mesuré en prod : 46 127 transactions FED, 2 472 wallets users avec solde FED > 0, 22 places avec activité FED (18 .coop, 4 .re). Le token FED d'un user est un objet GLOBAL : si on importe son solde dans fedow_core V2 au moment où le lieu A migre, mais que le lieu B (resté V1) continue d'accepter ce même solde via le Fedow standalone, on a deux registres divergents pour le même argent — double dépense possible, soldes irréconciliables au moment de migrer B. Le garde peut_recharger_v2 (lespass-main BaseBillet/views.py:805, verdict wallet_legacy sur wallet.origin) bloque la recharge mais pas la coexistence de deux soldes FED parallèles.

**Recommandation :** Le périmètre FED doit migrer d'un bloc : bascule coordonnée des 22 places à activité FED + pot central + tokens FED des 2 472 wallets, avec gel des transactions FED côté standalone pendant l'import. Les tenants à assets purement locaux peuvent migrer individuellement AVANT, à condition de ne pas importer leur token FED (le laisser sur le standalone jusqu'à la bascule finale).

**Contre-expertise (confiance haute)** : confirmé. Sévérité réévaluée : bloquant pour la Phase 6 (plan d'import tel qu'écrit) — mais non déclenchable aujourd'hui, aucune commande d'import n'est implémentée ; aucun impact sur le code en production actuelle.
> CONFIRMÉ par lecture du code et des plans. (1) Fedow/fedow_core/models.py:970 : federated_with() ajoute inconditionnellement l'asset STRIPE_FED_FIAT aux assets acceptés de chaque Place, et lignes 1155-1158 garantissent l'unicité du FED — le FED est bien un objet global, tout lieu V1 l'accepte. (2) Le garde peut_recharger_v2 (lespass-main/BaseBillet/views.py:805-840) ne bloque que la RECHARGE (verdict wallet_legacy, lignes 834-838) ; le chemin de DÉPENSE V2 (laboutik/views.py, _payer_par_nfc ~3711+) ne vérifie ni wallet.origin ni server_cashless — un solde FED importé serait dépensable en V2. (3) Le plan Phase 6 (TECH DOC/SESSIONS/LABOUTIK/DONE/Session 01 - construction UX/phase6_migration.md) prévoit un import du dump GLOBAL Fedow incluant les tokens (lignes 27-35, 50-51) tout en exigeant ligne 17 et ligne 97 que « les anciens serveurs DOIVENT continuer de fonctionner après l'import » — c'est exactement le scénario double-registre dénoncé : même solde FED vivant dans deux registres (Fedow standalone V1 + fedow_core V2), double dépense possible, irréconciliable. (4) PLAN_LABOUTIK.md section 13.4 (ligne 1449) ne couvre que la double-écriture PAR TENANT ; le composant connexe FED cross-tenant n'est traité nulle part dans le plan. NUANCES : non déclenchable aujourd'hui — la commande import_fedow_data n'existe pas encore (seuls bootstrap_fed_asset et verify_transactions dans fedow_core/management/commands/), et en l'état les deux économies FED sont disjointes (wallet_legacy bloqué en recharge V2, solde V2 = 0, donc rien à double-dépenser). Les chiffres prod cités (46 127 tx, 2 472 wallets, 22 places) ne sont pas vérifiables depuis le code mais le problème structurel n'en dépend pas. C'est un défaut du PLAN de migration, pas du code livré : la Phase 6 telle qu'écrite est incohérente et doit intégrer une stratégie de bascule FED (gel V1, migration simultanée des tenants à activité FED, ou transfert one-way avec mise à zéro V1) avant implémentation.


### ⏳ [BLOQUANT] Un seul Fedow sert deux instances Lespass (.coop et .re) + 31 places avec lespass_domain='xxx.None'

`/home/jonas/TiBillet/dev/Fedow/fedow_core/models.py:940`

La prod Fedow contient 317 places en *.tibillet.coop, 50 en *.tibillet.re et 31 places dont lespass_domain se termine littéralement par '.None' (string Python None formatée, ex: 'afps.None', 'benenova.None') — ces 31 places sont inmappables vers un Client par domaine. Les 50 places .re vivent dans une AUTRE base Lespass : leurs tenants, users et wallets n'existent pas dans la DB cible du portage (lespass.tibillet.coop). 54 wallets users sont actifs sur les deux instances à la fois, et 4 des 22 places à activité FED sont en .re — le périmètre FED traverse donc les deux instances Lespass.

**Recommandation :** Décider du sort de l'instance .re avant le chantier (migrer ses tenants dans le mono-repo ? la garder en V1 HTTP ?). Corriger ou cartographier à la main les 31 lespass_domain='None' (probablement places de test ou créées avant le champ — 301 places sur 398 n'ont aucune transaction, vérifier le recouvrement). Le mapping Place→Client doit utiliser Customers.Domain (multi-domaines par tenant), pas une égalité stricte.

_Contre-expertise échouée (limite de session)._


### ✅ [BLOQUANT] Sémantique débit/crédit V1 ≠ V2 : importer les transactions brutes fausse les soldes recalculés

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/management/commands/verify_transactions.py:205`

verify_transactions._verifier_soldes() crédite TOUT receiver et débite tout sender sauf FST/CRE. Or dans le Fedow standalone (models.py:710-748) : REFUND local ne crédite PAS le receiver (le lieu a remboursé en espèces), REFUND FED vers le primary ne crédite pas, et DEPOSIT (BNK, 273 tx) ne crédite jamais le receiver primary (l'argent part à la banque). Si on importe ces transactions telles quelles (receiver renseigné), le recalcul V2 produira des divergences systématiques sur les tokens des lieux et du pot central, et --fix-tokens 'corrigerait' en créant de fausses créances (ex: re-créditer au pot central les 273 remises en banque).

**Recommandation :** Normaliser à l'import : receiver=None (le modèle V2 l'autorise, models.py:479) pour les REFUND non crédités en V1 et pour les DEPOSIT, OU porter dans l'importeur la table exacte crédit/débit du DRIFT README §8.1. Valider l'import en exécutant verify_transactions et en exigeant 0 divergence.

**Contre-expertise (confiance haute)** : confirmé.
> CONFIRMÉ par lecture croisée des deux codebases. (1) Sémantique V1 vérifiée dans /home/jonas/TiBillet/dev/Fedow/fedow_core/models.py : REFUND débite le sender (l.719) mais ne crédite le receiver — pourtant renseigné et asserté (l.715-716) — que si asset STRIPE_FED_FIAT + lieu + non-primaire (l.726-729) ; DEPOSIT ne crédite jamais le receiver primaire (l.743, l.747 « On ne rempli pas le receiver, ça part a la banque »). (2) Côté V2, /home/jonas/TiBillet/dev/lespass-main/fedow_core/management/commands/verify_transactions.py : _verifier_soldes() crédite TOUT receiver sans aucune exclusion (l.212-216), n'exclut du débit que FIRST/CREATION (l.204), et n'a aucun filtre sur le champ migrated ; --fix-tokens écrit solde_attendu dans Token.value (l.350-357). (3) Aucune garde : pas de commande d'import existante (seuls bootstrap_fed_asset.py et verify_transactions.py), mais le modèle V2 prévoit explicitement l'import brut (models.py:497-500 uuid « conserve pour les imports », :458 migrated, :389 DEPOSIT conservé, :582-585 card/primary_card conservés) sans normalisation receiver=None. Les tests (tests/pytest/test_verify_transactions.py) ne couvrent ni REFUND ni DEPOSIT ni migrated. (4) AGGRAVANT raté par l'auditeur : la désynchronisation est déjà déclenchable en V2 pur, sans import — services.py:768-773 exclut REFILL et BANK_TRANSFER du débit et :792 exclut BANK_TRANSFER du crédit, alors que verify_transactions ne le fait pas (son commentaire l.202-203 « cf. services.py ligne 429 » est périmé). Une BANK_TRANSFER native (services.py:1111-1114, receiver renseigné, aucune mutation de token) ou un REFILL dont le sender possède un token produisent dès aujourd'hui de fausses divergences, et --fix-tokens les « corrigerait » en corrompant les soldes. Seule nuance : le volet import (273 DEPOSIT, etc.) ne peut pas se déclencher tant que la commande d'import (Phase 6) n'est pas écrite — mais comme le volet BANK_TRANSFER/REFILL est déclenchable immédiatement, la sévérité bloquant est justifiée. Fix attendu : modéliser la sémantique par action dans _verifier_soldes (alignée sur services.py) + exclure ou traiter spécifiquement les transactions migrated=True lors du futur import.


### ✅ [BLOQUANT] Token.value non fiable (lost-update) : reconcile_tokens doit tourner en prod AVANT tout export

`/home/jonas/TiBillet/dev/Fedow/TECH_DEV/DRIFT/README.md:5`

Le DRIFT documente ~1 262,60 € de crédits perdus chez les lieux, -236 € de monnaie fantôme sur le primary, 98 € sur les monnaies locales. Le patch F() est appliqué mais la régularisation prod (transactions CORRECTION via reconcile_tokens) n'est PAS encore lancée ('régularisation prod + virements à lancer'). 0 transaction COR dans la DB au 09/06. Un import qui copie token.value fossilise le drift dans V2 ; un import qui recalcule depuis les transactions donnera des soldes ≠ token.value actuels (donc ≠ ce que les users/lieux voient) tant que les CORRECTION n'existent pas. Les uuid de transactions sont sains (PK uuid4, 0 doublon de hash) et les ~320 forks de chaîne ne bloquent pas puisque V2 abandonne le chaînage (hash=null, migrated=True).

**Recommandation :** Prérequis dur du chantier : exécuter reconcile_tokens sur la prod Fedow (avec --exclure du wallet christelle), vérifier drift=0 via la requête §10.1 du DRIFT, PUIS exporter. À l'import, recalculer les soldes depuis les transactions et exiger l'égalité avec token.value (tolérance zéro après réconciliation).

**Contre-expertise (confiance haute)** : confirmé. Sévérité réévaluée : bloquant (pour la Phase 6 migration uniquement ; n'affecte pas les Phases 0-5).
> Confirmé par lecture du code et requête SQL directe. (1) Le drift est documenté dans Fedow/TECH_DEV/DRIFT/README.md:22-27 (1 262,60 € lieux, -236 € primary, 98 € monnaies locales) avec ligne 5 : « régularisation prod + virements à lancer ». (2) Le patch F() est bien appliqué dans Fedow/fedow_core/models.py:583-584 et 773-782, mais il n'empêche que les futurs lost-updates — le drift historique reste dans token.value. (3) La commande Fedow/fedow_core/management/commands/reconcile_tokens.py existe (dry-run par défaut, --apply crée des transactions CORRECTION, action COR définie models.py:496 et exclue du recalcul ligne 750), mais vérification directe sur la copie de prod locale db.sqlite3 (09/06, 145 763 transactions) : 0 transaction COR — la régularisation prod n'a pas eu lieu. (4) Aucune garde côté V2 : lespass-main/fedow_core/management/commands/ ne contient que bootstrap_fed_asset.py et verify_transactions.py — aucun code d'import n'existe, donc rien ne force l'ordre « réconcilier avant exporter ». Le modèle V2 prévoit l'import (hash=null, migrated=True, lespass-main/fedow_core/models.py:433-458). Le dilemme de l'auditeur est exact : copier token.value fossilise le drift ; recalculer depuis les transactions donne des soldes différents de ceux affichés aux users tant que les COR n'existent pas. L'affirmation sur les forks non-bloquants en V2 est aussi correcte (V2 abandonne le chaînage). Nuance de sévérité : « bloquant » est juste pour la catégorie migration (Phase 6), mais ne bloque pas les Phases 0-5 (code additif nouveaux tenants), et le scénario n'est pas déclenchable aujourd'hui faute de code d'import — c'est un prérequis d'ordonnancement (lancer reconcile_tokens --apply en prod + virements AVANT tout export), pas un bug dans le code V2.


### ⏳ [MAJEUR] Transaction.tenant NOT NULL en V2 mais ~27 700 transactions Fedow n'ont pas de tenant naturel

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/models.py:635`

Le modèle V2 impose tenant FK NOT NULL ('TOUJOURS filtrer par ce champ'). Or côté Fedow : 11 510 REFILL et 11 512 CREATION ont le primary wallet comme sender/receiver (recharges Stripe en ligne, aucun lieu), 3 935 FUSION relient un wallet éphémère à un wallet user (aucun lieu impliqué), 785 REFUND online vont vers le primary, et la FST de l'asset FED n'a pas de lieu. L'importeur doit définir une règle d'affectation explicite pour chaque cas, sinon l'import plante sur la contrainte NOT NULL ou affecte arbitrairement (et _verifier_coherence_tenant_asset exigera en plus que chaque tenant affecté soit dans asset.federated_with).

**Recommandation :** Spécifier la table d'affectation : SALE/QRS → tenant du lieu receiver ; CREATION/REFILL/REFUND locaux → tenant du lieu de l'asset ; transactions côté primary et FUSION → tenant 'federation_fed' (créé par bootstrap_fed_asset). Ajouter tous les tenants migrés à asset_fed.federated_with pour passer le check 3 de verify_transactions.

_Contre-expertise échouée (limite de session)._


### ✅ [MAJEUR] Codes action divergents entre V1 et V2 + action CORRECTION absente du modèle V2

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/models.py:381`

Trois codes ont changé : REFILL 'REF'→'RFL' (33 627 lignes concernées), DEPOSIT 'BNK'→'DEP' (273), VOID 'VID'→'VOI' (0 en prod). Une copie brute du champ action passe silencieusement (max_length=3, choices non contraints en DB) mais produit des actions inconnues qui faussent verify_transactions et l'admin. Plus grave : 'COR' (CORRECTION, créées par reconcile_tokens — prérequis du finding drift) n'existe pas dans ACTION_CHOICES V2, alors que ces transactions DEVRONT être importées pour que les soldes recalculés tombent juste. SUB (9 085) et BDG (2 030) sont exclues par décision — vérifier que BaseBillet.Membership couvre bien l'historique avant de les jeter.

**Recommandation :** Table de mapping explicite des codes dans l'importeur + ajouter une action CORRECTION (ou mapper COR→TRANSFER avec metadata['action_origine']='COR' et l'exclure du recalcul de soldes comme le fait le DRIFT). Écrire un test d'import qui vérifie que chaque action V1 a un mapping défini, et qui échoue sur action inconnue.

**Contre-expertise (confiance haute)** : confirmé.
> Tentative de réfutation échouée — tous les faits structurels du finding sont confirmés par lecture du code.

1. Divergence des codes confirmée. V1 (/home/jonas/TiBillet/dev/Fedow/fedow_core/models.py:494-496) : REFILL='REF', VOID='VID', DEPOSIT='BNK', CORRECTION='COR'. V2 (/home/jonas/TiBillet/dev/lespass-main/fedow_core/models.py:381-405) : REFILL='RFL', VOID='VOI', DEPOSIT='DEP', et CORRECTION ABSENT de ACTION_CHOICES (les commentaires lignes 376-379 ne mentionnent que le retrait volontaire de BDG/SUB, pas de COR — l'omission de COR semble être un oubli, pas une décision).

2. Aucune contrainte DB sur action. Le champ (models.py:513-517) est un CharField(max_length=3, choices=...) sans CheckConstraint — Meta (lignes 650-664) ne contient que des indexes. Django n'applique les choices qu'en full_clean()/formulaires, pas en .save() ni bulk_create. Les codes V1 'REF'/'VID'/'BNK'/'COR' font tous 3 caractères : une copie brute passerait silencieusement. Confirmé.

3. CORRECTION est bien un prérequis d'intégrité. Dans V1 (Fedow models.py:750-759), une transaction COR mute les soldes (crédite receiver OU débite sender selon le wallet primaire) et est créée par la command reconcile_tokens.py (présente dans /home/jonas/TiBillet/dev/Fedow/fedow_core/management/commands/). Sans import de ces transactions, les soldes recalculés ne tomberont pas juste ; avec import brut sous code 'COR' inconnu, verify_transactions V2 (/home/jonas/TiBillet/dev/lespass-main/fedow_core/management/commands/verify_transactions.py:204) les traiterait comme crédit receiver + débit sender simultanés (seuls FST/CRE sont exclus du débit), alors que V1 n'applique qu'UN seul côté — faux écarts ou écarts masqués garantis.

4. Aucun mapping V1→V2 documenté nulle part (grep dans TECH_DOC/ et fedow_core/ : zéro résultat sur un mapping de codes action).

Seule nuance réfutable : le code d'import (Phase 6) n'existe pas encore dans lespass-main — rien n'est cassable AUJOURD'HUI. Mais l'import est explicitement planifié dans le modèle même (champ uuid « conservé pour les imports depuis l'ancien Fedow », models.py:423-429 ; champ migrated, models.py:458-461 ; datetime sans auto_now_add « pour importer des transactions historiques », lignes 551-557). Le finding est de catégorie « portage » : c'est exactement le bon moment pour le signaler. Je n'ai pas pu vérifier les volumétries annoncées (33 627 REF, 273 BNK, 9 085 SUB, 2 030 BDG — données de prod inaccessibles), mais elles ne changent pas la conclusion structurelle.

Sévérité « majeur » justifiée : corruption silencieuse de données financières lors de l'import + faux résultats de l'outil d'intégrité (verify_transactions --fix-tokens pourrait alors écrire de mauvais soldes). Bloquant pour la Phase 6, sans impact sur les phases actuelles.


### ⏳ [MAJEUR] bootstrap_fed_asset crée un pot central avec un uuid neuf, différent du primary wallet Fedow

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/management/commands/bootstrap_fed_asset.py:63`

Le root wallet V2 est créé par Wallet.objects.get_or_create(name='Pot central TiBillet FED') — uuid aléatoire, et lookup par name non-unique (risque MultipleObjectsReturned si un wallet importé porte ce nom). À la migration finale du FED, les ~24 000 transactions importées référenceront l'ANCIEN primary wallet (uuid Fedow) tandis que les nouvelles transactions V2 référencent le nouveau root wallet : deux pots centraux coexistent, le calcul de dette du pot central (services.py, total_refund − total_virement par wallet) et les soldes du token primary sont faussés.

**Recommandation :** Au moment de l'import FED : soit réécrire sender/receiver des transactions importées vers le root wallet V2, soit (plus simple) faire adopter au root wallet l'uuid du primary Fedow — ce qui impose d'importer AVANT le bootstrap ou de prévoir une fusion. De même, l'asset FED importé doit garder l'uuid de l'asset Fedow ou être fusionné avec celui créé par bootstrap (contrainte unique_fed_asset : un seul FED possible).

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] 24 365 transactions référencent un CheckoutStripe Fedow sans équivalent V2 ; remboursements Stripe pré-migration impossibles

`/home/jonas/TiBillet/dev/Fedow/fedow_core/models.py:33`

V2 remplace la FK CheckoutStripe par un UUIDField checkout_stripe censé pointer un Paiement_stripe (schema tenant). Les uuid CheckoutStripe Fedow ne correspondent à aucun Paiement_stripe : références pendouillantes ambiguës après import. Surtout, le remboursement Stripe d'une recharge pré-migration (refund_payment_intent, models.py:95) a besoin du checkout_session_id/payment_intent stockés dans CheckoutStripe ET du compte Stripe du Fedow standalone. Par ailleurs 1 993 checkouts OPEN + 473 PROGRESS existent (72 récents <30j) : pendant la fenêtre de bascule, les webhooks Stripe de paiements en cours arriveront encore sur le Fedow standalone.

**Recommandation :** À l'import, copier checkout_session_id_stripe/intent_payment_id_stripe/invoice dans Transaction.metadata (pas seulement l'uuid). Définir la procédure de cutover : fermer les checkouts OPEN côté Fedow (expiration Stripe = 24h) avant le gel, et garder le Fedow standalone en lecture seule + accès Stripe pour le SAV remboursements des recharges historiques.

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Wallets éphémères et orphelins porteurs de valeur : l'import ne peut pas se limiter aux wallets d'users

`/home/jonas/TiBillet/dev/Fedow/fedow_core/models.py:1062`

Sur 38 159 wallets : 14 971 wallets users, 398 places, 10 522 wallets éphémères de cartes anonymes — qui portent de l'argent réel : 2 090 tokens TLF>0 (17 053 €), 727 TNF>0 (9 194 €), 616 FED>0 (2 764,60 €) — et 12 268 wallets orphelins (ni user, ni place, ni carte, ni primary) dont 6 423 ont des transactions (anciens éphémères défusionnés : FK sender/receiver cassées si on les saute) et 4 ont encore 13 € de solde. S'ajoutent 26 642 cartes sans user NI wallet_ephemere (jamais utilisées, wallet créé paresseusement par get_wallet()).

**Recommandation :** Importer TOUS les wallets référencés par au moins une transaction ou un token (même orphelins), en conservant l'uuid (AuthBillet.Wallet.uuid = uuid Fedow, vérifié partagé via fedow_api.get_or_create_wallet). Lier carte.wallet_ephemere (champ déjà ajouté en V2 sur CarteCashless). Les wallets orphelins sans transaction ni solde (~5 845) peuvent être ignorés.


### ⏳ [MAJEUR] Assets locaux fédérés : l'unité minimale de migration est la fédération entière, pas le tenant

`/home/jonas/TiBillet/dev/Fedow/fedow_core/models.py:820`

Quatre fédérations actives partagent un asset local entre plusieurs places : CLAFoutils (36 places, 1 asset), CLAF-outils (4), Mamasound (3), Demeter (2). Un asset TLF/TNF fédéré est dépensable chez toutes les places membres : migrer une seule place d'une fédération recrée le problème du double registre (le token du user est décrémenté dans V2 quand il paie chez la place migrée, dans le standalone quand il paie chez les autres). 20 wallets détiennent des tokens locaux (valeur>0) issus d'assets de plus d'une place.

**Recommandation :** Définir l'unité de migration comme la fermeture transitive {place → fédérations → places membres} : toutes les places d'une même fédération locale migrent dans la même fenêtre. Outiller un script qui calcule ces composants connexes depuis la table fedow_core_federation_places avant de planifier les vagues.


### · [MINEUR] Mapping cartes : 2 tag_id non conformes (6 et 7 caractères) et champs sans équivalent V2

`/home/jonas/TiBillet/dev/Fedow/fedow_core/models.py:1048`

45 887 cartes sur 45 889 ont un first_tag_id de 8 caractères ; 2 cartes font 6 et 7 caractères, or les validators Lespass (fedow_connect/validators.py:196) et CarteCashless.tag_id imposent 8 hex — l'import les rejettera. Mapping à spécifier : Card.qrcode_uuid (NOT NULL unique) → CarteCashless.uuid (nullable unique, conflits possibles si la carte existe déjà côté Lespass avec un autre uuid) ; complete_tag_id_uuid sans équivalent ; primary_places M2M (8 cartes maîtresses rattachées à PLUSIEURS places) alors que la décision V2 's'appuie sur detail.origine' qui est mono-place. Origin(place, generation) → Detail(origine, generation) : OK structurellement. 0 doublon de casse sur tag_id/number_printed.

**Recommandation :** Matcher par tag_id (get_or_create), traiter les 2 cartes anormales à la main, stocker complete_tag_id_uuid dans un champ ou metadata, et reconstruire les cartes maîtresses par tenant côté laboutik (gérer explicitement les 8 cartes multi-places).

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Correspondance users saine côté Fedow, mais matching à faire en insensible à la casse côté Lespass

`/home/jonas/TiBillet/dev/Fedow/fedow_core/models.py:905`

FedowUser : 14 971 users, 0 doublon après lower(), 0 email avec majuscules (get_or_create_user normalise), 1 seul user sans wallet. Le risque résiduel est côté Lespass : TibilletUser.email est unique mais rien ne garantit la normalisation lower() historique — un match strict par égalité créerait des doublons TibilletUser pour le même humain (et donc deux wallets pour un même email). Les users de l'instance .re n'existent pas dans la DB .coop et devront être créés (sans mot de passe, email_valid à décider).

**Recommandation :** Matching par email__iexact avec rapport de collisions avant import. Pour les users créés à l'import : user inactif/sans mot de passe, déclenchement du flow magic-link existant à la première connexion.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] verify_transactions --tenant produit de faux écarts sur les assets fédérés

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/management/commands/verify_transactions.py:186`

Avec --tenant, les tokens sont filtrés par asset__tenant_origin mais les transactions par tenant=X : pour un asset fédéré (FED ou TLF partagé), les transactions des AUTRES tenants sur le même token sont exclues du recalcul → solde attendu faux, et --fix-tokens écraserait Token.value avec une valeur partielle. C'est précisément l'outil prévu pour valider les imports tenant par tenant : il donnera des faux positifs sur tout tenant membre d'une fédération.

**Recommandation :** Pour la validation post-import, n'utiliser --fix-tokens qu'en mode global (sans --tenant), ou corriger la commande pour que le recalcul d'un token agrège TOUTES les transactions du couple (wallet, asset) quel que soit le tenant.

_Non contre-expertisé (sous le seuil majeur)._


### · [INFO] UUID stockés sans tirets dans SQLite : piège pour tout outillage d'export SQL brut

`/home/jonas/TiBillet/dev/Fedow/db.sqlite3:0`

Django stocke les UUIDField SQLite en char(32) sans tirets (documenté dans DRIFT §10.2). Un export CSV/SQL brut vers PostgreSQL (qui attend le format avec tirets) échouera ou créera des uuid invalides. Volume total modeste : 145 763 transactions, 36 870 tokens, 38 159 wallets — un import via ORM Django (lecture SQLite, écriture PostgreSQL) est faisable en une nuit et évite le piège.

**Recommandation :** Privilégier un management command Django avec deux connexions (database router ou lecture sqlite3 + uuid.UUID(hex=...)), idempotent grâce à Transaction.uuid unique (get_or_create), rejouable par tranches.

_Non contre-expertisé (sous le seuil majeur)._


---

## Prérequis du portage V2 → V1

**Synthèse de l'auditeur :** Audit des prérequis du portage fedow_core V2 (lespass-main, branche V2) vers le repo V1 (Lespass, branche main-fedow-import). Les deux repos sont des clones du même remote, divergés de 209/357 commits depuis le merge-base 10a9e914. Le socle fedow_core pur est étonnamment portable : ses imports inter-apps (Wallet, CarteCashless.detail/origine, Client, staff_admin_site, TenantAdminPermissionWithRequest, TibilletUser.get_private_key, Membership.card_number) existent tous en V1 avec la même interface, les migrations AuthBillet/QrcodeCashless/Customers sont copiables sans conflit, les templates admin asset/federation sont déjà présents et identiques en V1, et la sidebar/dashboard V1 est déjà pré-câblée (marqueurs « FROM V2 »). Le portage achoppe sur quatre points durs : (1) collision frontale des migrations BaseBillet 0204-0217 (numéros identiques, contenus différents, proxies créés deux fois) qui impose une régénération complète côté V1 ; (2) la dépendance non gardée de fedow_core/signals.py à laboutik.models et aux champs POS de Product/CategorieProduct, absents de V1 — le portage « fedow_core seul » crashe au premier Asset créé ; (3) le chemin Stripe de recharge FED (refill_federation.py, source CASHLESS_REFILL, dispatch webhook refill_type=FED, BaseBillet/services_refund.py) entièrement absent de V1, avec un Webhook_stripe qui a divergé et exige une réinsertion manuelle ; (4) le front V2 du flow recharge vit dans un arbre de templates htmx/views/ qui n'existe pas en V1 (thème reunion). S'y ajoutent des pièges latents : résidus pycache fedow_core dans le working tree V1 (migrations peut-être déjà appliquées sur la DB dev), POSPriceInline V1 prêt à exploser au décommentage, et une incohérence bool()/is not None sur server_cashless dans le dispatch V1/V2 qui sera importée telle quelle. Conformément aux décisions du mainteneur, fedow_core V2 ne contient bien aucune catégorie SUB/BDG (adhésions via BaseBillet.Membership) et la chaîne Transaction utilise id BigAutoField + uuid d'import.


### ⏳ [BLOQUANT] Collision de numérotation des migrations BaseBillet 0204–0217 entre branches

`/home/jonas/TiBillet/dev/Lespass/BaseBillet/migrations/:0`

Les deux branches (même repo NothRen/Lespass, merge-base 10a9e914, divergence 209 vs 357 commits) ont chacune créé des migrations BaseBillet 0204→0217/0218 DIFFÉRENTES après 0203_formbricks. V1 : 0204_configuration_module_adhesion → 0218_federationconfiguration_tags_federation. V2 : 0204_categorieproduct → 0217_merge. Contenus qui se chevauchent : V1 0205 crée déjà les proxies POSProduct/FutProduct/MembershipProduct que V2 0204 crée aussi (avec CategorieProduct en plus). Copier les migrations V2 → doublons de numéros, InconsistentMigrationHistory, opérations en double sur les proxies.

**Recommandation :** Ne JAMAIS copier les migrations BaseBillet V2. Porter les champs modèles (CategorieProduct, Product.asset/methode_caisse/categorie_pos/couleurs POS, Price.asset/non_fiduciaire/contenance/poids_mesure, Paiement_stripe CASHLESS_REFILL) puis makemigrations frais en 0219+ dans V1, en vérifiant que les opérations proxy déjà jouées par V1 0205 ne sont pas régénérées.

_Contre-expertise échouée (limite de session)._


### ⏳ [BLOQUANT] fedow_core/signals.py importe laboutik.models sans garde — laboutik absent de V1

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/signals.py:65`

Le signal post_save sur Asset fait `from laboutik.models import PointDeVente` (ligne 65, sans try/except contrairement à services.py:660 qui guard CartePrimaire). Dans le repo V1, laboutik/ est une coquille vide non trackée (aucun .py, `git ls-files laboutik/` vide) et absente de TENANT_APPS (settings.py V1 ligne 174+). Déclencheur : tout save() d'un Asset TLF/TNF/TIM dans un schéma tenant → ModuleNotFoundError. Le signal exige aussi Product.methode_caisse/categorie_pos/couleur_fond_pos/icon_pos/asset et CategorieProduct, tous absents du modèle Product V1 (vérifié BaseBillet/models.py V1 : aucun de ces champs).

**Recommandation :** Soit porter laboutik avec fedow_core (10 700 lignes models+views tirées en cascade), soit découpler : guard try/except ImportError sur PointDeVente + rendre la création du Product de recharge conditionnelle aux champs POS (ou désactiver le signal en phase 1 du portage).

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] BaseBillet/services_refund.py absent du repo V1, requis par fedow_core/services.py

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/services.py:548`

rembourser_en_especes (ligne 548) et enregistrer_virement (ligne 1094) importent get_or_create_product_remboursement, get_or_create_pricesold_refund, get_or_create_product_virement_recu depuis BaseBillet.services_refund. Ce fichier n'existe pas dans /home/jonas/TiBillet/dev/Lespass/BaseBillet/ (vérifié). Déclencheur : premier remboursement carte ou virement de dette en V1 → ModuleNotFoundError.

**Recommandation :** Porter BaseBillet/services_refund.py (97 lignes, dépendances Price/PriceSold/Product/ProductSold toutes présentes en V1) dans le même lot que fedow_core/services.py.

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Client.FED et tenant federation_fed absents de V1

`/home/jonas/TiBillet/dev/Lespass/Customers/models.py:17`

V1 Customers/models.py ligne 17 : catégories A,S,F,T,P,M,W,R — pas de FED ('E'). Or bootstrap_fed_asset crée le tenant schema_name='federation_fed' avec categorie=Client.FED, RefillService.process_cashless_refill cherche Asset.objects.get(category=Asset.FED), et le webhook V2 (ApiBillet/views.py:1190) vérifie tenant.schema_name == 'federation_fed'. Sans la catégorie ni le bootstrap, toute recharge FED V2 crashe (Asset.DoesNotExist).

**Recommandation :** Copier Customers/migrations/0005_alter_client_categorie.py (historique Customers non divergé, copie sûre), porter le choix FED dans le modèle, et porter la command bootstrap_fed_asset (qui dépend elle-même de Product/Price du schéma federation_fed — vérifier ses champs requis).

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Chemin Stripe recharge V2 absent de V1 : refill_federation.py, source CASHLESS_REFILL, dispatch webhook

`/home/jonas/TiBillet/dev/Lespass/ApiBillet/views.py:1082`

Trois pièces manquantes en V1 : (1) PaiementStripe/refill_federation.py (gateway compte central, sans Connect) et PaiementStripe/serializers.py n'existent pas en V1 ; (2) Paiement_stripe.SOURCE_CHOICES V1 (BaseBillet/models.py:2720) n'a pas CASHLESS_REFILL (présent en V2 ligne 3600) ; (3) le Webhook_stripe V1 (ApiBillet/views.py:1082) n'a ni le dispatch metadata refill_type=='FED' (V2 lignes 1245-1248) ni traiter_paiement_cashless_refill (V2 lignes 1040-1150, avec select_for_update + anti-tampering). Le webhook V1 a divergé sur 209 commits : la réinsertion du dispatch doit se faire à la main, pas par copie du fichier.

**Recommandation :** Porter refill_federation.py + serializers.py tels quels (deps RootConfiguration/LigneArticle présentes en V1), ajouter CASHLESS_REFILL au modèle (migration BaseBillet fraîche), et ré-implémenter le dispatch refill_type=FED dans le Webhook_stripe V1 en suivant test_refill_webhook.py comme contrat.

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Templates du flow recharge V2 dans un arbre htmx/views/ inexistant en V1

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:1856`

Les branches V2 de MyAccount rendent htmx/views/my_account/refill_form_v2.html (lignes 1856, 1899, 1920, 2035), tirelire_section.html (1118) et refill_migration_inline.html (1835). Le repo V1 n'a AUCUN dossier BaseBillet/templates/htmx/ (vérifié) — son front est le thème reunion/. En revanche reunion/partials/account/token_table_v2.html et transaction_history_v2.html (rendus lignes ~1482+) sont dans le même arbre que les token_table.html/transaction_history.html V1 et sont copiables. Bonne nouvelle : aucun des templates V2 à porter n'utilise django-cotton (vérifié), donc pas de dépendance aux loaders cotton absents de V1.

**Recommandation :** Copier les 2 partials reunion ; réécrire refill_form_v2/tirelire/migration_inline pour le thème reunion V1 (ou porter uniquement la logique serveur et brancher sur le formulaire refill existant de MyAccount V1, ligne 1132 de views.py V1).

_Contre-expertise échouée (limite de session)._


### ⏳ [MAJEUR] Sidebar V1 déjà câblée sur des URLs admin fedow_core inexistantes (NoReverseMatch latent)

`/home/jonas/TiBillet/dev/Lespass/Administration/admin/dashboard.py:381`

get_sidebar_navigation V1 contient déjà le bloc `if configuration.module_monnaie_locale:` avec reverse_lazy('staff_admin:fedow_core_asset_changelist'), _transaction_, _federation_ (lignes 371-396) alors que fedow_core n'est pas installé. Déclencheur : module_monnaie_locale=True (possible via shell, fixture, ou import de données — le toggle dashboard est neutralisé car MODULE_FIELDS le commente ligne 778) → NoReverseMatch sur TOUTES les pages admin du tenant. Même motif dans tests/e2e/conftest.py V1 ligne 229 qui navigue vers /admin/fedow_core/asset/. C'est aussi une bonne nouvelle : la sidebar et les templates admin/asset/* + admin/federation/* (identiques aux V2, diff vide) sont déjà en place.

**Recommandation :** Faire du portage de fedow_core/admin.py la condition d'activation : tant qu'il n'est pas mergé, ne jamais passer module_monnaie_locale à True en V1 (ajouter un guard ou un check Django temporaire).

_Contre-expertise échouée (limite de session)._


### · [MINEUR] POSPriceInline V1 référence des champs Price inexistants et importe fedow_core

`/home/jonas/TiBillet/dev/Lespass/Administration/admin/products.py:588`

POSPriceInline (ligne 588) déclare fields poids_mesure/contenance/non_fiduciaire/asset et son formfield_for_foreignkey importe fedow_core.models (ligne 632), alors que Price V1 n'a aucun de ces champs (vérifié BaseBillet/models.py V1). Inoffensif aujourd'hui car l'enregistrement est commenté (lignes 1490-1641, marqueurs FROM V2), mais SystemCheckError garanti au premier décommentage avant le portage des champs Price. Idem proxy POSProduct V1 (BaseBillet/models.py:1148, docstring filtre methode_caisse) sans champ methode_caisse.

**Recommandation :** Dans le plan de portage, traiter ces backports partiels « FROM V2 : TODO » comme des points de reprise : porter Price.asset/non_fiduciaire/contenance/poids_mesure AVANT de décommenter quoi que ce soit dans products.py.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Résidus d'exécution V2 dans le working tree V1 : pycache fedow_core + migrations peut-être déjà appliquées en DB dev

`/home/jonas/TiBillet/dev/Lespass/fedow_core/migrations/__pycache__:0`

Le repo V1 contient fedow_core/__pycache__ (models, services, admin compilés, dont des .pyc des migrations 0001_initial, 0002, 0003) et un dossier laboutik/ vide non tracké : la branche V2 a tourné dans ce working tree (commit 7a62df9e visible via --all sur les branches V2). Risque concret : la base PostgreSQL de dev du repo V1 contient peut-être déjà les lignes django_migrations de fedow_core 0001-0003 et les tables fedow_core_* ; au moment du vrai portage, migrate échouera ou passera silencieusement sur un état de table divergent de la migration régénérée.

**Recommandation :** Avant le portage : SELECT app, name FROM django_migrations WHERE app IN ('fedow_core','laboutik') sur la DB dev V1, et \dt fedow_core_* ; purger les pycache et l'éventuel état orphelin. Documenter dans le plan de portage.

_Non contre-expertisé (sous le seuil majeur)._


### · [MINEUR] Dispatch V1/V2 incohérent dans lespass-main : bool() vs is not None sur server_cashless

`/home/jonas/TiBillet/dev/lespass-main/BaseBillet/views.py:829`

Les flows carte testent `tenant_est_en_v1 = bool(config.server_cashless)` (lignes 453, 598, 1143) mais peut_recharger_v2 teste `config.server_cashless is not None` (lignes 829 et 837). server_cashless est un URLField(blank=True, null=True) : un formulaire admin Django sauve "" (chaîne vide), pas NULL. Scénario : un tenant V2 dont la Configuration a été enregistrée une fois via l'admin a server_cashless="" → cartes traitées en V2 mais recharge refusée avec verdict 'v1_legacy'. Ce bug sera importé tel quel dans V1 où tous les tenants passent par le form Configuration.

**Recommandation :** Harmoniser sur bool(config.server_cashless) dans peut_recharger_v2 (lignes 829 et 837) avant ou pendant le portage ; ajouter un cas "" dans test_peut_recharger_v2.py.

_Non contre-expertisé (sous le seuil majeur)._


### · [INFO] Migrations AuthBillet/QrcodeCashless/Customers/fedow_core copiables telles quelles — sauf décision sur 0025_terminal_role

`/home/jonas/TiBillet/dev/lespass-main/fedow_core/migrations/0001_initial.py:13`

Contrairement à BaseBillet, les historiques AuthBillet, QrcodeCashless et Customers n'ont PAS divergé : V2 ajoute proprement AuthBillet 0024 (Wallet.public_pem+name) et 0025 (TibilletUser.terminal_role), QrcodeCashless 0021 (wallet_ephemere), Customers 0005 (catégorie FED). fedow_core 0001_initial dépend exactement de Customers 0004 (présent en V1), QrcodeCashless 0021 et AuthBillet 0024 (à copier d'abord) — chaîne cohérente. Point de décision : AuthBillet 0025 ajoute terminal_role qui ne sert qu'à laboutik (rôles LB/TI/KI) ; le porter ou non selon que laboutik suit.

**Recommandation :** Copier ces 4-5 fichiers de migration à l'identique (même noms → les dependencies de fedow_core 0001 restent valides). Trancher explicitement le sort de 0025_tibilletuser_terminal_role dans le plan.

_Non contre-expertisé (sous le seuil majeur)._


### · [INFO] Tests V2 : pytest portables, e2e partiellement dépendants de laboutik

`/home/jonas/TiBillet/dev/lespass-main/tests/pytest/test_fedow_core.py:28`

Les tests pytest fedow (test_fedow_core, test_refill_service, test_refill_federation_gateway, test_refill_webhook, test_peut_recharger_v2, test_tokens_table_v2, test_transactions_table_v2, test_scan_qr_carte_v2, test_traiter_paiement_cashless_refill) n'importent que Customers/AuthBillet/fedow_core et utilisent call_command('bootstrap_fed_asset') + le conftest --api-key (manage.py test_api_key présent dans les deux repos). Ils sont portables avec fedow_core. En revanche les e2e tests V2 (tests/e2e/test_pos_vider_carte.py, test_asset_federation.py…) supposent le POS laboutik et/ou les fixtures demo V2 — non portables sans laboutik. V1 utilise en plus un arbre tests/playwright absent de lespass-main (frameworks e2e différents entre branches).

**Recommandation :** Porter le lot pytest avec fedow_core + bootstrap_fed_asset ; reporter les e2e POS à la phase laboutik ; vérifier les divergences de conftest e2e (celui de V1 référence déjà /admin/fedow_core/asset/ ligne 229).

_Non contre-expertisé (sous le seuil majeur)._


### · [INFO] Settings V1 : seul SHARED_APPS += 'fedow_core' est requis, pas de dépendance cotton/channels

`/home/jonas/TiBillet/dev/Lespass/TiBillet/settings.py:121`

Audit croisé des settings : fedow_core (app, admin, services, signals) ne requiert ni middleware ni setting clé supplémentaire ; il suffit de l'ajouter à SHARED_APPS V1 (ligne 121+, comme V2 ligne 149). Les écarts V2 (django_cotton loaders, channels, controlvanne, booking, logger 'laboutik' ligne 528) ne concernent pas fedow_core. pyproject quasi identiques (seul ajout V2 : django-cotton, inutile ici). Les imports de fedow_core/admin.py sont satisfaits en V1 : staff_admin_site ré-exporté par Administration/admin_tenant.py ligne 13, TenantAdminPermissionWithRequest (ApiBillet/permissions.py:61), pas de clash related_name (fedow_core_assets vs assets_created de fedow_connect et assets_fedow_public de fedow_public).

**Recommandation :** Une seule ligne settings + copie des migrations partagées : le socle fedow_core pur (models/services/admin/exceptions) est le lot le moins risqué du portage. Commencer par lui.

_Non contre-expertisé (sous le seuil majeur)._
