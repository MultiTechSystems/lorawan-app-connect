#!/usr/bin/python

import paho.mqtt.client as mqtt
import sys
import json
import ssl
import os
import re
import tempfile
import signal
import time
import httplib
import threading, Queue
import logging
import logging.handlers
import socket
import gzip

from httplib import BadStatusLine, ResponseNotReady
from collections import deque


# LoRaWAN Application connecting to 3rd Party Back-end
# AppEUI and AppURL are sent to conduit when a Join Accept message is received from the Lens Join Server
# This application will save the AppEUI/AppURL pairs and use them to post to an HTTPS URL or publish to an MQTTS URL




local_mqtt_sub_up = "lora/+/+/up"
local_mqtt_sub_joined = "lora/+/joined"
local_mqtt_down_topic = "lora/%s/down"


app_http_prefix = "/api/v1/"

app_http_init_path = app_http_prefix + "lorawan/%s/%s/init"
app_http_close_path = app_http_prefix + "lorawan/%s/%s/close"
app_http_uplink_path = app_http_prefix + "lorawan/%s/%s/up"
app_http_downlink_path = app_http_prefix + "lorawan/%s/down"
app_http_joined_path = app_http_prefix + "lorawan/%s/%s/joined"


app_mqtt_init_topic = "lorawan/%s/%s/init"
app_mqtt_config_topic = "lorawan/%s/%s/config"
app_mqtt_close_topic = "lorawan/%s/%s/close"
app_mqtt_disconnected_topic = "lorawan/%s/%s/disconnected"
app_mqtt_joined_topic = "lorawan/%s/%s/joined"
app_mqtt_uplink_topic = "lorawan/%s/%s/up"
app_mqtt_downlink_topic = "lorawan/%s/%s/down"



def custom_app_uplink_handler(app, topic, msg):
    # print("Custom app uplink", topic, msg)
    return (topic, msg)



def custom_app_downlink_handler(app, topic, msg):
    # print("Custom app downlink", topic, msg)
    return (topic, msg)



class GZipRotator:
    def __call__(self, source, dest):
        os.rename(source, dest)
        f_in = open(dest, 'rb')
        f_out = gzip.open("%s.gz" % dest, 'wb')
        f_out.writelines(f_in)
        f_out.close()
        f_in.close()
        os.remove(dest)


apps = {}
app_message_queue = {}
gateways = []
mqtt_clients = {}
http_clients = {}
http_threads = {}
http_uplink_queue = {}
http_app_devices = {}
http_downlink_queue = {}
request_timeout = 20
queue_size = 10
downlink_query_interval = 30

def on_mqtt_subscribe(client, userdata, mid, qos):
    logging.info("subscribed: %s", json.dumps(userdata))

def on_mqtt_disconnect(client, userdata, rc):
    logging.info("disconnecting reason  "  +str(rc))
    client.connected_flag=False
    client.disconnect_flag=True

def setup_mqtt_app(app_net):
    logging.info("Setup MQTT App")
    global apps
    global mqtt_clients
    global gw_uuid

    parts = app_net["url"].split(":")
    client_id = "lorawan/" + app_net["eui"] + "/" + gw_uuid
    mqtt_clients[app_net["eui"]] = mqtt.Client(client_id, True, app_net)

    apps[app_net["eui"]]["isMqtt"] = True
    apps[app_net["eui"]]["isHttp"] = False

    if re.match('^mqtts://', app_net["url"]):
        temp = None
        ca_file = ""
        reqs = None
        cert_file = None
        key_file = None
        check_hostname = True

        if "options" in app_net:
            if "server_cert" in app_net["options"]:
                ca_file = "/tmp/server-" + app_net["eui"] + ".pem"
                temp = open(ca_file, "w")
                temp.write(app_net["options"]["server_cert"])
                temp.flush()
                temp.close()
                reqs=ssl.CERT_REQUIRED
            if "client_cert" in app_net["options"]:
                cert_file = "/tmp/client-" + app_net["eui"] + ".pem"
                temp = open(cert_file, "w")
                temp.write(app_net["options"]["client_cert"])
                temp.flush()
                temp.close()
            if "apikey" in app_net["options"]:
                key_file = "/tmp/client-" + app_net["eui"] + ".key"
                temp = open(key_file, "w")
                temp.write(app_net["options"]["apikey"])
                temp.flush()
                temp.close()
            if "check_hostname" in app_net["options"]:
                check_hostname=app_net["options"]["check_hostname"]

        mqtt_clients[app_net["eui"]].tls_set(ca_certs=ca_file, certfile=cert_file,
                        keyfile=key_file, cert_reqs=reqs,
                        tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)
        if ca_file != "":
            mqtt_clients[app_net["eui"]].tls_insecure_set(False)

    username = None
    password = None

    if "username" in app_net["options"]:
        username = app_net["options"]["username"]
    if "password" in app_net["options"]:
        password = app_net["options"]["password"]

    if username or password:
        mqtt_clients[app_net["eui"]].username_pw_set(username, password)

    logging.info("MQTT connect %s", app_net["url"])
    mqtt_clients[app_net["eui"]].on_connect = on_mqtt_app_connect
    mqtt_clients[app_net["eui"]].on_message = on_mqtt_app_message
    mqtt_clients[app_net["eui"]].on_subscribe = on_mqtt_subscribe
    mqtt_clients[app_net["eui"]].on_disconnect = on_mqtt_disconnect

    if len(parts) == 2:
        mqtt_clients[app_net["eui"]].connect(parts[1][2:], 1883, 60)
    if len(parts) == 3:
        mqtt_clients[app_net["eui"]].connect(parts[1][2:], int(parts[2]), 60)

    mqtt_clients[app_net["eui"]].loop_start()

    init_msg = json.dumps({'gateways_euis': gateways})
    topic = app_mqtt_init_topic % ( app_net["eui"], gw_uuid )
    mqtt_clients[app_net["eui"]].publish(topic, init_msg)

def setup_http_app(app_net):
    global request_timeout

    apps[app_net["eui"]]["isMqtt"] = False
    apps[app_net["eui"]]["isHttp"] = True

    parts = app_net["url"].split(":")

    if re.match('^https://', app_net["url"]):
        # http.client.HTTPSConnection(host, port=None, key_file=None, cert_file=None, [timeout, ]source_address=None, *, context=None, check_hostname=None, blocksize=8192)

        temp = None
        ca_file = ""
        reqs = None
        cert_file = None
        key_file = None
        check_hostname = True

        if "options" in app_net:
            if "server_cert" in app_net["options"]:
                ca_file = "/tmp/server-" + app_net["eui"] + ".pem"
                temp = open(ca_file, "w")
                temp.write(app_net["options"]["server_cert"])
                temp.flush()
                temp.close()
                reqs=ssl.CERT_REQUIRED
            if "client_cert" in app_net["options"]:
                cert_file = "/tmp/client-" + app_net["eui"] + ".pem"
                temp = open(cert_file, "w")
                temp.write(app_net["options"]["client_cert"])
                temp.flush()
                temp.close()
            if "apikey" in app_net["options"]:
                key_file = "/tmp/client-" + app_net["eui"] + ".key"
                temp = open(key_file, "w")
                temp.write(app_net["options"]["apikey"])
                temp.flush()
                temp.close()
            if "check_hostname" in app_net["options"]:
                check_hostname = app_net["options"]["check_hostname"]

        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca_file)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        context.check_hostname = check_hostname


        # Create a connection to submit HTTP requests
        port = 443
        if len(parts) == 3:
            port = int(parts[2])

        http_clients[app_net["eui"]] = httplib.HTTPSConnection(parts[1][2:], port, context=context, timeout=request_timeout)

    else:
        port = 80
        if len(parts) == 3:
            port = int(parts[2])

        # http.client.HTTPConnection(host, port=None, [timeout, ]source_address=None, blocksize=8192
        http_clients[app_net["eui"]] = httplib.HTTPConnection(parts[1][2:], port, timeout=request_timeout)


    http_uplink_queue[app_net["eui"]] = Queue.Queue()
    http_threads[app_net["eui"]] = {}

    http_threads[app_net["eui"]]["running"] = True
    http_threads[app_net["eui"]]["ready"] = False
    http_threads[app_net["eui"]]["closing"] = False
    http_threads[app_net["eui"]]["queue_size"] = queue_size
    http_threads[app_net["eui"]]["downlink_query_interval"] = downlink_query_interval
    http_threads[app_net["eui"]]["lock"] = threading.Lock()
    http_threads[app_net["eui"]]["downlink_cond"] = threading.Condition()
    http_threads[app_net["eui"]]["uplink"] = threading.Thread(target=http_uplink_thread, args=(app_net["eui"],))
    http_threads[app_net["eui"]]["downlink"] = threading.Thread(target=http_downlink_thread, args=(app_net["eui"],))
    http_threads[app_net["eui"]]["uplink"].start()
    http_threads[app_net["eui"]]["downlink"].start()

    if app_net["eui"] not in http_app_devices:
        http_app_devices[app_net["eui"]] = []

    time.sleep(1)

    init_msg = json.dumps({'gateways_euis': gateways})

    topic = app_http_init_path % ( app_net["eui"], gw_uuid )

    app_publish_msg(app_net, topic, init_msg)


def setup_app(app_net):
    if "url" in app_net:
        if re.match('^mqtt(s)?://', app_net["url"]):
            logging.info("Call setup MQTT App")
            setup_mqtt_app(app_net)
        elif re.match('^http(s)?://', app_net["url"]):
            setup_http_app(app_net)




def on_mqtt_app_connect(client, userdata, flags, rc):
    global gateways
    if rc == 0:
        client.connected_flag=True
        client.disconnect_flag=False
        client.will_set(app_mqtt_disconnected_topic % ( userdata["eui"], gw_uuid ), None, 1, retain=False)

def on_mqtt_app_message(client, userdata, msg):
    global local_client
    parts = msg.topic.split('/')
    appeui = parts[1]
    deveui = parts[2]
    event = parts[3]

    logging.info("Device eui: " + deveui)
    logging.info("App eui: " + appeui)
    logging.info("Event: " + event)

    if event == "down":
        app_schedule_downlink(apps[appeui], deveui, msg)



def app_schedule_downlink(app, deveui, msg):

    topic = local_mqtt_down_topic % ( deveui )

    response = custom_app_downlink_handler(app, topic, msg)

    if not response:
        return

    (topic, msg) = response

    local_client.publish(topic, msg)



def app_publish_msg(app, topic, msg):
    logging.info("Uplink json_data: %s", msg)

    if re.match(".*\/up$", topic):
        response = custom_app_uplink_handler(app, topic, msg)
        if not response:
            return False
        else:
            (topic, msg) = response

    appeui = app["eui"]

    if app["isMqtt"]:
        if mqtt_clients[str(appeui)].connected_flag:
            mqtt_clients[str(appeui)].publish(topic, msg)
        else:
            # TODO:
            logging.info('MQTT Client is not connected')
            logging.info('store and forward not implemented')
    elif app["isHttp"]:
        http_uplink_queue[app["eui"]].put((topic,msg))


    return True


def app_publish_http(app, path, msg, retain=False):
    logging.info("POST to '%s'", path)
    headers = {"Content-type": "application/json", "Accept": "text/plain"}

    data = None

    if app["eui"] in http_clients:
        sent = False
        retry = 3

        while retry and http_threads[app["eui"]]["running"]:
            try:
                with http_threads[app["eui"]]["lock"]:
                    http_clients[app["eui"]].request("POST", path, msg, headers)
                    res = http_clients[app["eui"]].getresponse()
                    logging.info("%d %s", res.status, res.reason)
                    data = res.read()
                    logging.info(data)
                    sent = True
                    break
            except (IOError, KeyboardInterrupt), e:
                print "Request exception", e
                http_clients[app["eui"]].close()
            except (BadStatusLine, ResponseNotReady), e:
                print "Response exception", e
                http_clients[app["eui"]].close()
            finally:
                retry = retry - 1

        if not sent and retain:
            http_uplink_queue[app["eui"]].put((path, msg))


    else:
        logging.error("App net not found")
        return


    if data:
        try:
            data_json = json.loads(data)

            if re.match(".*\/up$", path):
                if "deveui" in data_json and "data" in data_json:
                    app_schedule_downlink(app, data_json["deveui"], data)
            elif re.match(".*\/init$", path):
                if "timeout" in data_json:
                    http_threads[app["eui"]]["request_timeout"] = data_json["timeout"]
                if "downlink_query_interval" in data_json:
                    http_threads[app["eui"]]["downlink_query_interval"] = data_json["downlink_query_interval"]
                if "queue_size" in data_json:
                    http_threads[app["eui"]]["queue_size"] = data_json["queue_size"]

                http_threads[app["eui"]]["ready"] = True
        except ValueError:
            logging.info("failed to parse response as json")


def on_mqtt_connect(client, userdata, flags, rc):
    logging.info("Connected with result code "+str(rc))
    client.subscribe(local_mqtt_sub_up)
    client.subscribe(local_mqtt_sub_joined)

def on_mqtt_message(client, userdata, msg):
    global apps
    global mqtt_clients

    logging.info("LOCAL MESSAGE Topic: " + msg.topic + '\nMessage: ' + str(msg.payload))
    #BT - Extract out the mac address in the topic
    parts = msg.topic.split('/')
    appeui = ""
    deveui = parts[1]
    event = parts[2]

    if len(parts) > 3:
        appeui = parts[1]
        deveui = parts[2]
        event = parts[3]

    logging.info("Device eui: " + deveui)
    logging.info("App eui: " + appeui)
    logging.info("Event: " + event)

    if event == "joined":
        logging.info("Device joined " + deveui)

        try:
            json_data = json.loads(msg.payload.decode("utf-8"))

            logging.info("App eui: " + json_data["appeui"])
            appeui = json_data["appeui"]
            gweui = json_data["gweui"]
        except ValueError:
            logging.info('Decoding JSON has failed')
            return

        if appeui not in apps:
            stream = os.popen('lora-query -x appnet get ' + appeui)
            output = stream.read()
            logging.info(output)
            app_data = json.loads(output)

            if "status" in app_data and app_data["status"] == "fail":
                logging.info("failed to find application")
                return
            else:
                apps[appeui] = app_data
                setup_app(app_data)

        if apps[appeui]["isMqtt"]:
            downlink_topic = app_mqtt_downlink_topic % ( appeui, deveui )

            logging.info("subscribe for downlinks: %s", downlink_topic)
            mqtt_clients[appeui].subscribe(str(downlink_topic), 0)

            joined_topic = app_mqtt_joined_topic % (appeui, deveui)
            app_publish_msg(apps[appeui], joined_topic, msg.payload)
        elif apps[appeui]["isHttp"]:
            topic = app_http_joined_path % ( appeui, deveui )
            app_publish_msg(apps[appeui], topic, msg.payload)
            if not appeui in http_app_devices:
                http_app_devices[appeui] = []

            if deveui not in http_app_devices[appeui]:
                http_app_devices[appeui].append(deveui)

    if event == "up":
        if appeui in apps:
            if apps[appeui]["isMqtt"]:
                app_publish_msg(apps[appeui], app_mqtt_uplink_topic % ( appeui, deveui ), msg.payload)
            elif apps[appeui]["isHttp"]:
                app_publish_msg(apps[appeui], app_http_uplink_path % ( appeui, deveui ), msg.payload)




def http_uplink_thread(appeui):
    logging.info("uplink thread %s started", appeui)

    while http_threads[appeui]["running"]:
        logging.info("uplink thread %s", appeui)

        # if not http_threads[appeui]["ready"]:
        #     time.sleep(5)
        #     continue

        msg = http_uplink_queue[appeui].get()
        app_publish_http(apps[appeui], msg[0], msg[1], True)
        http_uplink_queue[appeui].task_done()


    logging.info("uplink thread %s exited", appeui)
    return



def http_downlink_thread(appeui):
    logging.info("downlink thread %s started", appeui)

    while http_threads[appeui]["running"]:
        logging.info("downlink thread %s", appeui)

        if not appeui in http_app_devices:
            logging.info("Device list for %s not found", appeui)
            with http_threads[appeui]["downlink_cond"]:
                http_threads[appeui]["downlink_cond"].wait(5)
            continue

        if not http_threads[appeui]["ready"]:
            with http_threads[appeui]["downlink_cond"]:
                http_threads[appeui]["downlink_cond"].wait(5)
            continue

        path = app_http_downlink_path % ( appeui )

        deveuis = http_app_devices[appeui]
        logging.info("GET from '%s'", path)
        headers = {"Content-type": "application/json", "Accept": "text/plain"}

        data = None

        if appeui in http_clients:
            sent = False
            retry = 3

            while retry and http_threads[appeui]["running"]:
                try:
                    with http_threads[appeui]["lock"]:
                        http_clients[appeui].request("GET", path, json.dumps(deveuis), headers)
                        res = http_clients[appeui].getresponse()
                        logging.info("%d %s", res.status, res.reason)
                        data = res.read()
                        logging.info(data)
                        break
                except (IOError, KeyboardInterrupt), e:
                    print "Exception during request GET", e
                    http_clients[appeui].close()
                except (BadStatusLine, ResponseNotReady), e:
                    print "Exception during GET response", e
                    http_clients[appeui].close()
                finally:
                    retry = retry - 1

        else:
            logging.error("App net not found")
            return

        if data:
            try:
                downlinks = json.loads(data)

                if len(downlinks) > 0:
                    for downlink in downlinks:
                        if "deveui" in downlink and "data" in downlink:
                            app_schedule_downlink(apps[appeui], downlink["deveui"], json.dumps(downlink))
            except ValueError:
                logging.info("failed to parse response as json")


        with http_threads[appeui]["downlink_cond"]:
            http_threads[appeui]["downlink_cond"].wait(http_threads[appeui]["downlink_query_interval"])


    logging.info("downlink thread %s exited", appeui)
    return




format = "%(asctime)s: %(message)s"
logging.basicConfig(format=format, level=logging.INFO, datefmt="%Y-%m-%dT%H:%M:%S%z")
handler = logging.handlers.SysLogHandler('/dev/log')
handler.ident = "lora-app-connect"

logging.getLogger().addHandler(handler)
# rotate = logging.handlers.RotatingFileHandler('/var/log/lora-app-net.log', 'a', 15*1024, 4)
# rotate.rotator = GZipRotator()
# logging.getLogger().addHandler(rotate)



local_client = mqtt.Client()

local_client.on_connect = on_mqtt_connect
local_client.on_message = on_mqtt_message
local_client.on_subscribe = on_mqtt_subscribe
local_client.on_disconnect = on_mqtt_disconnect

local_client.connect("127.0.0.1", 1883, 60)

stream = os.popen('cat /sys/devices/platform/mts-io/uuid')
gw_uuid = stream.read()
gw_uuid = gw_uuid[:-1]


stream = os.popen('lora-query -x config  | jsparser --jsobj --path defaultApp')
output = stream.read()

try:
    default_app = json.loads(output)
except ValueError:
    logging.info("Network Server is not available")
    time.sleep(5)
    exit(1)


stream = os.popen('lora-query -x gateways list json')
output = stream.read()

try:
    gw_list = json.loads(output)
except ValueError:
    exit(1)


for gw in gw_list:
    gateways.append(gw["gweui"])


if "enabled" in default_app and default_app["enabled"]:
    apps[default_app["eui"]] = default_app
    setup_app(default_app)


stream = os.popen('lora-query -x appnet list json')
output = stream.read()
app_list = json.loads(output)

for app in app_list:
    apps[app["eui"]] = app
    logging.info("Setup App", app)
    setup_app(app)



def compare_apps(app1, app2):
    if "enabled" in app1:
        return True

    if app1["eui"] != app2["eui"]:
        return False
    if app1["app_net_id"] != app2["app_net_id"]:
        return False
    if app1["app_net_uuid"] != app2["app_net_uuid"]:
        return False
    if app1["url"] != app2["url"]:
        return False
    if json.dumps(app1["options"]) != json.dumps(app2["options"]):
        return False

    return True


stream = os.popen('lora-query -x session list json')
output = stream.read()
dev_list = json.loads(output)

for dev in dev_list:
    if dev["appeui"] in apps:
        if apps[dev["appeui"]]["isMqtt"] and dev["appeui"] in mqtt_clients:
            topic = app_mqtt_downlink_topic % ( dev["appeui"], dev["deveui"] )
            logging.info("subscribe for downlinks: %s", topic)
            mqtt_clients[dev["appeui"]].subscribe(str(topic), 0)
        if apps[dev["appeui"]]["isHttp"] and dev["appeui"] in http_clients:
            if dev["appeui"] not in http_app_devices:
                http_app_devices[dev["appeui"]] = []
            if dev["appeui"] not in http_app_devices[dev["appeui"]]:
                http_app_devices[dev["appeui"]].append(dev["deveui"])



logging.info("start client")


local_client.loop_start()


run = True

def handler_stop_signals(signum, frame):
    global run
    run = False

signal.signal(signal.SIGINT, handler_stop_signals)
signal.signal(signal.SIGTERM, handler_stop_signals)

refreshed = time.time()

while run:
    if (time.time() - refreshed > 60):
        refreshed = time.time()

        # refresh the app list in case of changes
        stream = os.popen('lora-query -x appnet list json')
        output = stream.read()
        try:
            test_app_list = json.loads(output)
        except ValueError:
            continue

        logging.info("Check for app updates")

        for test_app in test_app_list:
            if not test_app["eui"] in apps:
                apps[test_app["eui"]] = test_app
                setup_app(test_app)
                continue

            for appeui in apps:
                if appeui == test_app["eui"]:
                    if not compare_apps(apps[appeui], test_app):
                        if apps[appeui]["isMqtt"]:
                            mqtt_clients[appeui].publish("lorawan/" + appeui + "/" + gw_uuid + "/close", None)
                            mqtt_clients[appeui].loop_stop()
                            mqtt_clients.pop(appeui, None)
                            apps[appeui] = test_app
                            setup_app(test_app)
                        elif apps[appeui]["isHttp"]:
                            http_clients.pop(appeui, None)
                            http_threads[appeui]["running"] = False
                            http_threads[appeui]["uplink"].join()
                            http_threads[appeui]["downlink"].join()
                            apps[appeui] = test_app
                            setup_app(test_app)
                    else:
                        logging.info("No update for %s", str(appeui))
    time.sleep(5)
    pass

logging.info("Closing local client")

local_client.loop_stop()

logging.info("Closing app clients")

if default_app["enabled"]:

    if apps[default_app["eui"]]["isMqtt"]:

        app_publish_msg(apps[default_app["eui"]], app_mqtt_close_topic % ( default_app["eui"], gw_uuid ), None)
        time.sleep(2)
        mqtt_clients[default_app["eui"]].loop_stop()

    if apps[default_app["eui"]]["isHttp"]:

        http_threads[default_app["eui"]]["running"] = False
        app_publish_msg(apps[default_app["eui"]], app_http_close_path % ( default_app["eui"], gw_uuid ), None)

        time.sleep(5)

        with http_threads[default_app["eui"]]["downlink_cond"]:
            http_threads[default_app["eui"]]["downlink_cond"].notify()

        http_threads[default_app["eui"]]["uplink"].join()
        http_threads[default_app["eui"]]["downlink"].join()


for app in app_list:
    if app["eui"] in mqtt_clients:
        app_publish_msg(apps[app["eui"]], app_mqtt_close_topic % ( app["eui"], gw_uuid ), None)
        time.sleep(2)
        mqtt_clients[app["eui"]].loop_stop()
    if app["eui"] in http_clients:

        http_threads[app["eui"]]["running"] = False

        app_publish_msg(apps[app["eui"]], app_http_close_path % ( app["eui"], gw_uuid ), None)

        time.sleep(5)

        with http_threads[app["eui"]]["downlink_cond"]:
            http_threads[app["eui"]]["downlink_cond"].notify()

        http_threads[app["eui"]]["uplink"].join()
        http_threads[app["eui"]]["downlink"].join()


logging.info("app exit")