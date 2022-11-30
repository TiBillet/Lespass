import {test} from '@playwright/test'
import * as dotenv from 'dotenv'
dotenv.config('../.env')

const email = process.env.TEST_MAIL

test.describe('Api.', () => {
  test('Place rafftou create', async ({request}) => {


    /*
    création "api key":
    relation "BaseBillet_externalapikey" does not exist LINE 1: SELECT COUNT(*) AS "__count" FROM "BaseBillet_externalapikey...





    const newIssue = await request.post(`/api/place`, {
      data: {
        organisation: "Raffinerie",
        short_description: "Tiers-lieux eco-culturel du Billetistan",
        long_description: "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        phone: "0692929292",
        email: "jturbeaux+raff@pm.me",
        site_web: "https://laraffinerie.re/",
        postal_code: "97410",
        img_url: "https://picsum.photos/1920/1080.jpg",
        logo_url: "https://picsum.photos/300/300.jpg",
        categorie: "S",
        stripe_connect_account: "acct_1M7YYOE0J1b3jXbW"
      }
    });
    expect(newIssue.ok()).toBeTruthy();

    console.log('retour =', retour)
*/
  })
})
