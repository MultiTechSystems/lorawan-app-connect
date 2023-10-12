from flask import Flask, request, Response, redirect, url_for
from flask import render_template
from flask_assets import Environment, Bundle

from base64 import b64encode, b64decode
import paho.mqtt.client as mqtt
import sys
import json
import uuid
import serial, time, random

serial_ports = {}

mqtt_status = {"connected":False, "messages": []}
MAX_MESSAGES = 1000

devices = []
gateways = []
applications = []

def on_mqtt_connect(client, userdata, flags, rc):
   mqtt_status["connected"] = True

   local_client.subscribe("lorawan/+/init")
   local_client.subscribe("lorawan/+/api_res")
   local_client.subscribe("lorawan/+/close")


api_responses = {}

def on_mqtt_message(client, userdata, msg):
   print(msg.topic,msg.payload)
   global api_responses

   if "/api_res" in msg.topic:
      parts = msg.topic.split("/")

      try:
         gw_uuid = uuid.UUID(parts[2])
         app_eui = parts[1]
         has_app = True
      except:
         gw_uuid = uuid.UUID(parts[1])
         has_app = False

      ip_addr = None
      hw_ver = None
      fw_ver = None

      try:
          p_json = json.loads(msg.payload)
          api_responses[str(p_json["rid"])] = msg.payload

      except:
          print("failed to parse json ********** ", msg.payload)
          p_json = {}

      if "rid" in p_json and p_json["rid"] == "DEVICE_DATA":
         # api_res for system info
         hw_ver = p_json["result"]["hardwareVersion"]
         fw_ver = p_json["result"]["firmware"]
      if "rid" in p_json and p_json["rid"] == "ETH_DATA":
         ip_addr = p_json["result"]["ip"]

      for i, ch_gw in enumerate(gateways):
         if ch_gw[1] == gw_uuid:
            gateway = (ch_gw[0], ch_gw[1], ch_gw[2], ch_gw[3], ch_gw[4], ch_gw[5])
            if ip_addr:
               gateway = (ch_gw[0], ch_gw[1], ch_gw[2], ip_addr, ch_gw[4], ch_gw[5])
            if hw_ver and fw_ver:
               gateway = (ch_gw[0], ch_gw[1], ch_gw[2], ch_gw[3], hw_ver, fw_ver)

            # update gateway with latest init
            gateways[i] = gateway
            break

   if "/moved" in msg.topic:
      mqtt_status['messages'].insert(0, {"topic": msg.topic, "payload": ""})
      return

   if "/close" in msg.topic:
      mqtt_status['messages'].insert(0, {"topic": msg.topic, "payload": ""})
      return

   if "/up" in msg.topic:
      print("handling up message")
      p_json = json.loads(msg.payload)
      if not p_json["deveui"] in devices:
         print("adding device to list")
         devices.append(p_json["deveui"])
      if "data-format" in p_json and p_json["data-format"] == "hexadecimal":
         msg.payload["data"] = b64encode(bytes.fromhex(p_json["data"])).decode()
         msg.payload = json.dumps(p_json)

   if "/init" in msg.topic:
      parts = msg.topic.split("/")

      p_json = json.loads(msg.payload)

      try:
         gw_uuid = uuid.UUID(parts[2])
         app_eui = parts[1]
         has_app = True
      except:
         gw_uuid = uuid.UUID(parts[1])
         has_app = False

      gateway = None

      for gw in p_json["gateways_euis"]:
         found = False
         gateway = (gw, gw_uuid, has_app, None, None, None )
         for i, ch_gw in enumerate(gateways):
            if ch_gw[0] == gw:
               found = True
               # update gateway with latest init
               gateways[i] = gateway
               break
         if not found:
            print("adding gateway_eui to list", gateway)
            gateways.append( gateway )

      if has_app and not app_eui in applications:
         print("adding application to list")
         applications.append(app_eui)

      # Get additional system info
      message_data = {
         "method": "GET",
         "path": "/api/system",
         "body": "",
         "rid": "DEVICE_DATA"
      }

      if not gateway[2]:
         local_client.publish("lorawan/" + str(gw_uuid) +  "/api_req", json.dumps(message_data))
      else:
         local_client.publish("lorawan/" + app_eui + "/" + str(gw_uuid).replace("-", "").upper() +  "/api_req" , json.dumps(message_data))

      message_data = {
         "method": "GET",
         "path": "/api/stats/eth0",
         "body": "",
         "rid": "ETH_DATA"
      }

      if not gateway[2]:
         local_client.publish("lorawan/" + str(gw_uuid) +  "/api_req", json.dumps(message_data))
      else:
         local_client.publish("lorawan/" + app_eui + "/" + str(gw_uuid).replace("-", "").upper() +  "/api_req" , json.dumps(message_data))

   try:
      mqtt_status['messages'].insert(0, {"topic": msg.topic, "payload": json.loads(msg.payload)})
   except:
      pass

   while (len(mqtt_status['messages']) > MAX_MESSAGES):
      mqtt_status['messages'].pop()

def on_mqtt_subscribe(client, userdata, mid, qos):
    pass

def on_mqtt_disconnect(client, userdata, rc):
    mqtt_status["connected"] = False

local_client = mqtt.Client(clean_session=True)

local_client.on_connect = on_mqtt_connect
local_client.on_message = on_mqtt_message
local_client.on_subscribe = on_mqtt_subscribe
local_client.on_disconnect = on_mqtt_disconnect

mqtt_server = "172.16.0.221"

mqtt_port = 1883

local_client.connect(mqtt_server, mqtt_port, 60)

local_client.loop_start()

# DOT_PORT = "/dev/ttyACM2"

# def open_serial_port(portname):
#    global serial_ports

#    serial_ports[portname] = {}
#    serial_ports[portname]["device"] = serial.Serial(
#       port= portname,
#       baudrate= 115200,
#       parity=serial.PARITY_NONE,
#       stopbits=serial.STOPBITS_ONE,
#       bytesize=serial.EIGHTBITS
#    )
#    serial_ports[portname]["response"] = []

# open_serial_port(DOT_PORT)

app = Flask(__name__)

assets = Environment(app)
assets.url = app.static_url_path
scss = Bundle('sass/styles.scss', filters='pyscss', output='all.css')
assets.register('scss_all', scss)

rid = 0

gwuuid = '8ffa106f-c751-cfcd-6300-80918d516837'



# @app.route('/', defaults={'path':''})
@app.route('/<path:path>', methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def index(path):
    print(request)
    print(path)
    print(request.query_string)
    print(json.dumps(request.values))
    #    print(request.json)
    # print(request.args)
    global api_responses
    global rid
    global gwuuid

    rid = rid + 1
    my_rid = str(gwuuid) + str(rid)
    message_data = {
            'method': request.method,
            'path': '/' + path,
            'body': '',
            'rid': my_rid
            }

    if len(request.query_string) != 0:
        message_data['path'] = message_data['path'] + "?" + request.query_string.decode('utf-8')
    try:
        if request.json:
            message_data['body'] = json.dumps(request.json)
    except:
        pass

    local_client.publish("lorawan/" + gwuuid +  "/api_req", json.dumps(message_data))

    while not str(my_rid) in api_responses:
        time.sleep(0.1)

    print("RETURNING API RESPONSE : ", api_responses[str(my_rid)])

    if (api_responses[str(my_rid)]):
        json_data = json.loads(api_responses[str(my_rid)])
        if "code" in json_data and json_data["code"] != 200:
            return Response(api_responses[str(my_rid)], status=json_data["code"], mimetype='application/json')

    return Response(api_responses[str(my_rid)], mimetype='application/json') #json.dumps({"messages":mqtt_status["messages"][-10::-1]})

@app.route('/api/gateways', defaults={'new_gwuuid': None}, methods = ['GET'])
@app.route('/api/gateways/<new_gwuuid>', methods = ['GET'])
def api_gateways(new_gwuuid):
   global gwuuid
   if new_gwuuid != None:
      gwuuid = new_gwuuid
      return '<meta http-equiv="refresh" content="0; url=/" />'
   else:
      gw_list = "<h1>Gateways</h1><ul>"
      for gw in gateways:
         gw_list = gw_list + "<li><a href='/api/gateways/" + str(gw[1]) + "'>" + str(gw[1]) + "</a> - " + str(gw[0]) + " - " + str(gw[3]) + " - " + str(gw[4]) + " - " + str(gw[5]) +"</li>"
      gw_list = gw_list + "</ul>"

#      for gw in gateways:
#           gw_list += "<br/>" + str(gw)
      return gw_list

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)
