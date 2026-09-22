# Table des matieres des lancements de tests. La logique vit dans scripts/lancer_tests.sh.
# / Table of contents for test runs. The logic lives in scripts/lancer_tests.sh.
.PHONY: help test test-stripe e2e e2e-stripe coverage

LANCER := bash scripts/lancer_tests.sh

help:
	@echo "Lespass — lancer les tests"
	@echo ""
	@echo "  make test          pytest, sans Stripe reel (hors reseau)"
	@echo "  make test-stripe   pytest + tests Stripe reel (cle sk_test, reseau)"
	@echo "  make e2e           E2E navigateur, sans Stripe reel"
	@echo "  make e2e-stripe    E2E complets (verifie que stripe listen tourne dans byobu)"
	@echo "  make coverage      pytest sans Stripe reel + couverture du code (total + htmlcov/)"
	@echo ""
	@echo "  Cibler :  make test ARGS=\"tests/pytest/test_stripe_refund.py -k panier\""
	@echo "  Detail :  make coverage FICHIERS=\"BaseBillet/services_panier.py,BaseBillet/services_commande.py\""
	@echo ""
	@echo "  Sans Stripe reel, les tests qui en ont besoin sont ignores"
	@echo "  et nommes en rouge en fin de run."

test:
	@$(LANCER) python sans-stripe $(ARGS)

test-stripe:
	@$(LANCER) python stripe $(ARGS)

e2e:
	@$(LANCER) e2e sans-stripe $(ARGS)

e2e-stripe:
	@$(LANCER) e2e stripe $(ARGS)

coverage:
	@FICHIERS="$(FICHIERS)" $(LANCER) couverture sans-stripe $(ARGS)
