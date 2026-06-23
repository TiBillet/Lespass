export const cors = function (req, res, headers, options) {
  if (options.origin !== undefined) {
    headers['Access-Control-Allow-Origin'] = options.origin
  }

  if (options.methods !== undefined) {
    headers['Access-Control-Allow-Methods'] = options.methods
  }

  if (options.maxAge !== undefined) {
    headers['Access-Control-Max-Age'] = options.maxAge
  }

  if (options.credentials !== undefined) {
    headers['Access-Control-Allow-Credentials'] = options.credentials
  }

  if (options.headers !== undefined) {
    headers['Access-Control-Allow-Headers'] = options.headers
  }

  if (req.method === 'OPTIONS') {
    res.writeHead(options.optionsSuccessStatus, headers)
    res.end()
  }
}