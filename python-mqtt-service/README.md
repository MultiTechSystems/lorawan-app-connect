# MQTT Application

## Network

![Architecture](/images/network-diagram.png)

## Setup

    python >3.7.3
    pip3 install -r requirements.txt
    # Run the server
    python3 server.py

## MQTT configuration

- server: Broker Server IP
- port: Broker Server Port

## MQTT Protocol

- Publishes

  - lorawan/\<APP-EUI>/\<GW-UUID>/init
    - ```json
      {
        "gateways_euis": ["00-80-00-00-d0-00-01-ff"],
        "time": "2022-08-31T19:38:59.666890Z"
      }
      ```
  - lorawan/\<APP-EUI>/\<GW-UUID>/close
    - No Message
  - lorawan/\<APP-EUI>/\<GW-UUID>/disconnected
    - No Message
  - lorawan/\<APP-EUI>/\<DEV-EUI>/joined
    - ```json
      {
        "appeui": "16-ea-76-f6-ab-66-3d-80",
        "gweui": "00-80-00-00-d0-00-01-ff",
        "remote": false,
        "time": "2022-08-31T20:01:33.139592Z"
      }
      ```
  - lorawan/\<APP-EUI>/\<DEV-EUI>/up
    - ```json
      {
        "jver": 1,
        "tmst": 1480759655,
        "time": "2022-08-31T20:02:39.470982Z",
        "tmms": 1346011377470,
        "chan": 8,
        "rfch": 0,
        "freq": 903,
        "mid": 16,
        "stat": 1,
        "modu": "LORA",
        "datr": "SF8BW500",
        "codr": "4/5",
        "rssis": -12,
        "lsnr": 12.5,
        "foff": -3206,
        "rssi": -12,
        "opts": "",
        "size": 9,
        "fcnt": 0,
        "cls": 0,
        "port": 1,
        "mhdr": "401d97ef01800000",
        "data": "AAIAWgBkgAYU",
        "appeui": "16-ea-76-f6-ab-66-3d-80",
        "deveui": "00-80-00-ff-00-00-00-01",
        "devaddr": "01ef971d",
        "ack": false,
        "adr": true,
        "gweui": "00-80-00-00-d0-00-01-ff",
        "seqn": 0
      }
      ```
  - lorawan/\<APP-EUI>/\<DEV-EUI>/moved
    - List of GW-EUIs
    - ```json
      ["00-80-00-00-d0-00-01-ff"]
      ```

- Subscribed

  - lorawan/\<APP-EUI>/\<DEV-EUI>/+
  - lorawan/\<GW-EUI>/\<DEV-EUI>/+
  - lorawan/\<GW-UUID>/\<DEV-EUI>/+

  - Supported topics
    - down - downlinks to schedule
    - clear - clear downlinks for a device
    - api_req - send API request
    - lora_req - send request for lora-query utility
    - log_req - send request for log file
      - lines - number of lines to returned
      - file - name of file to read from /var/log folder
