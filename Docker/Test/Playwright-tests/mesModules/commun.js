import {test, request, expect} from '@playwright/test'
import moment from 'moment'
import * as dotenv from 'dotenv'
import * as fs from 'node:fs'

// ajoute les variables de .env aux variables d'environnement, accessibles par process.env.XXXXX
dotenv.config({path: './.env'})
// console.log('env =', process.env)
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
    const response = await context.post(process.env.URL_META + '/api/user/token/', {
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

export async function initData() {
  try {
    const data = fs.readFileSync('./mesModules/dataPeuplementInit.json', 'utf8')
    fs.writeFileSync('./mesModules/dataPeuplementTempo.json', data, 'utf8')
    console.log('Init dataPeuplement.')
  } catch (err) {
    console.log(`Error init dataPeuplement: ${err}`)
    return []
  }

}

export function getData() {
  try {
    const data = fs.readFileSync('./mesModules/dataPeuplementTempo.json', 'utf8')
    return JSON.parse(data)
  } catch (err) {
    console.log(`Error reading file from disk: ${err}`)
    return []
  }
}

export function updateData(dataR) {
  try {
    const data = JSON.stringify(dataR, null, 4)
    fs.writeFileSync('./mesModules/dataPeuplementTempo.json', data, 'utf8')
  } catch (err) {
    console.log(`Error writing file: ${err}`)
  }
}