# playwright

## installer les modules nodejs
```
npm i
npx playwright install
```

## Lancer les Tests
1 - Lancer le script pour la mise en place de l'infrastucture de la billetterie (db non peuplée):  
```
cd .../TiBillet/Docker/Development/
./test_dev.sh
```

2 - Lancer le peuplement de la base de données et le test "iframeevent"
```
cd .../TiBillet/Docker/Test/Playwright-tests
npx playwright test --headed
   #ou sans navigateur
npx playwright test
```

## Infos

### Lancer les tests (/tests/*.test.js)
```
npx playwright test
npx playwright test --headed
npx playwright test --reporter=line
```

### Lancer un test
```
npx playwright test 0010-contexte_loginHardware.test.js
```

### Voir le raport
```
npx playwright show-report
```

### Ne faire qu'un test (.only)
test.describe.only

### Bloquer l'exécution d'un test (.only)
test.describe.skip

### ".only" et ".skip" peuvent être utilisé à l'intérieur d'un groupe "test.describe"
