export function emitEvent(typeEvent, data) {
  // console.log('EmitEvent, typeEvent =', typeEvent, '  --  data =', data)
  const monEvenement = new CustomEvent(typeEvent, {
    detail: data,
    bubbles: true
  })
  document.body.dispatchEvent(monEvenement)
}
