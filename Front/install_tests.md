# Playwright
. https://playwright.dev/docs/intro

## Installer
```
npm i -D @playwright/test
# install supported browsers
npx playwright install
```

## Lancer un test
```
npm run test
# avec un visuel
npm run test -- --headed
# un navigateur
npm run test -- --project=firefox
# un fichier
npm run test -- Modallogin.spec.js
```

## Configurer package.json
```
"scripts": {
  ...
  "test": "playwright test --config=tests/playwright.config.js",
  "testf": "playwright test --project=firefox --config=tests/playwright.config.js",
  "testfv": "playwright test --project=firefox --config=tests/playwright.config.js --headed",
  ...
}
```
## Configurer (tests/playwright.config.js), tests sur plusieurs navigateurs
```
const { devices } = require('@playwright/test')
const config = {
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  use: {
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
}
module.exports = config
```

## Divers
. Vous aurez des paquets à installer suivant votre système