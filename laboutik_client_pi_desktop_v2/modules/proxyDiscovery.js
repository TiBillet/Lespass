import { readConfigFile } from './commun.js'

export async function proxyDiscoveryClaim(req, res, body, headers) {
  try {
    const urlProxy = readConfigFile().server_pin_code + '/api/discovery/claim/'
    console.log('urlProxy =', urlProxy)

    const response = await fetch(urlProxy, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body
    })


    const data = await response.json()
    headers["Content-Type"] = "application/json"
    res.writeHead(response.status, headers)
    res.write(JSON.stringify(data))
    res.end()
  } catch (error) {
    console.log('-> proxyDiscoveryClaim error:', error)
    headers["Content-Type"] = "application/json"
    res.writeHead(502, headers)
    res.write(JSON.stringify({ error: 'Proxy error', message: error.message }))
    res.end()
  }
}
