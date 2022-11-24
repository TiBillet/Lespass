import {test} from '@playwright/test'

test.use({viewport: {width: 1024, height: 800}})

let page

test.describe('Regroupe des tests.', () => {
  test('login_hardware', async ({browser}) => {
     // 1 - connexion appareil client
    page = await browser.newPage()
    // première connexion
    await page.goto('https://en.wikipedia.org/wiki/Poisson_distribution')
    await page.pause()
  })
})