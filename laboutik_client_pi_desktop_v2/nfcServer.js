import { MTE } from './httpServer/index.js'
import { readConfigFile, writeConfigFile, startBrowser, testNetworkStatus, readfile, testDiscoveryServer } from './modules/commun.js'
import { env } from './env.js'
import * as os from 'node:os'
import { cors } from './modules/cors.js'
import { proxyDiscoveryClaim } from './modules/proxyDiscovery.js'
import { checkPrinter, print } from './modules/devices/thermalPrinterTcp.js'


const root = process.cwd()
let refAskTagId = null, clientGlobale = null, nfc = null

// 1 - affiche messages des appels socket.io et leurs méthodes uniquement
// 2 - url et méthodes affiliées
// 10 - tous les logs
const logLevel = env.logLevel

function socketEmit(msg, data) {
  if (clientGlobale !== null) {
    clientGlobale.emit(msg, data)
  }
}

function initNfcDevice() {
  // console.log('-> initNfcDevice')
  return new Promise((resolve, reject) => {
    try {
      // modules à importés en fonction du type d'application (pi ou desktop)
      const deviceFiles = {
        desktop: 'acr122u-u9.js',
        pi: 'vma405-rfid-rc522.js'
      }
      const pathDevice = root + '/modules/devices/' + deviceFiles[env.type_app]
      console.log('pathDevice =', pathDevice)

      import(pathDevice).then(module => {
        const { startListening, stopListening, getStatus } = module
        resolve({
          startListening,
          stopListening,
          getStatus
        })
      }).catch(err => {
        console.log('-> initNfcDevice, erreur chargement module:', err)
        reject(err)
      })
    } catch (error) {
      console.log('-> initNfcDevice,', error)
      reject(error)
    }
  })
}

async function getPrintersStatus() {
  let printersStatus = []
  for (let i = 0; i < env.ipPrinters.length; i++) {
    const ip = env.ipPrinters[i]
    const status = await checkPrinter(ip)
    // console.log('-> getPrinterStatus - ip =', ip, '  --  status =', status,' --  ', new Date())
    printersStatus.push({ ip, status })
  }
  socketEmit('printersStatus', printersStatus)
}


async function initListenDevicesStatus() {
  try {
    // network
    const networkStatus = await testNetworkStatus()
    socketEmit('networkStatus', networkStatus)
    // console.log('networkStatus =', networkStatus)   

    // demande de status du nfc reader (one shot too)
    if (clientGlobale !== null) {
      nfc.getStatus(clientGlobale)
    }
  } catch (error) {
    console.log("-> initListenDevicesStatus,", error)
  }

  // relance les écoutes dans 5 secondes
  const timeoutId = setTimeout(initListenDevicesStatus, 5000)
}


function renderIndexHtml(req, res, headers, options) {
  const path = root + '/www/index.html'
  let file = readfile(path)
  if (file !== null) {
    // ajoute le bon PORT au template index.html
    file = file.replace('{{ port }}', env.PORT)
    headers["Content-Type"] = "text/html; charset=utf-8"
    res.writeHead(200, headers)
    res.write(file)
    res.end()
  } else {
    headers["Content-Type"] = "text/html; charset=utf-8"
    res.writeHead(500, headers)
    res.end('<h1>Error index.html file !</h1>')
  }
}


function writeConfFile(req, res, body, headers) {
  console.log('-> writeConfFile')
  try {
    const result = writeConfigFile(body)
    if (result.status === true) {
      res.writeHead(200, headers)
      res.write(JSON.stringify(result))
      res.end()
    } else {
      res.writeHead(400, headers)
      res.write(JSON.stringify(result))
      res.end()
    }
  } catch (error) {
    res.writeHead(400, headers)
    res.write(JSON.stringify({ error }))
    res.end()
  }
}


function readConfFile(req, res, headers, options) {
  try {
    const confFile = readConfigFile()
    res.writeHead(200, headers)
    res.write(JSON.stringify(confFile))
    res.end()
  } catch (error) {
    res.writeHead(400, headers)
    res.write(JSON.stringify({ error }))
    res.end()
  }
}

async function changeServerDiscovery(req, res, body, headers, data) {
  try {
    console.log('-> changeServerDiscovery - data =', data);

    // 1 - url conforme
    const url = data.server_discovery
    const urlRegex = /^(https?:\/\/)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(\/[^\s]*)?$/
    const urlOk = urlRegex.test(url)
    console.log('urlOk =', urlOk)
    if (urlOk === false) {
      throw new Error("Url non conforme.")
    }

    // 2 - serveur joignable
    const testServer = await testDiscoveryServer(url)
    console.log('testServer =', testServer)
    if (testServer !== 'available') {
      throw new Error("Serveur non disponible ou inconnu")
    }

    // 3 - read conf
    const confFile = readConfigFile()
    console.log('confFile =', confFile)

    // 4 - change serveur discovery in config file
    confFile.server_pin_code = url

    // 5 save conf
    const result = writeConfigFile(confFile)
    if (result.status !== true) {
      throw new Error("Error - save  config file.")
    }

    // send url to say ok
    res.writeHead(200, headers)
    res.write(JSON.stringify({url}))
    res.end()
  } catch (error) {
    res.writeHead(400, headers)
    res.write(JSON.stringify({ error: error.message }))
    res.end()
  }
}

// encapsulate all errors
try {
  // initialise le nfc
  nfc = await initNfcDevice()
  nfc.startListening(clientGlobale)

  // init listen networ Status
  initListenDevicesStatus()

  // --- socket.io handler ---
  const socketHandler = (client) => {
    clientGlobale = client
    console.log("Client connecté !")

    clientGlobale.on("getConfigFile", () => {
      // console.log('getConfigFile');
      // send config file
      const confIle = readConfigFile()
      socketEmit('sendConfigFile', confIle)
    })

    clientGlobale.on("nfcStartListening", (data) => {
      // data = objet avec uuid
      try {
        nfc.startListening(clientGlobale, data)
      } catch (error) {
        console.log("-> nfcStartListening,", error)
      }
    })

    clientGlobale.on("nfcStopListening", () => {
      nfc.stopListening()
    })

    clientGlobale.on("getPrintersStatus", () => {
      getPrintersStatus()
    })

    clientGlobale.on("disconnect", () => {
      console.log("Client déconnecté !!")
    })
  }

  const optionsServer = {
    socketHandler,
    config: {
      PORT: env.PORT,
      HOST: env.HOST,
      // racine du projet = process.cwd()
      PUBLIC: process.cwd() + '/www',
      DEBUG: true,
      logLevel: env.logLevel
    }
  }
  const app = new MTE(optionsServer)

  // ajout du midleware cors
  app.use(cors, {
    origin: '*',
    headers: 'Sentry-trace, Baggage, Access-Control-Allow-Headers, Origin,Accept, X-Requested-With, Content-Type, Access-Control-Request-Method, Access-Control-Request-Headers',
    methods: 'GET,HEAD,PUT,PATCH,POST,DELETE',
    optionsSuccessStatus: 204,
    maxAge: 2592000,
    credentials: true
  })

  // routes
  app.addRoute('/api/discovery/claim/', proxyDiscoveryClaim, { urlProxy: env.server_pin_code + '/api/discovery/claim/' }) // proxy
  app.addRoute('/read_config_file', readConfFile)
  app.addRoute('/write_config_file', writeConfFile)
  app.addRoute('/', renderIndexHtml)
  app.addRoute('/change_server_discovery', changeServerDiscovery)

  app.listen((host, port) => {
    console.log(`Lancement du serveur à l'adresse : ${port === 443 ? 'https' : 'http'}://${host}:${port}/`)
    console.log(`Single server version ${app.version} (c) filaos974`)
  })

  // on prod
  startBrowser(`http://${env.HOST}:${env.PORT}/`)

} catch (error) {
  console.log('error', error)
}
