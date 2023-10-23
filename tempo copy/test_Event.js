import { event } from './data_event.js'
import { membershipsData } from './data_memberships.js'

// console.log('event =', event)

event.products.forEach((product) => {
  product.prices.forEach((price) => {
    if (price.adhesion_obligatoire === null) {
      price["customers"] = [{first_name: '', last_name: ''}]
    } else {
      let newProduct = membershipsData.find(membership => membership.uuid === price.adhesion_obligatoire)
      newProduct['type'] = 'membership'
      newProduct["customers"] = [{first_name: '', last_name: '', phone: '', postal_code: ''}]
      event.products.push(newProduct)
    }
  })
})

event.products.forEach((product) => {
  // console.log('product.name =', product.name, '  --  uuid =', product.uuid)
  console.log('product=', product)
  console.log('------------------')
})