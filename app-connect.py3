#!/usr/bin/env python3

# Copyright 2020 Multitech Systems Inc

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import paho.mqtt.client as mqtt
import sys
import json
import ssl
import os
import re
import tempfile
import signal
import time
import http.client
import threading, queue
import logging
import logging.handlers
import socket
import gzip

from http.client import BadStatusLine, ResponseNotReady, CannotSendRequest, CannotSendHeader
from collections import deque


# LoRaWAN Application connecting to 3rd Party Back-end
# AppEUI and AppURL are sent to conduit when a Join Accept message is received from the Lens Join Server
# This application will save the AppEUI/AppURL pairs and use them to post to an HTTPS URL or publish to an MQTTS URL




local_mqtt_sub_up = "lora/+/+/up"
local_mqtt_sub_moved = "lora/+/moved"
local_mqtt_sub_joined = "lora/+/joined"
local_mqtt_down_topic = "lora/%s/down"
local_mqtt_clear_topic = "lora/%s/clear"



app_http_prefix = "/api/v1/"

app_http_init_path = app_http_prefix + "lorawan/%s/%s/init"
app_http_close_path = app_http_prefix + "lorawan/%s/%s/close"
app_http_uplink_path = app_http_prefix + "lorawan/%s/%s/up"
app_http_uplink_app_path = app_http_prefix + "lorawan/%s/up"
app_http_downlink_path = app_http_prefix + "lorawan/%s/down"
app_http_joined_path = app_http_prefix + "lorawan/%s/%s/joined"


app_mqtt_init_topic = "lorawan/%s/%s/init"
app_mqtt_config_topic = "lorawan/%s/%s/config"
app_mqtt_close_topic = "lorawan/%s/%s/close"
app_mqtt_disconnected_topic = "lorawan/%s/%s/disconnected"
app_mqtt_joined_topic = "lorawan/%s/%s/joined"
app_mqtt_uplink_topic = "lorawan/%s/%s/up"
app_mqtt_moved_topic = "lorawan/%s/%s/moved"
app_mqtt_downlink_topic = "lorawan/%s/%s/down"
app_mqtt_clear_topic = "lorawan/%s/%s/clear"



def custom_app_uplink_handler(app, topic, msg):
    # print("Custom app uplink", topic, msg)
    return (topic, msg)



def custom_app_downlink_handler(app, topic, msg):
    # print("Custom app downlink", topic, msg)
    return (topic, msg)



class GZipRotator(object):
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

    if "client_id" in app_net["options"] and app_net["options"]["client_id"] != "":
        client_id = app_net["options"]["client_id"]
    else:
        client_id = "lorawan/" + app_net["eui"] + "/" + gw_uuid

    mqtt_clients[app_net["eui"]] = mqtt.Client(client_id, False, app_net)

    apps[app_net["eui"]]["isMqtt"] = True
    apps[app_net["eui"]]["isHttp"] = False

    if re.match('^mqtts://', app_net["url"]):
        temp = None
        ca_file = None
        reqs = None
        cert_file = None
        key_file = None
        check_hostname = True

        if "options" in app_net:
            if "server_cert" in app_net["options"] and isinstance(app_net["options"]["server_cert"], str):
                if app_net["options"]["server_cert"].strip() != "":
                    ca_file = "/tmp/server-" + app_net["eui"] + ".pem"
                    temp = open(ca_file, "w")
                    temp.write(app_net["options"]["server_cert"])
                    temp.flush()
                    temp.close()
                    reqs=ssl.CERT_REQUIRED
            if "client_cert" in app_net["options"] and isinstance(app_net["options"]["client_cert"], str):
                if app_net["options"]["client_cert"].strip() != "":
                    cert_file = "/tmp/client-" + app_net["eui"] + ".pem"
                    temp = open(cert_file, "w")
                    temp.write(app_net["options"]["client_cert"])
                    temp.flush()
                    temp.close()
            if "apikey" in app_net["options"] and isinstance(app_net["options"]["apikey"], str):
                if app_net["options"]["apikey"].strip() != "":
                    key_file = "/tmp/client-" + app_net["eui"] + ".key"
                    temp = open(key_file, "w")
                    temp.write(app_net["options"]["apikey"])
                    temp.flush()
                    temp.close()
            if "check_hostname" in app_net["options"] and isinstance(app_net["options"]["check_hostname"], bool):
                check_hostname = app_net["options"]["check_hostname"]

        if ca_file is None:
            check_hostname = False
            ca_file = '/var/config/ca-cert-links/ca-certificates.crt'

        mqtt_clients[app_net["eui"]].tls_set(ca_certs=ca_file, certfile=cert_file,
                        keyfile=key_file, cert_reqs=reqs,
                        tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)

        mqtt_clients[app_net["eui"]].tls_insecure_set(not check_hostname)

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
    mqtt_clients[app_net["eui"]].publish(topic, init_msg, 1, True)

def setup_http_app(app_net):
    global request_timeout

    apps[app_net["eui"]]["isMqtt"] = False
    apps[app_net["eui"]]["isHttp"] = True

    parts = app_net["url"].split(":")

    if re.match('^https://', app_net["url"]):
        # http.client.HTTPSConnection(host, port=None, key_file=None, cert_file=None, [timeout, ]source_address=None, *, context=None, check_hostname=None, blocksize=8192)

        temp = None
        ca_file = None
        reqs = None
        cert_file = None
        key_file = None
        check_hostname = True

        if "options" in app_net:
            if "server_cert" in app_net["options"] and isinstance(app_net["options"]["server_cert"], str):
                if app_net["options"]["server_cert"].strip() != "":
                    ca_file = "/tmp/server-" + app_net["eui"] + ".pem"
                    temp = open(ca_file, "w")
                    temp.write(app_net["options"]["server_cert"])
                    temp.flush()
                    temp.close()
                    reqs=ssl.CERT_REQUIRED
            if "client_cert" in app_net["options"] and isinstance(app_net["options"]["client_cert"], str):
                if app_net["options"]["client_cert"].strip() != "":
                    cert_file = "/tmp/client-" + app_net["eui"] + ".pem"
                    temp = open(cert_file, "w")
                    temp.write(app_net["options"]["client_cert"])
                    temp.flush()
                    temp.close()
            if "apikey" in app_net["options"] and isinstance(app_net["options"]["apikey"], str):
                if app_net["options"]["apikey"].strip() != "":
                    key_file = "/tmp/client-" + app_net["eui"] + ".key"
                    temp = open(key_file, "w")
                    temp.write(app_net["options"]["apikey"])
                    temp.flush()
                    temp.close()
            if "check_hostname" in app_net["options"] and isinstance(app_net["options"]["check_hostname"], bool):
                check_hostname = app_net["options"]["check_hostname"]

        if ca_file is None:
            check_hostname = False
            ca_file = '/var/config/ca-cert-links/ca-certificates.crt'

        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca_file)
        context.check_hostname = check_hostname

        if cert_file and key_file:
            context.load_cert_chain(certfile=cert_file, keyfile=key_file)

        # Create a connection to submit HTTP requests
        port = 443
        if len(parts) == 3:
            port = int(parts[2])

        http_clients[app_net["eui"]] = http.client.HTTPSConnection(parts[1][2:], port, context=context, timeout=request_timeout)

    else:
        port = 80
        if len(parts) == 3:
            port = int(parts[2])

        # http.client.HTTPConnection(host, port=None, [timeout, ]source_address=None, blocksize=8192
        http_clients[app_net["eui"]] = http.client.HTTPConnection(parts[1][2:], port, timeout=request_timeout)


    http_uplink_queue[app_net["eui"]] = queue.Queue()
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
    if "url" in app_net and len(app_net["url"]) > 0:
        if re.match('^mqtt(s)?://', app_net["url"]):
            logging.info("Call setup MQTT App")
            setup_mqtt_app(app_net)
        elif re.match('^http(s)?://', app_net["url"]):
            setup_http_app(app_net)
        else:
            apps[app_net["eui"]]["isMqtt"] = False
            apps[app_net["eui"]]["isHttp"] = False
    else:
        apps[app_net["eui"]]["isMqtt"] = False
        apps[app_net["eui"]]["isHttp"] = False



def on_mqtt_app_connect(client, userdata, flags, rc):
    global gateways
    global gw_uuid
    if rc == 0:
        client.connected_flag=True
        client.disconnect_flag=False
        client.will_set(app_mqtt_disconnected_topic % ( userdata["eui"], gw_uuid ), None, 1, retain=False)

        if flags["session present"] == False:
            # resubscribe for downlinks
            query = os.popen('lora-query -x session list json file /tmp/sessions.json')
            file = open('/tmp/sessions.json',mode='r')
            dev_list = json.loads(file.read())
            file.close()
            query.close()

            for dev in dev_list:
                if dev["appeui"] in apps and userdata["eui"] == dev["appeui"]:
                    if apps[dev["appeui"]]["isMqtt"] and dev["appeui"] in mqtt_clients:
                        topic = app_mqtt_downlink_topic % ( dev["appeui"], dev["deveui"] )
                        logging.info("subscribe for downlinks: %s", topic)
                        mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

                        topic = app_mqtt_clear_topic % ( dev["appeui"], dev["deveui"] )
                        logging.info("subscribe for queue clear: %s", topic)
                        mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

                        topic = app_mqtt_downlink_topic % ( gw_uuid, dev["deveui"] )
                        logging.info("subscribe for downlinks: %s", topic)
                        mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

                        topic = app_mqtt_clear_topic % ( gw_uuid, dev["deveui"] )
                        logging.info("subscribe for queue clear: %s", topic)
                        mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

                        for gw in gateways:
                            topic = app_mqtt_downlink_topic % ( gw, dev["deveui"] )
                            logging.info("subscribe for downlinks: %s", topic)
                            mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

                            topic = app_mqtt_clear_topic % ( gw, dev["deveui"] )
                            logging.info("subscribe for queue clear: %s", topic)
                            mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

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
        app_schedule_downlink(apps[appeui], deveui, msg.payload)

    if event == "clear":
        topic = local_mqtt_clear_topic % deveui
        local_client.publish(topic, None, 1, True)

def app_schedule_downlink(app, deveui, msg):

    topic = local_mqtt_down_topic % ( deveui )

    response = custom_app_downlink_handler(app, topic, msg)

    if not response:
        return

    (topic, msg) = response

    local_client.publish(topic, msg, 1, True)



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
        mqtt_clients[str(appeui)].publish(topic, msg, 1, True)
    elif app["isHttp"]:
        if app["eui"] in http_uplink_queue:
            while (http_uplink_queue[app["eui"]].qsize() >= http_threads[app["eui"]]["queue_size"]):
                http_uplink_queue[app["eui"]].get()
                http_uplink_queue[app["eui"]].task_done()
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
                    data = res.read().decode('utf-8')
                    logging.info(data)
                    sent = True
                    break
            except (IOError, KeyboardInterrupt) as e:
                print("Request exception", e)
                http_clients[app["eui"]].close()
            except (BadStatusLine, ResponseNotReady, CannotSendRequest, CannotSendHeader, MemoryError) as e:
                print("Response exception", e)
                http_clients[app["eui"]].close()
            finally:
                retry = retry - 1
                if not sent:
                    time.sleep(5)

        if not sent and retain:
            while (http_uplink_queue[app["eui"]].qsize() >= http_threads[app["eui"]]["queue_size"]):
                http_uplink_queue[app["eui"]].get()
                http_uplink_queue[app["eui"]].task_done()
            http_uplink_queue[app["eui"]].put((path, msg))

    else:
        logging.error("App net not found")
        return


    if data:
        try:
            data_json = json.loads(data)

            if re.match(".*\/up$", path):
                if isinstance(data_json, list):
                    for item in data_json:
                        if "deveui" in item and "data" in item:
                            app_schedule_downlink(app, item["deveui"], json.dumps(item))
                else:
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
    client.subscribe(local_mqtt_sub_up, 1)
    client.subscribe(local_mqtt_sub_joined, 1)
    client.subscribe(local_mqtt_sub_moved, 1)


def on_mqtt_message(client, userdata, msg):
    global apps
    global mqtt_clients
    global gw_uuid

    parts = msg.topic.split('/')
    appeui = ""
    deveui = parts[1]
    event = parts[2]

    if len(parts) > 3:
        appeui = parts[1]
        deveui = parts[2]
        event = parts[3]

    logging.info("Device eui: " + deveui + " App eui: " + appeui + " Event: " + event)

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
            stream.close()
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
            mqtt_clients[appeui].subscribe(str(downlink_topic), 1)

            topic = app_mqtt_clear_topic % ( appeui, deveui )
            logging.info("subscribe for queue clear: %s", topic)
            mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

            topic = app_mqtt_downlink_topic % ( gw_uuid, deveui )
            logging.info("subscribe for downlinks: %s", topic)
            mqtt_clients[appeui].subscribe(str(topic), 1)

            topic = app_mqtt_clear_topic % ( gw_uuid, deveui )
            logging.info("subscribe for queue clear: %s", topic)
            mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

            for gw in gateways:
                topic = app_mqtt_downlink_topic % ( gw, deveui )
                logging.info("subscribe for downlinks: %s", topic)
                mqtt_clients[appeui].subscribe(str(topic), 1)

                topic = app_mqtt_clear_topic % ( gw, deveui )
                logging.info("subscribe for queue clear: %s", topic)
                mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

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

    if event == "moved":
        if appeui in apps:
            if apps[appeui]["isMqtt"]:
                app_publish_msg(apps[appeui], app_mqtt_moved_topic % ( appeui, deveui ), msg.payload)


def http_uplink_thread(appeui):
    logging.info("uplink thread %s started", appeui)

    while http_threads[appeui]["running"]:
        logging.info("uplink thread %s", appeui)

        # if not http_threads[appeui]["ready"]:
        #     time.sleep(5)
        #     continue


        if (http_uplink_queue[appeui].qsize() > 1):
            msg = None
            msgs = []
            cnt = 0
            join_break = False
            while not http_uplink_queue[appeui].empty() and cnt < 10:
                msg = http_uplink_queue[appeui].get()

                if msg is None or (len(msg) != 2 and not (msg[0] or msg[1])):
                    http_uplink_queue[appeui].task_done()
                    break

                if (len(msg[1]) > 700 or re.match(".*\/joined$", msg[0])):
                    join_break = True
                    http_uplink_queue[appeui].task_done()
                    break

                msgs.append(json.loads(msg[1]))
                http_uplink_queue[appeui].task_done()
                cnt = cnt + 1

            if len(msgs) > 0:
                app_publish_http(apps[appeui], app_http_uplink_app_path % (appeui), json.dumps(msgs), True)

            if join_break:
                app_publish_http(apps[appeui], msg[0], msg[1], True)
        else:
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
                        data = res.read().decode("utf-8")
                        logging.info("API Response: " + data)
                        break
                except (IOError, KeyboardInterrupt) as e:
                    print("Exception during request GET", e)
                    http_clients[appeui].close()
                except (BadStatusLine, ResponseNotReady, CannotSendRequest, CannotSendHeader, MemoryError) as e:
                    print("Exception during GET response", e)
                    http_clients[appeui].close()
                finally:
                    retry = retry - 1

        else:
            logging.error("App net not found")
            return

        if data:
            try:
                downlinks = json.loads(data)

                if isinstance(downlinks, list):
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
stream.close()

try:
    default_app = json.loads(output)
except ValueError:
    logging.info("Network Server is not available")
    time.sleep(5)
    exit(1)


stream = os.popen('lora-query -x gateways list json')
output = stream.read()
stream.close()

try:
    gw_list = json.loads(output)
except ValueError:
    exit(1)


for gw in gw_list:
    gateways.append(gw["gweui"])

if "enabled" in default_app and default_app["enabled"]:
    default_app["eui"] = "-".join(re.findall('..',default_app["eui"].replace("-","").lower()))
    apps[default_app["eui"]] = default_app
    setup_app(default_app)


stream = os.popen('lora-query -x appnet list json')
output = stream.read()
app_list = json.loads(output)
stream.close()

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


query = os.popen('lora-query -x session list json file /tmp/sessions.json')
file = open('/tmp/sessions.json',mode='r')
dev_list = json.loads(file.read())
file.close()
query.close()


for dev in dev_list:
    if dev["appeui"] in apps:
        if apps[dev["appeui"]]["isMqtt"] and dev["appeui"] in mqtt_clients:
            topic = app_mqtt_downlink_topic % ( dev["appeui"], dev["deveui"] )
            logging.info("subscribe for downlinks: %s", topic)
            mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)


            topic = app_mqtt_clear_topic % ( dev["appeui"], dev["deveui"] )
            logging.info("subscribe for queue clear: %s", topic)
            mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

            topic = app_mqtt_downlink_topic % ( gw_uuid, dev["deveui"] )
            logging.info("subscribe for downlinks: %s", topic)
            mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)


            topic = app_mqtt_clear_topic % ( gw_uuid, dev["deveui"] )
            logging.info("subscribe for queue clear: %s", topic)
            mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

            for gw in gateways:
                topic = app_mqtt_downlink_topic % ( gw, dev["deveui"] )
                logging.info("subscribe for downlinks: %s", topic)
                mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

                topic = app_mqtt_clear_topic % ( gw, dev["deveui"] )
                logging.info("subscribe for queue clear: %s", topic)
                mqtt_clients[dev["appeui"]].subscribe(str(topic), 1)

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
        stream.close()
        try:
            test_app_list = json.loads(output)
        except ValueError:
            continue

        logging.info("Check for app updates")

        for test_app in test_app_list:
            test_eui = test_app["eui"]
            if not test_eui in apps:
                apps[test_eui] = test_app
                setup_app(test_app)
                continue

            for appeui in apps:
                if appeui == test_eui:
                    if not compare_apps(apps[appeui], test_app):
                        if apps[appeui]["isMqtt"]:
                            mqtt_clients[appeui].publish("lorawan/" + appeui + "/" + gw_uuid + "/close", None, 1, True)
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
        app_publish_msg(apps[default_app["eui"]], app_http_close_path % ( default_app["eui"], gw_uuid ), None)

        time.sleep(5)

        http_threads[default_app["eui"]]["running"] = False
        app_publish_msg(apps[default_app["eui"]], "", None)

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

        app_publish_msg(apps[app["eui"]], app_http_close_path % ( app["eui"], gw_uuid ), None)

        time.sleep(5)

        http_threads[app["eui"]]["running"] = False
        app_publish_msg(apps[app["eui"]], "", None)

        with http_threads[app["eui"]]["downlink_cond"]:
            http_threads[app["eui"]]["downlink_cond"].notify()

        http_threads[app["eui"]]["uplink"].join()
        http_threads[app["eui"]]["downlink"].join()


logging.info("app exit")