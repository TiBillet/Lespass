# Table des matieres des lancements de tests. La logique vit dans scripts/lancer_tests.sh.
# / Table of contents for test runs. The logic lives in scripts/lancer_tests.sh.

# Familles E2E : lues dans pytest.ini (marqueurs dont la description commence par
# « famille E2E »), ecrites avec des tirets (caisse_composants -> caisse-composants).
# Un nom de famille tape apres la cible (make e2e-visible adhesion) est une « cible »
# pour make : on la declare sans action, et on transmet les familles demandees au script.
# / E2E families are read from pytest.ini and typed after the target; make sees them as
# goals, so they are declared as no-op targets and passed to the script.
FAMILLES_E2E := $(shell sed -n 's/^ *\([a-z_]*\): famille E2E.*/\1/p' pytest.ini | tr '_' '-')
FAMILLES_DEMANDEES := $(filter $(FAMILLES_E2E),$(MAKECMDGOALS))
CIBLES := help test e2e e2e-visible coverage release env update update_nuit

# Un mot inconnu arrete tout AVANT de lancer quoi que ce soit : sinon une faute de frappe
# (make e2e-visible adhesio) lancerait d'abord toute la suite.
# / An unknown word stops everything BEFORE running: a typo would otherwise run the whole suite.
MOTS_INCONNUS := $(filter-out $(CIBLES) $(FAMILLES_E2E),$(MAKECMDGOALS))
ifneq ($(MOTS_INCONNUS),)
$(error Inconnu : $(MOTS_INCONNUS). Les familles sont listees par « make help »)
endif
ifneq ($(FAMILLES_DEMANDEES),)
ifeq ($(filter e2e e2e-visible,$(MAKECMDGOALS)),)
$(error Une famille va avec make e2e ou make e2e-visible : make e2e-visible $(FAMILLES_DEMANDEES))
endif
endif

.PHONY: $(CIBLES) $(FAMILLES_E2E)

LANCER := bash scripts/lancer_tests.sh

help:
	@echo "Lespass — lancer les tests"
	@echo ""
	@echo "  make test          pytest, tests Stripe reel compris (cle sk_test, reseau)"
	@echo "  make e2e           E2E navigateur, parcours Stripe compris (stripe listen dans byobu)"
	@echo "  make e2e-visible   E2E dans un Chromium visible sur l'ecran, ralenti, avec journal"
	@echo "  make coverage      pytest + couverture du code (total + htmlcov/)"
	@echo "  make release       MAINTENEUR : construit l'image d'origin/main et la pousse (REFAIRE_LA_BASE=1 : tout reconstruire)"
	@echo "  make env           PROD : cree le .env (secrets generes, A_REMPLIR), les dossiers, et controle le serveur"
	@echo "  make update        PROD : mise a jour sans coupure (release poussee avant, a toute heure : attend la fin d'une sauvegarde en cours)"
	@echo "  make update_nuit   PROD : programme make update a 02:05 avec at (MIGRER=1 ou EXECUTEUR=standard transmis)"
	@echo ""
	@echo "  Familles E2E (avec make e2e ou make e2e-visible, cumulables) :"
	@sed -n 's/^ *\([a-z_]*\): famille E2E — \(.*\)/\1|\2/p' pytest.ini \
		| while IFS='|' read -r nom description; do \
			printf "    %-22s %s\n" "$$(echo "$$nom" | tr '_' '-')" "$$description"; \
		done
	@echo ""
	@echo "  Famille : make e2e-visible adhesion"
	@echo "            make e2e-visible adhesion qrcode       (les deux familles)"
	@echo "  Cibler :  make test ARGS=\"tests/pytest/test_stripe_refund.py -k panier\""
	@echo "  Detail :  make coverage FICHIERS=\"BaseBillet/services_panier.py,BaseBillet/services_commande.py\""
	@echo "  Suivre :  make e2e-visible LENTEUR=1500 ARGS=\"tests/e2e/test_panier_flow.py\""
	@echo ""
	@echo "  Aucun test Stripe n'est ignore : si Stripe ou stripe listen manque,"
	@echo "  les tests concernes ECHOUENT."

test:
	@$(LANCER) python $(ARGS)

e2e:
	@FAMILLES="$(FAMILLES_DEMANDEES)" $(LANCER) e2e $(ARGS)

e2e-visible:
	@FAMILLES="$(FAMILLES_DEMANDEES)" LENTEUR="$(LENTEUR)" $(LANCER) e2e-visible $(ARGS)

coverage:
	@FICHIERS="$(FICHIERS)" $(LANCER) couverture $(ARGS)

# Machine du mainteneur : construit l'image d'origin/main (quelle que soit la branche
# courante) et la pousse sur Docker Hub, tags latest et $VERSION. REFAIRE_LA_BASE=1
# reconstruit tout (systeme, venv). / Maintainer's machine: builds and pushes origin/main.
release:
	@bash scripts/release.sh

# Production uniquement : prepare le serveur (.env depuis env_prod_example, dossiers,
# controles). Ne remplace jamais un .env existant ; relancable a volonte.
# / Production only: prepares the server. Never overwrites an existing .env.
env:
	@bash scripts/fabriquer_env_prod.sh

# Production uniquement : la procedure vit dans le script (TECH_DOC/SESSIONS/DEPLOIEMENT/SPEC.md).
# / Production only: the procedure lives in the script.
update:
	@bash scripts/mise_a_jour_prod.sh

# Programme `make update` a 02:05 avec at, une heure creuse. Plus de fenetre horaire : le
# verrou partage avec la sauvegarde les tient a l'ecart l'une de l'autre. at garde le
# dossier et l'environnement de la personne qui programme ; le resultat se lit dans
# logs/mise_a_jour_*.log.
# MIGRER et EXECUTEUR sont transmis : vides, le script choisit seul.
# L'image est tiree tout de suite (sans effet sur la prod) : a 02:05 le pull est instantane.
# Voir la tache : atq — l'annuler : atrm <numero>.
# / Schedules `make update` at 02:05 with at; pre-pulls the image now.
update_nuit:
	@command -v at >/dev/null || { echo "at n'est pas installe : apt install at" >&2; exit 1; }
	@docker pull tibillet/lespass:latest
	@echo "cd $(CURDIR) && MIGRER=$(MIGRER) EXECUTEUR=$(EXECUTEUR) make update" | at 02:05
	@atq

# Les familles n'ont pas d'action propre : elles precisent make e2e / make e2e-visible.
# / Families have no action of their own: they narrow make e2e / make e2e-visible.
$(FAMILLES_E2E):
	@:
