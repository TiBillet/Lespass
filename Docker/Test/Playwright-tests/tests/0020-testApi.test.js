import {test} from '@playwright/test'


const urlTester = 'https://raffinerie.django-local.org/iframeevent/ziskakan-072625-1830/'

test.describe.skip('Api.', () => {
  test('Réservation.', async ({browser, request}) => {

    const context = await request.newContext({
      baseURL: 'https://raffinerie.django-local.org/api',
    })

    const retour = await request.post('/reservations/', {
      data: JSON.stringify({
        event: '97696d98-bc9b-43ae-8f50-6326dd7877af',
        email: 'filaos974@hotmail.com',
        chargeCashless: 0,
        prices: [
          {
            uuid: '85156abc-b144-400f-bf5f-d3244779f57d',
            qty: 1,
            customers: [{
              uuid: 'a4348e35-5bc6-4024-8401-542d5d12d481',
              first_name: '',
              last_name: ''
            }]
          },
          {
            uuid: '093cd863-3395-4e50-81f0-ba22e5869ef2',
            qty: 1
          }
        ],
        options: []
      })
    })

    console.log('retour =', retour)

  })
})
