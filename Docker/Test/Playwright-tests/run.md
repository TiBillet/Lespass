# Playwright

## installation de node et npm par Volta
### Installer Volta
```
curl https://get.volta.sh | bash
```

### Installer une vesrion donnée de nodejs (18.12.1)
```
volta install node@18.12.1
```

### Installer une vesrion donnée de npm (8.19.2)
```
volta install npm@8.19.2
```

## installer les dépendences de playwright
```
npm i
npx playwright install
```

## Lancer les Tests
### 1 - Lancer le script pour la mise en place de l'infrastucture de la billetterie (db non peuplée):  
```
cd .../TiBillet/Docker/Development/
./test_dev.sh
```
Attention: ne pas utiliser postman pour peupler la db, le fichier de tests 00010-db_peuplement_initial_billetterie.test.js
le fait.

### 2 - Lancer les tests playwright:
#### Avec le container docker
```
cd .../TiBillet/Docker/Test/Playwright-tests
docker compose up -d
npx playwright test --reporter=line
```

#### En locale (débug graphique)
```
cd .../TiBillet/Docker/Test/Playwright-tests
npx playwright test --headed
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
npx playwright test 0010-xxxxxxxxxxxx.test.js
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

### Fixer une version de nodej et npm pour un projet
- Aller à la racine du projet, un fichier package.json doit existé, le cas échéant "npm init -y".   
- Fixer la versionde node à "18.12.1" et la version de npm à "8.19.2":
```
volta pin node@18.12.1
volta pin npm@8.19.2
```
