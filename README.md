# lorawan-app-connect
Default mPower&trade; LoRaWAN&reg; application and server API implementation for a distributed LoRaWAN network. The application will communicate with the embedded LoRaWAN network server on a MultiTech Conduit&reg; and forward messages to the configured HTTP(S) or MQTT(S) servers. Configuration for a single server can be provided via the mPower WebUI or for multiple servers using the [MultiTech Lens&reg;](https://www.multitech.com/brands/lens) cloud service.

The default application feature allows last mile bi-directional connectivity from the gateway to a cloud application without needing to deploy custom code on each gateway. An existing API can add compatible end-points allowing LoRaWAN uplinks and downlinks to be consumed and produced by the cloud application.

It also provides a starting point for those wanting to bring intelligence to the edge by customizing the default application.

# Architecture

The diagram below show the components for a distributed LoRaWAN network using MultiTech hardware and cloud services with a 3rd Party API. The Conduit can be one of server models such as MTCAP, MTCDT or MTCDTIP running the mPower firmware version 5.3.0 or later.

![Components](/images/3rd%20Party%20API.png)



# Network Messages
The diagram below shows the messages passed between a LoRaWAN end-device (Dot), LoRaWAN Network Server (Conduit), LoRaWAN Join Server and Application/Network Management Server (Lens) and a 3rd Party API.

![Ladder Diagram](/images/3rd-Party-API-Ladder.png)

In the diagram the Class A Rx1 Offset has been increased to five seconds to allow the HTTPS request to be returned in time for a possible Class A downlink to be scheduled to the end-device. The HTTPS connection adds latency that can extend beyond the default one second Rx1 Delay.

1. The Dot sends join reqeust over-the-air
2. The Conduit received the join request and forwards the request to the Lens Join Server
3. The Lens Join Server authenticates the request and issues a Join Accept message
4. The Conduit receives the Join Accept message, AppEUI and Session Keys from the Lens Join Server
5. The Conduit send the Join Accept message over-the-air
6. The Conduit reqeusts additional App Info from Lens if it is not cached
7. If is a new app the Init Msg is sent to the 3rd Party API
8. The 3rd Party API returns configuration data in the Init Msg response
9. A device joined message is sent to the 3rd Party API
10. When an uplink is received by the Conduit it is forwarded to the 3rd Party API
11. The 3rd Party API can response to the Uplink message with a list of downlinks
12. The Conduit will periodically request downlink packets from the 3rd Party API
13. The Conduit will schedule received downlinks for transmission to a Dot


# Installation

The example API projected should be installed and run on a PC with node.js support installed.

```bash
$ npm install
```

# Running the HTTP/HTTPS server

```bash
$ node app.js
```

# Application Location

The application source is located in the mPower file system at /opt/lora/app-connect.py. A [custom application](http://www.multitech.net/developer/software/aep/creating-a-custom-application/) can be created and deployed via DeviceHQ to install and run the python script.

# HTTP(S) Applications

A default application can be configured using mPower 5.3.x firmware.

![mPower Network Configuration](/images/LoRaWAN_Networking.png)

## Application Configuration

    url: server URL
    eui: application identifier
    options:
      server_cert: server certificate
      clent_cert: client certicate
      apikey: client private key
      check_hostname: boolean to verifiy the server hostname

## HTTPS API Protocol

### Paths

* POST /api/lorawan/v1/\<APP-EUI>/\<GW-UUID>/init
  * BODY
    ```json
    { "gateways_euis": [ "00-80-00-00-a0-00-0f-4d" ] }
    ```
  * RESPONSE
    * The response can contain configuration data for the application on Conduit.
      * Timeout in seconds for HTTP requests
      * Queue size for the number of requests to retain while disconnected
      * Downlink query interval for the number of seconds between HTTP requests for downlinks
    ```json
    {
        "timeout": 20,
        "queue_size": 10,
        "downlink_query_interval": 30
    }
    ```


* POST /api/lorawan/v1/\<APP-EUI>/\<GW-UUID>/close

* POST /api/lorawan/v1/\<APP-EUI>/\<DEV-EUI>/up
  * Field descriptions can be found on [multitech.net](https://www.multitech.net/developer/software/lora/lora-network-server/mqtt-messages/)
    * BODY
    ```json
    {
        "tmst": 2450008103,
        "time": "2020-09-16T18:29:35.263610Z",
        "tmms": 1284316193263,
        "chan": 8,
        "rfch": 0,
        "freq": 904.6,
        "stat": 1,
        "modu": "LORA",
        "datr": "SF8BW500",
        "codr": "4/5",
        "lsnr": 10,
        "rssi": -66,
        "opts": "",
        "size": 7,
        "fcnt": 27,
        "cls": 0,
        "port": 1,
        "mhdr": "4012233112801b00",
        "data": "bWVzc2FnZQ==",
        "appeui": "16-ea-76-f6-ab-66-3d-80",
        "deveui": "00-80-00-00-00-01-58-34",
        "devaddr": "12312312",
        "ack": false,
        "adr": true,
        "gweui": "00-80-00-00-a0-00-0f-4d",
        "seqn": 27
    }
    ```
  * RESPONSE
    * The API can send any downlinks in the response
    ```json
    [
        {"deveui":"00-11-22-33-44-55-66-77", "data": "AQ=="}
    ]
    ```

  * POST /api/lorawan/v1/\<APP-EUI>/up
  * If more than one uplink is available to be sent, up to ten may be sent in an array to the APP-EUI uplink path, this helps if many uplinks are being received in a burst.
  * Field descriptions can be found on [multitech.net](https://www.multitech.net/developer/software/lora/lora-network-server/mqtt-messages/)
    * BODY
    ```json
    [
      {
          "tmst": 2450008103,
          "time": "2020-09-16T18:29:35.263610Z",
          "tmms": 1284316193263,
          "chan": 8,
          "rfch": 0,
          "freq": 904.6,
          "stat": 1,
          "modu": "LORA",
          "datr": "SF8BW500",
          "codr": "4/5",
          "lsnr": 10,
          "rssi": -66,
          "opts": "",
          "size": 7,
          "fcnt": 27,
          "cls": 0,
          "port": 1,
          "mhdr": "4012233112801b00",
          "data": "bWVzc2FnZQ==",
          "appeui": "16-ea-76-f6-ab-66-3d-80",
          "deveui": "00-80-00-00-00-01-58-34",
          "devaddr": "12312312",
          "ack": false,
          "adr": true,
          "gweui": "00-80-00-00-a0-00-0f-4d",
          "seqn": 27
      },
      {
          "tmst": 2451008103,
          "time": "2020-09-16T18:29:36.263610Z",
          ...
          "deveui": "00-80-00-00-00-03-33-34",
          "devaddr": "0013FABE",
          "ack": false,
          "adr": true,
          "gweui": "00-80-00-00-a0-00-0f-4d",
          "seqn": 894
      }
    ]
    ```
  * RESPONSE
    * The API can send any downlinks in the response
    ```json
    [
        {"deveui":"00-11-22-33-44-55-66-77", "data": "AQ=="}
    ]
    ```

* POST /api/lorawan/v1/\<APP-EUI>/\<DEV-EUI>/joined
    ```json
    {
        "appeui": "16-ea-76-f6-ab-66-3d-80",
        "gweui": "00-80-00-00-a0-00-0f-4d",
        "remote": false
    }
    ```

* GET  /api/lorawan/v1/\<APP-EUI>/down
    * Provides a list of DEV-EUI values
    * Returns list of downlinks to queue
    ```json
    [
        {"deveui":"00-11-22-33-44-55-66-77", "data": "AQ=="}
    ]
    ```

### TLS Certificates

[Linux Certificate Doc](https://www.golinuxcloud.com/openssl-create-client-server-certificate/)

* server_cert.pem - Public cerificate given out to connecting clients for server authentication
* server_key.pem - Private key used to create client certificates for client authentication




# MQTT Applications

## Application configuration
    url: mqtts://test.mosquitto.org:8883
    options:
      server_cert: server certificate
      clent_cert: client certicate
      apikey: client private key
      username: MQTT username
      password: MQTT password

## MQTT Protocol

* Publish
  * lorawan/\<APP-EUI>/\<GW-UUID>/init
  * lorawan/\<APP-EUI>/\<GW-UUID>/close
  * lorawan/\<APP-EUI>/\<GW-UUID>/disconnected
  * lorawan/\<APP-EUI>/\<DEV-EUI>/up
  * lorawan/\<APP-EUI>/\<DEV-EUI>/joined
* Subscribe
  * lorawan/\<APP-EUI>/\<DEV-EUI>/down

### Test brokers

* https://test.mosquitto.org/
  * Supports TLS1.2 server certificate, client certificate and apikey settings for authentication
  * Application configuration
    * url: mqtts://test.mosquitto.org:8883
    * options:
      * server_cert: server certificate
      * clent_cert: client certicate
      * apikey: client private key
* https://flespi.com/mqtt-api
  * Supports authentication using username access token for authentication
  * Application configuration
    * url: mqtt://mqtt.flespi.io
    * options:
      * username: \<FLESPI-TOKEN>