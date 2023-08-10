export function log (options) {
  const userLevel = 2

  if (options.message) {
    console.log(options.message)
  }

  if(userLevel === 1) {
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
}