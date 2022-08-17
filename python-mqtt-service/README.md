# MQTT Application

## Network

![Architecture](/images/network-diagram.png)
## Setup
    python >3.7.3
    pip3 install -r requirements.txt
    # Run the server
    python3 server.py

## MQTT configuration
* server: Broker Server IP
* port: Broker Server Port

## MQTT Protocol

* Publishes
  * lorawan/\<APP-EUI>/\<GW-UUID>/init
  * lorawan/\<APP-EUI>/\<GW-UUID>/close
  * lorawan/\<APP-EUI>/\<GW-UUID>/disconnected
  * lorawan/\<APP-EUI>/\<DEV-EUI>/up
  * lorawan/\<APP-EUI>/\<DEV-EUI>/joined
  * lorawan/\<GW-EUI>/\<DEV-EUI>/moved

* Subscribed
  * lorawan/\<APP-EUI>/\<DEV-EUI>/+
  * lorawan/\<GW-EUI>/\<DEV-EUI>/+
  * lorawan/\<GW-UUID>/\<DEV-EUI>/+

  * Supported topics
    * down - downlinks to schedule
    * clear - clear downlinks for a device
    * api_req - send API request
    * lora_req - send request for lora-query utility
    * log_req - send request for log file
      * lines - number of lines to returned
      * file - name of file to read from /var/log folder
