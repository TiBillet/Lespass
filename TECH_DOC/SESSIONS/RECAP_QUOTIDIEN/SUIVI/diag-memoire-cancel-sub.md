# Diagnostic memoire : test cancel_sub (recap quotidien)

## Cause
Probleme du TEST seul (mauvais mock). `patch("ApiBillet.views.stripe.Subscription.modify")` renvoie un MagicMock nu.
Le test POST sans en-tete HTMX : la vue prend la branche JSON (ApiBillet/views.py, ~l.680) :
`Response({... 'stripe': {'id': sub.id, 'cancel_at_period_end': sub.cancel_at_period_end}})`.
`sub.id` est donc un MagicMock. Au rendu, `rest_framework/utils/encoders.py:61-63` (JSONEncoder.default) fait
`hasattr(obj, 'tolist')` -> vrai pour un MagicMock (tout attribut existe) -> `return obj.tolist()` -> un nouveau MagicMock
-> le JSON l'encode a nouveau -> `default()` -> recursion/allocation sans fin : MemoryError (24-28 Go sans limite).
Ce n'est ni une boucle de redirection, ni le gabarit, ni un logger.

## Preuve
Test isole sous `ulimit -v 6000000` : `json.dumps({"id": MagicMock().id}, cls=rest_framework.utils.encoders.JSONEncoder)`
-> `MemoryError` en ~19 s.
Meme appel avec `MagicMock(id="sub_x", cancel_at_period_end=True)` -> `{"id": "sub_x", "c": true}`, passe en 5 s.

## Recette d'un test correct
Donner des valeurs reelles au retour de Subscription.modify :
    with patch("ApiBillet.views.stripe.Subscription.modify",
               return_value=SimpleNamespace(id="sub_test_recap_1234", cancel_at_period_end=True)), \
         patch("ApiBillet.views.Configuration.get_stripe_connect_account", return_value="acct_test"), \
         patch("ApiBillet.views.RootConfiguration.get_solo"):
        ...
(le dernier patch peut rester MagicMock : get_stripe_api() n'est que affecte a stripe.api_key, jamais serialise.)
Regle : ne jamais laisser un MagicMock dans une donnee passee a Response/JSON.

## Production
Non concernee : le vrai stripe.Subscription renvoie un objet avec id (str) et cancel_at_period_end (bool). Aucun defaut de la vue.

## Nettoyage
tests/pytest/test_diag_memoire_cancel_sub.py supprime (verifie par ls). Aucun autre fichier modifie.
