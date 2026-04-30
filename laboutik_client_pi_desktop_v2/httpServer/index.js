import { typeMime } from './typeMine.js'
import http from 'http'
import fs from 'node:fs'
import { Server } from "socket.io"

let fichier = '', contentType = ''

// 1 - affiche messages des appels socket.io et leurs méthodes uniquement
// 2 - url et méthodes affiliées
// 10 - tous les logs
let logLevel

// --- serveur http/https ---
export class MTE {
  constructor(options) {
    this.listFonctions = []
    this.routes = []
    this.serveur = {}
    this.version = "MTE-1.0.0"
    this.socketHandler = options.socketHandler
    this.config = options.config
    this.io = {},
    logLevel = options.config.logLevel
  }

  addRoute(route, fonction) {
    this.routes.push({
      name: route,
      fonction
    })
  }

  setTerminalTitle(title) {
    process.stdout.write(
      String.fromCharCode(27) + "]0;" + title + String.fromCharCode(7)
    )
  }

  use(fonction, options) {
    if (typeof fonction !== 'function') {
      throw new Error('Il faut une fonction')
    }
    this.listFonctions.push({ func: fonction, options })
  }

  listen(callback) {
    const handler = async (req, res) => {
      let url = req.url, useProxy = false

      const origin = (req.headers.origin === undefined) ? `http://${this.config.HOST}:${this.config.HOST}` : req.headers.origin
      // console.log('url =', req.url, '  --  origin =', origin)

      let headers = {}

      const methode = req.method
      const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress || null
      if (logLevel === 2 || logLevel === 10) {
        console.log('-> url =', url, '  --  ip =', ip)
      }
      //console.log('-> methode =', methode, '  --  routes (post) =', this.routes)

      //midleware
      this.listFonctions.forEach((foncData) => {
        // console.log('-> call midleware :')
        foncData.func.call(this, req, res, headers, foncData.options)
      })

      const route = this.routes.find(obj => obj.name === url)

      if (methode === 'POST') {
        // réception des données
        let body = ''
        req.on("data", (chunk) => {
          body += chunk
        })

        req.on("end", () => {
          // recherche dans les routes
          if (route.name === url && useProxy === false) {
            route.fonction.call(this, req, res, body, headers)
          }
        })
      }

      if (methode === 'GET') {
        if (route?.name === url && useProxy === false) {
          route.fonction.call(this, req, res, headers)
        }
      }

      // vue gère la méthode "GET"
      if (methode === 'GET' && route?.name !== url && useProxy === false) {
        try {
          let fichier, posDerPoint, extention

          // index_origine.html
          if (url === '/' || url === '/index.html') {
            url = '/index.html'
          }

          fichier = this.config.PUBLIC + '/' + url.substring(1, url.length)
          posDerPoint = url.lastIndexOf('.')
          extention = url.substring(posDerPoint + 1, url.length)

          let contentType = typeMime[extention.toLowerCase()]
          if (contentType === undefined) {
            contentType = 'text/plain'
          }

          const ip = req.connection.remoteAddress
          if (logLevel === 2 || logLevel === 10) {
            console.log('-> fichier :' + fichier)
          }

          if (fs.existsSync(fichier) === true) {
            const contenuFichier = fs.readFileSync(fichier)
            // console.log('-> fichier :' + fichier + '  --  contentType = ' + contentType + '  --  extention = ' + extention + '   -> chargé !')
            headers["Content-Type"] = contentType
            res.writeHead(200, headers)
            res.write(contenuFichier)
            res.end()
          } else {
            headers["Content-Type"] = "text/html; charset=utf-8"
            res.writeHead(500, headers)
            res.end('<h1>' + 'Comment vas-tu ?' + '</h1>')
          }

        } catch (erreur) {
          console.log('->', erreur)
          headers["Content-Type"] = "text/html; charset=utf-8"
          res.writeHead(500, headers)
          res.end('<h1>' + 'Comment vas-tu ?' + '</h1>')
        }
      }
    }
    this.serveur = http.createServer(handler).listen(this.config.PORT, this.config.HOST, callback.call(this, this.config.HOST, this.config.PORT))

    // socket.io
    try {
      // activated if "this.socketHandler" defined
      if (this.socketHandler !== undefined) {
        // --- socket.io ---
        const options = {
          // allowEio3: true,
          cors: {
            origin: "*",
            methods: ["PUT", "GET", "POST"],
          },
        }
        this.io = new Server(this.serveur, options)
        this.io.on("connection", this.socketHandler)
        if (logLevel === 1 || logLevel === 10) {
          console.log('Socket.io up')
        }
      }

    } catch (error) {
      console.log('socket.io,', error)
    }

    return this.serveur
  }
}
