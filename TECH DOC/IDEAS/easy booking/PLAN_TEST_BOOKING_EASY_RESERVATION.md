# Plan test Playwright : Bouton "Je m'inscris" (FREERES)

## Fichier

`tests/playwright/tests/XX-booking-easy-reservation.spec.ts`

## Pre-requis

- Un event avec uniquement des produits FREERES dans la DB de test
- Un compte utilisateur connecte
- Un event avec au moins un produit BILLET (pour verifier le cas inverse)

## Tests a ecrire

### Test 1 : Le bouton "Je m'inscris" s'affiche pour un user connecte sur un event FREERES

1. Se connecter
2. Aller sur `/event/<slug-freeres>/`
3. Verifier que `[data-testid="booking-easy-reservation"]` est visible
4. Verifier que `[data-testid="booking-open-panel"]` n'existe PAS

### Test 2 : Le bouton offcanvas classique s'affiche sur un event avec BILLET

1. (toujours connecte)
2. Aller sur `/event/<slug-billet>/`
3. Verifier que `[data-testid="booking-open-panel"]` est visible
4. Verifier que `[data-testid="booking-easy-reservation"]` n'existe PAS

### Test 3 : Le bouton "Je m'inscris" ne s'affiche PAS pour un user anonyme

1. Se deconnecter (ou ouvrir une session anonyme)
2. Aller sur `/event/<slug-freeres>/`
3. Verifier que `[data-testid="booking-easy-reservation"]` n'existe PAS
4. Verifier que `[data-testid="booking-open-panel"]` est visible (offcanvas classique)

### Test 4 (futur, quand le back sera code) : Clic sur "Je m'inscris" cree une reservation

1. Se connecter
2. Aller sur `/event/<slug-freeres>/`
3. Cliquer sur `[data-testid="booking-easy-reservation"]`
4. Verifier la reponse (redirection ou message de confirmation)
5. Verifier en DB : `docker exec lespass_django poetry run python manage.py verify_test_data --type reservation --email <EMAIL>`
