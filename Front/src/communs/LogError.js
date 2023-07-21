export function log (options) {
  if (options.message) {
    console.log(options.message)
  }

  if (options.object) {
    console.log(JSON.stringify(options.object, null, 2))
  }

  if (options.error) {
    console.log(options.error)
  }

  if (options.raw) {
    console.log(options.raw)
  }
}