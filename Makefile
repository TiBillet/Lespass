# Table des matieres des lancements de tests. La logique vit dans scripts/lancer_tests.sh.
# / Table of contents for test runs. The logic lives in scripts/lancer_tests.sh.
.PHONY: help test e2e e2e-visible coverage

LANCER := bash scripts/lancer_tests.sh

help:
	@echo "Lespass — lancer les tests"
	@echo ""
	@echo "  make test          pytest, tests Stripe reel compris (cle sk_test, reseau)"
	@echo "  make e2e           E2E navigateur, parcours Stripe compris (stripe listen dans byobu)"
	@echo "  make e2e-visible   E2E dans un Chromium visible sur l'ecran, ralenti, avec journal"
	@echo "  make coverage      pytest + couverture du code (total + htmlcov/)"
	@echo ""
	@echo "  Cibler :  make test ARGS=\"tests/pytest/test_stripe_refund.py -k panier\""
	@echo "  Detail :  make coverage FICHIERS=\"BaseBillet/services_panier.py,BaseBillet/services_commande.py\""
	@echo "  Suivre :  make e2e-visible LENTEUR=1500 ARGS=\"tests/e2e/test_panier_flow.py\""
	@echo ""
	@echo "  Aucun test Stripe n'est ignore : si Stripe ou stripe listen manque,"
	@echo "  les tests concernes ECHOUENT."

test:
	@$(LANCER) python $(ARGS)

e2e:
	@$(LANCER) e2e $(ARGS)

e2e-visible:
	@LENTEUR="$(LENTEUR)" $(LANCER) e2e-visible $(ARGS)

coverage:
	@FICHIERS="$(FICHIERS)" $(LANCER) couverture $(ARGS)
