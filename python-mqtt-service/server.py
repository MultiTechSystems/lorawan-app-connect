from flask import Flask, request
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
   local_client.subscribe("lorawan/#")

def on_mqtt_message(client, userdata, msg):
   print(msg.topic,msg.payload)

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
         has_app = True
      except:
         gw_uuid = uuid.UUID(parts[1])
         has_app = False

      for gw in p_json["gateways_euis"]:
         found = False
         for i, ch_gw in enumerate(gateways):
            if ch_gw[0] == gw:
               found = True
               # update gateway with latest init
               gateways[i] = (gw, gw_uuid, has_app )
               break
         if not found:
            print("adding gateway_eui to list", (gw, gw_uuid, has_app ))
            gateways.append( (gw, gw_uuid, has_app ) )

      if has_app and not parts[1] in applications:
         print("adding application to list")
         applications.append(parts[1])

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

mqtt_server = "172.16.0.222"

mqtt_port = 1883

local_client.connect(mqtt_server, mqtt_port, 60)

local_client.loop_start()

DOT_PORT = "/dev/ttyACM2"

def open_serial_port(portname):
   global serial_ports

   serial_ports[portname] = {}
   serial_ports[portname]["device"] = serial.Serial(
      port= portname,
      baudrate= 115200,
      parity=serial.PARITY_NONE,
      stopbits=serial.STOPBITS_ONE,
      bytesize=serial.EIGHTBITS
   )
   serial_ports[portname]["response"] = []

open_serial_port(DOT_PORT)

app = Flask(__name__)

assets = Environment(app)
assets.url = app.static_url_path
scss = Bundle('sass/styles.scss', filters='pyscss', output='all.css')
assets.register('scss_all', scss)

@app.route('/enqueue',methods = ['POST'])
def enqueue():
   if request.method == 'POST':
      data = request.form
      print(data)
      if data["schedule"] == "AppEUI":
         local_client.publish("lorawan/" + data["appeui"] + "/" + data["deveui"] + "/down", '{"data":"' + b64encode(bytes.fromhex(data["payload"])).decode() + '","port":' + data["port"] + "}")
      if data["schedule"] == "GwEUI":
         local_client.publish("lorawan/" + data["gweui"] + "/" + data["deveui"] + "/down", '{"data":"' + b64encode(bytes.fromhex(data["payload"])).decode() + '","port":' + data["port"] + "}")
      if data["schedule"] == "GwUUID":
         local_client.publish("lorawan/" + data["gwuuid"].replace("-", "").upper() + "/" + data["deveui"] + "/down", '{"data":"' + b64encode(bytes.fromhex(data["payload"])).decode() + '","port":' + data["port"] + "}")
      if data["schedule"] == "GwUUID v1.1":
         local_client.publish("lorawan/" + data["gwuuid"] + "/down", '{"deveui": "' + data["deveui"] + '", "data":"' + b64encode(bytes.fromhex(data["payload"])).decode() + '","port":' + data["port"] + "}")
      return "Success<script>setTimeout(function(){ window.location = '/downlink'; }, 3000);</script>"

@app.route('/downlink',)
def downlink():
   print("devices", devices)
   return render_template("downlink.html", devices=devices, gateways=gateways, applications=applications)

@app.route('/status',)
def status():
   print(mqtt_status)
   return render_template("status.html", title="MQTT STATUS", mqtt_status=mqtt_status)

@app.route('/device_list',)
def device_list():
   return render_template("devices.html", title="Devices", devices=devices)

@app.route('/device/<eui>', methods = ['GET', 'POST'])
def device(eui):
   if request.method == 'POST':
      data = json.loads(request.data)
      print(data)

      portname = DOT_PORT
      command = (data["command"]+"\r\n").encode('utf-8')
      serial_ports[portname]["device"].write(command)

      if ("AT+JOIN" in str(command).upper()):
         time.sleep(8)
      else:
         time.sleep(3)

      readBytes = b''
      while serial_ports[portname]["device"].inWaiting() > 0:
         readBytes += serial_ports[portname]["device"].read(1)

      response = readBytes

      return response.decode('utf-8')
   else:
      return render_template("device.html", title="Device " + eui, eui=eui, mqtt_status=mqtt_status)

@app.route('/demo_fluid_level')
def demo_fluid_level():
   return render_template("demo_fluid_level.html", title="Fluid Level Demo", mqtt_status=mqtt_status)

@app.route('/demo_locator')
def demo_locator():
   return render_template("demo_locator.html", title="Locator Demo", mqtt_status=mqtt_status)

@app.route('/demo_faucet')
def demo_faucet():
   return render_template("demo_faucet.html", title="Faucet Demo", mqtt_status=mqtt_status)

@app.route('/demo_custom')
def demo_custom():
   return render_template("demo_custom.html", title="Custom Demo", mqtt_status=mqtt_status)

@app.route('/gateway_list',)
def gateway_list():
   return render_template("gateways.html", title="Gateways", gateways=gateways)

@app.route('/mqtt_commands',)
def mqtt_commands():
   return render_template("mqtt_commands.html", title="MQTT Commands", gateways=gateways, applications=applications)

@app.route('/application_list',)
def application_list():
   return render_template("applications.html", title="Applications", applications=applications)

@app.route('/mtb_data_protocol',)
def mtb_protocol():
   return render_template("mtb_data_protocol.html", title="MTB Data Protocol", mqtt_status=mqtt_status)

@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html', applications=applications, gateways=gateways, devices=devices, mqtt_server=mqtt_server, mqtt_port=mqtt_port)

@app.route('/api/device/<eui>', methods = ['GET', 'POST'])
def api_device(eui):
   if request.method == 'POST':
      pass
   else:
      return json.dumps(devices)

@app.route('/api/gateway/<uuid>', methods = ['GET', 'POST'])
def api_gateway(uuid):
   if request.method == 'POST':
      pass
   else:
      return json.dumps(gateways)

@app.route('/api/application/<eui>', methods = ['GET', 'POST'])
def api_application(eui):
   if request.method == 'POST':
      pass
   else:
      return json.dumps(applications)

@app.route('/api/mqtt_command', methods = ['GET', 'POST'])
def api_mqtt_command():
   if request.method == 'POST':
      data = json.loads(request.data)
      print(data)

      message_data = {}

      if (data["type"] == "lora_req"):
         message_data["command"] = data["command"]
      elif (data["type"] == "api_req"):
         message_data["method"] = data["method"]
         message_data["path"] = data["path"]
         message_data["body"] = data["body"]
      elif (data["type"] == "log_req"):
         message_data["file"] = data["file"]
         message_data["filter"] = data["filter"]
         if ("lines" in data):
            message_data["lines"] = data["lines"]
         else:
            message_data["lines"] = 50

      message_data["rid"] = random.randint(0, 100000);

      gateway = (0,0,1)

      for gw in gateways:
         if gw[1] == uuid.UUID(data["gwuuid"]):
            gateway = gw

      if not gateway[2]:
         local_client.publish("lorawan/" + data["gwuuid"] +  "/" + data["type"], json.dumps(message_data))
      else:
         local_client.publish("lorawan/" + data["appeui"] + "/" + data["gwuuid"].replace("-", "").upper() +  "/" + data["type"], json.dumps(message_data))

      return json.dumps({ "code": 200, "status": "success" })
   else:
      return json.dumps({"messages":mqtt_status["messages"][-10::-1]})


@app.route('/api/mqtt', methods = ['GET', 'POST'])
def api_mqtt():
   if request.method == 'POST':
      global local_client
      global mqtt_server
      global mqtt_port

      try:
         local_client = mqtt.Client(clean_session=True)

         local_client.on_connect = on_mqtt_connect
         local_client.on_message = on_mqtt_message
         local_client.on_subscribe = on_mqtt_subscribe
         local_client.on_disconnect = on_mqtt_disconnect

         data = request.form
         print(data)

         mqtt_server = data["mqtt_server"]
         mqtt_port = data["mqtt_port"]

         local_client.connect(mqtt_server, int(mqtt_port), 60)

         local_client.loop_start()
      except:
         return "Failed<script>setTimeout(function(){ window.location = '/'; }, 2000);</script>"

      return "Success<script>setTimeout(function(){ window.location = '/'; }, 2000);</script>"
   else:
      return json.dumps(mqtt_status)

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)
