// Copyright 2020 Multitech Systems Inc

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//      http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

var express = require('express')
const https = require('https')
const fs = require('fs')

var app = express()

// var host = '10.17.100.116'
var host = '0.0.0.0'
var port = 3000

var use_https = false

app.use(express.json()) // for parsing application/json
app.use(express.urlencoded({ extended: true })) // for parsing application/x-www-form-urlencoded

var opts = {}

if (use_https) {
  opts = {
    key: fs.readFileSync('server_key.pem'),
    cert: fs.readFileSync('server_cert.pem'),
    requestCert: true,
    rejectUnauthorized: false,
    ca: [fs.readFileSync('server_cert.pem')],
  }
}

if (use_https) {
  https.createServer(opts, app).listen(port, host, () => {
    console.log('Server running on https://' + host + ':' + port)
  })
} else {
  app.listen(port, host, () => {
    console.log('Server running on http://' + host + ':' + port)
  })
}

function check_auth(req, res) {
  if (use_https) {
    const cert = req.connection.getPeerCertificate()
    if (!req.client.authorized) {
      res.status(401).json({ message: 'Certificate rejected' })
      return false
    }
  }
  return true
}

app.get('/', (req, res) => {
  res.send('<a href="authenticate">Log in using client certificate</a>')
})

app.get('/authenticate', (req, res) => {
  const cert = req.connection.getPeerCertificate()
  if (req.client.authorized) {
    res.send(
      `Hello ${cert.subject.CN}, your certificate was issued by ${cert.issuer.CN}!`,
    )
  } else if (cert.subject) {
    res
      .status(403)
      .send(
        `Sorry ${cert.subject.CN}, certificates from ${cert.issuer.CN} are not welcome here.`,
      )
  } else {
    res
      .status(401)
      .send(`Sorry, but you need to provide a client certificate to continue.`)
  }
})

var down_deveui = ''
var down_data = 'AQAQAQ=='

var app_prefix_v1 = '/api/v1/lorawan/'

app.get(app_prefix_v1 + '*', (req, res) => {
  console.log(req.path, req.body)

  if (down_deveui != '') {
    res.json([{ deveui: down_deveui, data: down_data }])
    down_deveui = ''
  } else {
    res.json([])
  }
})

app.post(app_prefix_v1 + ':appeui/:gw_uuid/init', (req, res, next) => {
  if (!check_auth(req, res)) return

  console.log(req.path, req.body)
  res.json({ timeout: 20, queue_size: 10, downlink_query_interval: 30 })
})

app.post(app_prefix_v1 + ':appeui/:gw_uuid/close', (req, res, next) => {
  if (!check_auth(req, res)) return

  console.log(req.path, req.body)
  res.json({})
})

app.post(app_prefix_v1 + ':appeui/:deveui/joined', (req, res, next) => {
  if (!check_auth(req, res)) return

  console.log(
    'Path:',
    req.path,
    '\r\nBody:',
    req.body,
    '\r\nParams:',
    req.params,
  )
  res.json({})
})

app.post(app_prefix_v1 + ':appeui/:deveui/up', (req, res, next) => {
  if (!check_auth(req, res)) return

  console.log(
    'Path:',
    req.path,
    '\r\nBody:',
    req.body,
    '\r\nParams:',
    req.params,
  )
  if (req.body.size > 0) {
    down_deveui = req.body.deveui
    down_data = req.body.data
    res.json({ deveui: req.body.deveui, data: req.body.data })
  } else {
    res.json({})
  }
})
