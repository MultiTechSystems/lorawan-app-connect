# lorawan-app-connect
Default mPower&trade; LoRaWAN&reg; application and server API implementation for a distributed LoRaWAN network. The application will communicate with the embedded LoRaWAN network server on a MultiTech Conduit&reg; and forward messages to the configured HTTP(S) or MQTT(S) servers. Configuration for a single server can be provided via the mPower WebUI or for multiple servers using the [MultiTech Lens&reg;](https://www.multitech.com/brands/lens) cloud service.

# Architecture

The diagram below show the components for a distributed LoRaWAN network using MultiTech hardware and cloud services with a 3rd Party API. The Conduit can be one of server models such as MTCAP, MTCDT or MTCDTIP running the mPower firmware version 5.3.0 or later.

![Components](/images/3rd%20Party%20API.png)

# Ladder Diagram
The diagram below shows the messages passed between a LoRaWAN end-device (Dot), LoRaWAN Network Server (Conduit), LoRaWAN Join Server and Application/Network Management Server (Lens) and a 3rd Party API.

![Ladder Diagram](/images/3rd-Party-API-Ladder.png)

In the diagram the Class A Rx1 Offset has been increased to five seconds to allow the HTTPS request to be returned in time for a possible Class A downlink to be scheduled to the end-device. The HTTPS connection adds latency that can extend beyond the default one second Rx1 Delay.

# Installation

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

## Application Configuration

    url: server URL
    options:
      server_cert: server certificate
      clent_cert: client certicate
      apikey: client private key
      check_hostname: boolean to verifiy the server hostname

## HTTPS API Protocol

### Paths

* POST /api/lorawan/v1/\<APP-EUI>/\<GW-UUID>/init
    ```json
    { "gateways_euis": [ "00-80-00-00-a0-00-0f-4d" ] }
    ```

* POST /api/lorawan/v1/\<APP-EUI>/\<GW-UUID>/close

* POST /api/lorawan/v1/\<APP-EUI>/\<DEV-EUI>/up
  * Field descriptions can be found on [multitech.net](https://www.multitech.net/developer/software/lora/lora-network-server/mqtt-messages/)

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

* Publish lorawan/\<APP-EUI>/\<GW-UUID>/init
* Publish lorawan/\<APP-EUI>/\<GW-UUID>/close
* Publish lorawan/\<APP-EUI>/\<GW-UUID>/disconnected
* Publish lorawan/\<APP-EUI>/\<DEV-EUI>/up
* Publish lorawan/\<APP-EUI>/\<DEV-EUI>/joined
* Subscribe lorawan/\<APP-EUI>/\<DEV-EUI>/down

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