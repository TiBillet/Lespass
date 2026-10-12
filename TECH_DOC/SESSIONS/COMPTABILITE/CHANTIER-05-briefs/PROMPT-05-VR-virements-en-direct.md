# Prompt — brancher les virements reçus (FED, Stripe) sur la vente, en production

**INTERDICTION ABSOLUE : aucune opération git qui écrit (`add`, `commit`, `push`, `checkout`, `stash`,
`reset`, `restore`, `clean`…). Lecture seule autorisée (`status`, `diff`, `log`). Jamais de
`Co-Authored-By`. Le mainteneur commite lui-même. Même règle pour tout sous-agent : en tête de son prompt.**

Tu es l'orchestrateur d'un correctif du chantier 05 de Lespass (« montants entiers »). **Réponds
TOUJOURS en français.** Sans sur-ingénierie : on résout ce problème, rien de plus.

## Contexte (2026-10-12)
- Le chantier 05 est **EN PRODUCTION depuis la nuit du 11 au 12 octobre 2026** (518 lieux migrés,
  22 880 ventes reprises, 106 J « reprise »). Procédure et résultats :
  `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-nuit-procedure.md`, fiche
  `CHANTIER-05-R-reprise-ventes.md`, journal `CHANTIER-05-SUIVI.md`, point d'entrée
  `CHANTIER-05-briefs/PROMPT-ORCHESTRATEUR.md`. **Lis-les avant tout**, avec `GUIDELINES.md` et
  `tests/PIEGES.md`.
- **Le bug** (constat n°35, point (2), `TECH_DOC/SESSIONS/TODO/BUGS-constats-chantier-05.md`) :
  le webhook Stripe `transfer.created` (`ApiBillet/views.py` ~l.1357-1435 : virement de monnaie
  fédérée **FED**, de vrais euros versés par Stripe Connect au lieu) crée un `Paiement_stripe`
  `source = T`, validé, l'envoie à Fedow et à LaBoutik V1… et **n'écrit aucune `Vente`**. Il n'a
  jamais été branché sur le modèle Vente / Règlement.
- La reprise de la nuit a donné une vente `VR` aux **125 virements historiques** (décision QO-9,
  option B) : le code est dans `BaseBillet/reprise_des_ventes.py`
  (`_reprendre_les_virements_recus`, ~l.1078-1165 : article `VR`, prix = montant du virement, TVA 0,
  asset FED, règlement `PaymentMethod.STRIPE_NOFED` / compte 517100, origine `SaleOrigin.WEBHOOK`)
  et `BaseBillet/reprise_des_ventes_ecriture.py` (`_creer_l_article_d_un_virement_recu` ~l.322,
  `get_or_create_product_virement_recu` et `get_or_create_pricesold_refund` de
  `BaseBillet/services_refund.py`, `encaisser_vente(vente, datetime_encaissement=…)` de
  `BaseBillet/services_vente.py`). C'est une commande **lancée une seule fois** : elle ne traite
  pas les virements arrivés après.
- **Cas réel en prod** : La Filature (`la-filature.tibillet.coop`, schéma
  `ffe52f5e8b134bf6b62b4d5b2b346763`), paiement `a1a32832`, **1 893,00 €**, 2026-10-12 05:17:06 UTC,
  statut V, **sans vente**. Le précédent (3 803,50 €, 2026-10-03) a sa vente `VR` (reprise).
- **HORS PÉRIMÈTRE : la CLAF.** Ses « remises en banque » sont des jetons LOCAUX (TLF), une
  transaction `DEPOSIT` sur Fedow, sans Stripe (bouton « Remise en banque » de l'admin,
  `Administration/admin_tenant.py` ~l.6523). Autre flux, autre fiche (constat n°35, points (1) et (2)
  côté CLAF). Ne pas y toucher.

## Ce qu'il faut livrer
1. **Une seule fabrique de la vente « virement reçu »** : extraire de la reprise ce qui fabrique la
   vente `VR` d'un paiement `T` (article, règlement, encaissement), en un service appelé par la
   reprise ET par le webhook. Les tests de la reprise (`tests/pytest/test_reprise_des_ventes.py`)
   doivent rester verts sans modification de leur intention.
2. **Le webhook `transfer.created`** écrit la vente `VR` juste après la création du
   `Paiement_stripe` `T` et la relie (`Paiement_stripe.vente`). Idempotent : un webhook rejoué
   (Stripe rejoue) ne crée pas une seconde vente (clé d'idempotence propre, distincte du préfixe
   `reprise-`). Un échec d'écriture de la vente ne doit pas faire perdre le virement (le paiement,
   Fedow et LaBoutik passent avant) : la vente reste à rattraper, avec une ligne d'erreur au journal.
   (Cosmétique, même endroit : le journal affiche `<bound method …uuid_8>`, il manque `()`.)
3. **Une commande de rattrapage** (`manage.py`, à blanc par défaut, `--executer` pour écrire) : pour
   chaque lieu, chaque paiement `T` validé **sans vente** reçoit sa vente `VR`. Le rapport ne montre
   que des nombres, des montants, des schémas et des domaines. On ne relance PAS
   `reprendre_les_ventes_existantes` : elle refuse un lieu qui a déjà des ventes hors reprise.

## Questions à trancher avec le mainteneur AVANT de coder
- **La date de la vente rattrapée.** La vente `VR` est encaissée à la date du virement dans la
  reprise. En rattrapage, si la clôture J du jour du virement est déjà faite, une vente datée de ce
  jour tomberait dans une période déjà clôturée (chaîne et clôtures incohérentes). Date du virement
  seulement si la période n'est pas clôturée, sinon maintenant ? Refus ? Lire comment
  `comptabilite/tasks.py` borne les J (`_ventes_reglees_entre`, filet J, heure de fermeture).
- Le service de la vente : dans `services_vente.py` (à côté de `encaisser_vente_stripe`) ou ailleurs ?

## Méthode (protocole du chantier 05)
brief (`CHANTIER-05-briefs/05-VR-N.md`) → l'ouvrier écrit les tests → tu prouves le ROUGE → vert →
**tu joues les mutations toi-même** (sha256 avant / après, fichier restauré) → caractérisation →
relecture Fable → le mainteneur commite. Tests : `make test` (suite complète) ; le serveur de dev
tourne dans byobu (s'il répond 502, demander au mainteneur ; ne jamais lancer un 2ᵉ serveur).

## Règles du projet (rappel)
- `poetry`, `pytest`, `ruff` TOUJOURS via `docker exec lespass_django …` (jamais depuis l'hôte : ça
  détruit le `.venv` partagé). `ruff format` seulement sur des fichiers NEUFS. `ruff check --fix`
  interdit sur `admin*.py`, `apps.py`, `signals.py`, `__init__.py` sans inspection.
- Pas de `makemessages` / `compilemessages`. Textes `_()` en français. Code FALC, commentaires FR/EN.
- Écriture des ventes : jamais `save()` sur une vente encaissée ; passer par les services.

## Production
- **Toute commande en prod est lancée par le mainteneur**, qui colle la sortie ; tu vérifies et tu
  donnes la suivante, **une à la fois**. Aucune lecture de donnée personnelle : comptages et montants.
- Déployer (code monté, pas d'image) : sur le serveur `cd ~/main-lespass && git status --short`
  (attendus : `logs/__init__`, `www/__init__` supprimés, `*_du_depot/` non suivis), `git pull`,
  `migrate_schemas` **seulement si une migration est en attente** (14 min 41 pour rien sinon ;
  multiprocessing interdit si une migration ajoute une clé étrangère vers une table publique),
  `collectstatic --no-input`, puis
  `docker exec lespass_django poetry run supervisorctl -c /DjangoFiles/supervisor/supervisord.conf restart gunicorn daphne celery`.
  **Jamais `docker compose up -d <service>` sans `--no-deps`** (recrée postgres et django : vécu
  le 2026-10-12, 1 min 30 de 502). Détails : `TECH_DOC/SESSIONS/TODO/DEPLOIEMENT-mise-a-jour-sans-coupure.md`.
- Puis le rattrapage en prod : à blanc, contrôle, `--executer`, contrôle (La Filature : la vente
  de 1 893,00 € apparaît dans `/admin/BaseBillet/vente/`).

**Première action : lire les docs listées, puis me poser les questions à trancher.**
