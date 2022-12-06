import {test, request, expect} from '@playwright/test'
import moment from 'moment'
import * as dotenv from 'dotenv'

// ajoute les variables de .env aux variables d'environnement, accessibles par process.env.XXXXX
dotenv.config('../.env')

/**
 * Retourne la date d'aujourd'hui + un nombre aléatoire(1 à 365) de jours
 * @returns {moment.Moment}
 */
export function randomDate() {
  const dateR = moment()
  const randomNbDays = (Math.random() * 365) + 1
  dateR.add(randomNbDays, 'days')
  dateR.format("YYYY-MM-DD")
  return dateR
}

/**
 * Obtenir le root token
 * @returns {string}
 */
export const getRootJWT = async function () {
  return await test.step('GeT Root JWT Token', async () => {
    const context = await request.newContext({
      baseURL: process.env.URL_ROOT,
      ignoreHTTPSErrors: true
    })
    const response = await context.post(process.env.URL_ROOT + '/api/user/token/', {
      headers: {
        "Content-Type": "application/json"
      },
      data: {
        username: process.env.EMAIL_ROOT,
        password: process.env.PASSWORD_ROOT
      }
    })
    const retour = await response.json()
    expect(response.ok()).toBeTruthy()
    return retour.access
  })
}