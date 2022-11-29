# playwright

## installer les modules nodejs
```
npm i
npx playwright install
```

## Lancer les tests (/tests/*.test.js)
```
npx playwright test
npx playwright test --headed
npx playwright test --reporter=line
```

## Lancer un test
```
npx playwright test 0010-contexte_loginHardware.test.js
```

## Voir le raport
```
npx playwright show-report
```

## Ignorer des tests (.skip)
- test.describe.skip   
- test.skip

## Ne faire qu'un test (.only)
test.describe.only
