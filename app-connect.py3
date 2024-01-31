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
import datetime
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
import uuid
from base64 import b64encode, b64decode

from http.client import (
    BadStatusLine,
    ResponseNotReady,
    CannotSendRequest,
    CannotSendHeader,
)
from collections import deque


# LoRaWAN Application connecting to 3rd Party Back-end
# AppEUI and AppURL are sent to conduit when a Join Accept message is received from the Lens Join Server
# This application will save the AppEUI/AppURL pairs and use them to post to an HTTPS URL or publish to an MQTTS URL

app_version = "1.0.0"

api_v1_0 = "1.0"
api_v1_1 = "1.1"


def custom_app_uplink_handler(app, topic, msg):
    # print("Custom app uplink", topic, msg)
    return (topic, msg)


def custom_app_downlink_handler(app, topic, msg):
    # print("Custom app downlink", topic, msg)
    return (topic, msg)


local_mqtt_sub_up = "lora/+/+/up"
local_mqtt_sub_moved = "lora/+/+/moved"
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


# MQTT v1.0

app_mqtt_init_topic = "lorawan/%s/%s/init"
app_mqtt_config_topic = "lorawan/%s/%s/config"
app_mqtt_close_topic = "lorawan/%s/%s/close"
app_mqtt_disconnected_topic = "lorawan/%s/%s/disconnected"
app_mqtt_joined_topic = "lorawan/%s/%s/joined"
app_mqtt_uplink_topic = "lorawan/%s/%s/up"
app_mqtt_moved_topic = "lorawan/%s/%s/moved"
app_mqtt_downlink_topic = "lorawan/%s/%s/down"
app_mqtt_clear_topic = "lorawan/%s/%s/clear"

# topics expected from server: down, clear, api_req, lora_req, log_req
# downlink - azure direct method for publishing downlinks to the gateway
# This application will subscribe to the following topics using appeui, gweui, gwuuid and deveui. Appeuis can be managed per device
# using Local Device Credentials
# The following combinations can be used to address the application from the broker to manage downlinks:
#  lorawan/<APP-EUI>/<DEV-EUI>/down
#  lorawan/<GW-EUI>/<DEV-EUI>/down
#  lorawan/<GW-UUID>/<DEV-EUI>/down
#  lorawan/<APP-EUI>/<DEV-EUI>/clear
#  lorawan/<GW-EUI>/<DEV-EUI>/clear
#  lorawan/<GW-UUID>/<DEV-EUI>/clear

app_mqtt_subscribe_down_topic = "lorawan/%s/%s/down"
app_mqtt_subscribe_clear_topic = "lorawan/%s/%s/clear"

# This application will subscribe to the following topics using appeui and gwuuid
# The Default App configured appeui will be used for these topics
# The following topcis can be used to request info from the system:
#  lorawan/<APP-EUI>/<GW-UUID>/api_req
#  lorawan/<APP-EUI>/<GW-UUID>/lora_req
#  lorawan/<APP-EUI>/<GW-UUID>/log_req

app_mqtt_api_request_topic = "lorawan/%s/%s/api_req"
app_mqtt_lora_request_topic = "lorawan/%s/%s/lora_req"
app_mqtt_log_request_topic = "lorawan/%s/%s/log_req"

# The following topcis will be used to publish info from the system:
#  lorawan/<APP-EUI>/<GW-UUID>/api_res
#  lorawan/<APP-EUI>/<GW-UUID>/lora_res
#  lorawan/<APP-EUI>/<GW-UUID>/log_res

app_mqtt_lora_result_topic = "lorawan/%s/%s/lora_res"
app_mqtt_api_result_topic = "lorawan/%s/%s/api_res"
app_mqtt_log_result_topic = "lorawan/%s/%s/log_res"


topic_list = [app_mqtt_subscribe_down_topic, app_mqtt_subscribe_clear_topic]
api_topic_list = []

# If this appeui is configured all devices will forward data to the broker regardless of joineui/appeui settings
appeui_all_devices = "ff-ff-ff-ff-ff-ff-ff-ff"


app_default_v1_0_mqtt_uplink_topic = "lorawan/%(appeui)s/%(deveui)s/up"
app_default_v1_0_mqtt_downlink_topic = "lorawan/%(appeui)s/%(deveui)s/down"


# MQTT v1.1
# Consistent topics could use only the GW-UUID for topics, add an option to use GW-UUID only topics

app_mqtt_v1_1_init_topic = "lorawan/%s/init"
app_mqtt_v1_1_config_topic = "lorawan/%s/config"
app_mqtt_v1_1_close_topic = "lorawan/%s/close"
app_mqtt_v1_1_disconnected_topic = "lorawan/%s/disconnected"
app_mqtt_v1_1_downlink_topic = "lorawan/%s/down"

app_mqtt_v1_1_joined_topic = "lorawan/%s/%s/%s/joined"
app_mqtt_v1_1_uplink_topic = "lorawan/%s/%s/%s/up"
app_mqtt_v1_1_moved_topic = "lorawan/%s/%s/%s/moved"
app_mqtt_v1_1_subscribe_clear_topic = "lorawan/%s/%s/%s/clear"

# The following combinations can be used to address the application from the broker to manage downlinks:
#  lorawan/<GW-UUID>/down
#  lorawan/<GW-UUID>/clear

app_mqtt_v1_1_subscribe_down_topic = "lorawan/%s/down"

# This application will subscribe to the following topics using appeui and gwuuid
# The Default App configured appeui will be used for these topics
# The following topcis can be used to request info from the system:
#  lorawan/<GW-UUID>/api_req
#  lorawan/<GW-UUID>/lora_req
#  lorawan/<GW-UUID>/log_req

app_mqtt_v1_1_api_request_topic = "lorawan/%s/api_req"
app_mqtt_v1_1_lora_request_topic = "lorawan/%s/lora_req"
app_mqtt_v1_1_log_request_topic = "lorawan/%s/log_req"

# The following topcis will be used to publish info from the system:
#  lorawan/<GW-UUID>/api_res
#  lorawan/<GW-UUID>/lora_res
#  lorawan/<GW-UUID>/log_res

app_mqtt_v1_1_lora_result_topic = "lorawan/%s/lora_res"
app_mqtt_v1_1_api_result_topic = "lorawan/%s/api_res"
app_mqtt_v1_1_log_result_topic = "lorawan/%s/log_res"


topic_v1_1_list = [
    app_mqtt_v1_1_subscribe_down_topic,
    app_mqtt_v1_1_subscribe_clear_topic,
]

app_default_v1_1_mqtt_uplink_topic = "lorawan/%(gwuuid)s/%(appeui)s/%(deveui)s/up"
app_default_v1_1_mqtt_downlink_topic = "lorawan/%(gwuuid)s/down"


app_default_mqtt_uplink_topic = app_default_v1_0_mqtt_downlink_topic
app_default_mqtt_downlink_topic = app_default_v1_0_mqtt_downlink_topic


class GZipRotator(object):
    def __call__(self, source, dest):
        os.rename(source, dest)
        f_in = open(dest, "rb")
        f_out = gzip.open("%s.gz" % dest, "wb")
        f_out.writelines(f_in)
        f_out.close()
        f_in.close()
        os.remove(dest)


apps = {}
app_message_queue = {}
gateways = []
devices = {}
mqtt_clients = {}
mqtt_client_locks = {}
http_clients = {}
http_threads = {}
http_uplink_queue = {}
http_app_devices = {}
http_downlink_queue = {}
request_timeout = 20
queue_size = 10
downlink_query_interval = 30


def on_mqtt_subscribe(client, userdata, mid, qos):
    logging.debug("Subscribed: mid: %d data: %s", mid, json.dumps(userdata))


def on_mqtt_disconnect(client, userdata, rc):
    logging.info("MQTT Disconnect reason " + str(rc))
    client.connected_flag = False
    client.disconnect_flag = True
    if userdata and "eui" in userdata and userdata["eui"] in apps:
        logging.info("MQTT Disconnect eui " + userdata["eui"])
        apps[userdata["eui"]]["disconnected_flag"] = True


def setup_mqtt_app(app_net):
    global apps
    global mqtt_clients
    global gw_uuid

    parts = app_net["url"].split(":")

    if "client_id" in app_net["options"] and app_net["options"]["client_id"] != "":
        client_id = app_net["options"]["client_id"]
    else:
        client_id = "lorawan/" + app_net["eui"] + "/" + gw_uuid

    clean_session = False

    if "clean_session" in app_net["options"]:
        clean_session = app_net["options"]["clean_session"]

    mqtt_clients[app_net["eui"]] = mqtt.Client(client_id, clean_session, app_net)

    apps[app_net["eui"]]["isMqtt"] = True
    apps[app_net["eui"]]["isHttp"] = False

    if re.match("^mqtts://", app_net["url"]):
        temp = None
        ca_file = None
        reqs = None
        cert_file = None
        key_file = None
        check_hostname = True

        if "options" in app_net:
            if "server_cert" in app_net["options"] and isinstance(
                app_net["options"]["server_cert"], str
            ):
                if app_net["options"]["server_cert"].strip() != "":
                    ca_file = "/tmp/server-" + app_net["eui"] + ".pem"
                    temp = open(ca_file, "w")
                    temp.write(app_net["options"]["server_cert"])
                    temp.flush()
                    temp.close()
                    reqs = ssl.CERT_REQUIRED
            if "client_cert" in app_net["options"] and isinstance(
                app_net["options"]["client_cert"], str
            ):
                if app_net["options"]["client_cert"].strip() != "":
                    cert_file = "/tmp/client-" + app_net["eui"] + ".pem"
                    temp = open(cert_file, "w")
                    temp.write(app_net["options"]["client_cert"])
                    temp.flush()
                    temp.close()
            if "apikey" in app_net["options"] and isinstance(
                app_net["options"]["apikey"], str
            ):
                if app_net["options"]["apikey"].strip() != "":
                    key_file = "/tmp/client-" + app_net["eui"] + ".key"
                    temp = open(key_file, "w")
                    temp.write(app_net["options"]["apikey"])
                    temp.flush()
                    temp.close()
            if "check_hostname" in app_net["options"] and isinstance(
                app_net["options"]["check_hostname"], bool
            ):
                check_hostname = app_net["options"]["check_hostname"]

        if ca_file is None:
            check_hostname = False
            ca_file = "/var/config/ca-cert-links/ca-certificates.crt"

        try:
            mqtt_clients[app_net["eui"]].tls_set(
                ca_certs=ca_file,
                certfile=cert_file,
                keyfile=key_file,
                cert_reqs=reqs,
                tls_version=ssl.PROTOCOL_TLSv1_2,
                ciphers=None,
            )

            mqtt_clients[app_net["eui"]].tls_insecure_set(not check_hostname)
        except Exception as e:
            logging.error("Error during App %s connection setup", app_net["eui"])
            logging.exception("Error during MQTT connection setup", exc_info=e)
            raise e

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
    mqtt_client_locks[app_net["eui"]] = threading.Lock()
    app_message_queue[app_net["eui"]] = []

    try:
        if len(parts) == 2:
            mqtt_clients[app_net["eui"]].connect(parts[1][2:], 1883, 60)
        if len(parts) == 3:
            mqtt_clients[app_net["eui"]].connect(parts[1][2:], int(parts[2]), 60)

        mqtt_clients[app_net["eui"]].loop_start()

        if (
            not "cloudService" in app_net["options"]
            or app_net["options"]["cloudService"] != "AZURE"
        ):
            init_msg = json.dumps(
                {
                    "gateways_euis": gateways,
                    "time": datetime.datetime.now().isoformat() + "Z",
                    "api_version": default_app["apiVersion"],
                    "app_version": app_version,
                }
            )

            if default_app["apiVersion"] == api_v1_1:
                topic = app_mqtt_v1_1_init_topic % (gw_uuid)
            else:
                topic = app_mqtt_init_topic % (app_net["eui"], gw_uuid)

            with mqtt_client_locks[app_net["eui"]]:
                mqtt_clients[app_net["eui"]].publish(topic, init_msg, 1, True)
    except Exception as e:
        logging.exception("MQTT connect exception", exc_info=e)
        raise e


def setup_http_app(app_net):
    global request_timeout

    apps[app_net["eui"]]["isMqtt"] = False
    apps[app_net["eui"]]["isHttp"] = True

    parts = app_net["url"].split(":")

    if re.match("^https://", app_net["url"]):
        # http.client.HTTPSConnection(host, port=None, key_file=None, cert_file=None, [timeout, ]source_address=None, *, context=None, check_hostname=None, blocksize=8192)

        temp = None
        ca_file = None
        reqs = None
        cert_file = None
        key_file = None
        check_hostname = True

        if "options" in app_net:
            if "server_cert" in app_net["options"] and isinstance(
                app_net["options"]["server_cert"], str
            ):
                if app_net["options"]["server_cert"].strip() != "":
                    ca_file = "/tmp/server-" + app_net["eui"] + ".pem"
                    temp = open(ca_file, "w")
                    temp.write(app_net["options"]["server_cert"])
                    temp.flush()
                    temp.close()
                    reqs = ssl.CERT_REQUIRED
            if "client_cert" in app_net["options"] and isinstance(
                app_net["options"]["client_cert"], str
            ):
                if app_net["options"]["client_cert"].strip() != "":
                    cert_file = "/tmp/client-" + app_net["eui"] + ".pem"
                    temp = open(cert_file, "w")
                    temp.write(app_net["options"]["client_cert"])
                    temp.flush()
                    temp.close()
            if "apikey" in app_net["options"] and isinstance(
                app_net["options"]["apikey"], str
            ):
                if app_net["options"]["apikey"].strip() != "":
                    key_file = "/tmp/client-" + app_net["eui"] + ".key"
                    temp = open(key_file, "w")
                    temp.write(app_net["options"]["apikey"])
                    temp.flush()
                    temp.close()
            if "check_hostname" in app_net["options"] and isinstance(
                app_net["options"]["check_hostname"], bool
            ):
                check_hostname = app_net["options"]["check_hostname"]

        if ca_file is None:
            check_hostname = False
            ca_file = "/var/config/ca-cert-links/ca-certificates.crt"

        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca_file)
        context.check_hostname = check_hostname

        if cert_file and key_file:
            context.load_cert_chain(certfile=cert_file, keyfile=key_file)

        # Create a connection to submit HTTP requests
        port = 443
        if len(parts) == 3:
            port = int(parts[2])

        http_clients[app_net["eui"]] = http.client.HTTPSConnection(
            parts[1][2:], port, context=context, timeout=request_timeout
        )

    else:
        port = 80
        if len(parts) == 3:
            port = int(parts[2])

        # http.client.HTTPConnection(host, port=None, [timeout, ]source_address=None, blocksize=8192
        http_clients[app_net["eui"]] = http.client.HTTPConnection(
            parts[1][2:], port, timeout=request_timeout
        )

    http_uplink_queue[app_net["eui"]] = queue.Queue()
    http_threads[app_net["eui"]] = {}

    http_threads[app_net["eui"]]["running"] = True
    http_threads[app_net["eui"]]["ready"] = False
    http_threads[app_net["eui"]]["closing"] = False
    http_threads[app_net["eui"]]["queue_size"] = queue_size
    http_threads[app_net["eui"]]["downlink_query_interval"] = downlink_query_interval
    http_threads[app_net["eui"]]["lock"] = threading.Lock()
    http_threads[app_net["eui"]]["downlink_cond"] = threading.Condition()
    http_threads[app_net["eui"]]["uplink"] = threading.Thread(
        target=http_uplink_thread, args=(app_net["eui"],)
    )
    http_threads[app_net["eui"]]["downlink"] = threading.Thread(
        target=http_downlink_thread, args=(app_net["eui"],)
    )
    http_threads[app_net["eui"]]["uplink"].start()
    http_threads[app_net["eui"]]["downlink"].start()

    if app_net["eui"] not in http_app_devices:
        http_app_devices[app_net["eui"]] = []

    time.sleep(1)

    init_msg = json.dumps({"gateways_euis": gateways})

    topic = app_http_init_path % (app_net["eui"], gw_uuid)

    app_publish_msg(app_net, topic, init_msg)


def setup_app(app_net):
    try:
        if "url" in app_net and len(app_net["url"]) > 0:
            if re.match("^mqtt(s)?://", app_net["url"]):
                logging.info("Call setup MQTT App")
                setup_mqtt_app(app_net)
            elif re.match("^http(s)?://", app_net["url"]):
                setup_http_app(app_net)
            else:
                apps[app_net["eui"]]["isMqtt"] = False
                apps[app_net["eui"]]["isHttp"] = False
        else:
            apps[app_net["eui"]]["isMqtt"] = False
            apps[app_net["eui"]]["isHttp"] = False
    except (IOError, KeyboardInterrupt) as e:
        logging.exception("Error during App Setup", exc_info=e)
        raise e


def mqtt_subscribe_to_app_topics_azure(appeui):
    topic = apps[appeui]["options"]["downlinkTopic"] % apps[appeui]["options"]
    # https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-direct-methods
    # https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-direct-methods#method-invocation-1
    # wildcard topic OK for direct-methods
    logging.debug("subscribe for app messages: %s", topic)
    mqtt_clients[appeui].subscribe(str(topic), 1)
    mqtt_clients[appeui].subscribe("$iothub/methods/POST/#", 1)


def mqtt_subscribe_to_app_topics_v1_0(appeui):
    if appeui == default_app["eui"]:
        for _topic in api_topic_list:
            topic = _topic % (appeui, gw_uuid)
            logging.debug("subscribe for app messages: %s", topic)
            mqtt_clients[appeui].subscribe(str(topic), 1)

    for dev in dev_list:
        if dev["appeui"] in apps and appeui == dev["appeui"]:
            if apps[appeui]["isMqtt"] and appeui in mqtt_clients:
                dev["gwuuid"] = gw_uuid
                dev["gwserial"] = gw_serial

                if default_app["options"]["overrideTopicsForAllApps"]:
                    topic = default_app["options"]["downlinkTopic"] % dev
                    logging.debug("subscribe for app messages: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)
                elif "downlinkTopic" in apps[appeui]["options"]:
                    topic = apps[appeui]["options"]["downlinkTopic"] % dev
                    logging.debug("subscribe for app messages: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)

                # subscribe to topic_list using appeui, deveui, gw_uuid
                for _topic in topic_list:
                    topic = _topic % (appeui, dev["deveui"])
                    logging.debug("subscribe for app messages: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)

                    topic = _topic % (gw_uuid, dev["deveui"])
                    logging.debug("subscribe for app messages: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)

                    topic = _topic % (appeui, gw_uuid)
                    logging.debug("subscribe for app messages: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)

                # subscribe to gateway/deveui specific topics
                for gw in gateways:
                    topic = app_mqtt_downlink_topic % (gw, dev["deveui"])
                    logging.debug("subscribe for downlinks: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)

                    topic = app_mqtt_clear_topic % (gw, dev["deveui"])
                    logging.debug("subscribe for queue clear: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)


def mqtt_subscribe_to_app_topics_v1_1(appeui):
    for _topic in api_topic_list:
        topic = _topic % (gw_uuid)
        logging.debug("subscribe for app messages: %s", topic)
        mqtt_clients[appeui].subscribe(str(topic), 1)

    topic = app_mqtt_v1_1_downlink_topic % (gw_uuid)
    logging.debug("subscribe for app messages: %s", topic)
    mqtt_clients[appeui].subscribe(str(topic), 1)


def mqtt_subscribe_to_custom_topics_v1_1(appeui):
    for dev in dev_list:
        if dev["appeui"] in apps and appeui == dev["appeui"]:
            if apps[appeui]["isMqtt"] and appeui in mqtt_clients:
                dev["gwuuid"] = gw_uuid
                dev["gwserial"] = gw_serial

                if default_app["options"]["overrideTopicsForAllApps"]:
                    topic = default_app["options"]["downlinkTopic"] % dev
                    logging.debug("subscribe for app messages: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)
                elif "downlinkTopic" in apps[appeui]["options"]:
                    topic = apps[appeui]["options"]["downlinkTopic"] % dev
                    logging.debug("subscribe for app messages: %s", topic)
                    mqtt_clients[appeui].subscribe(str(topic), 1)


def mqtt_subscribe_to_app_topics(appeui):
    if (
        "cloudService" in apps[appeui]["options"]
        and apps[appeui]["options"]["cloudService"] == "AZURE"
    ):
        mqtt_subscribe_to_app_topics_azure(appeui)
    elif default_app["apiVersion"] == api_v1_1:
        mqtt_subscribe_to_app_topics_v1_1(appeui)
    else:
        mqtt_subscribe_to_app_topics_v1_0(appeui)


def on_mqtt_app_connect(client, userdata, flags, rc):
    global gateways
    global gw_uuid

    logging.debug("MQTT app connect %s", userdata["eui"])

    if rc == 0:
        client.connected_flag = True
        client.disconnect_flag = False

        if userdata["eui"] in apps:
            appeui = userdata["eui"]
            with mqtt_client_locks[appeui]:
                if appeui in app_message_queue:
                    while len(app_message_queue[appeui]) > 0:
                        m = app_message_queue[appeui].pop()
                        mqtt_clients[str(appeui)].publish(m[0], m[1], 1, True)

            apps[userdata["eui"]]["disconnected_flag"] = False
        else:
            logging.debug("unknown application: %s", userdata["eui"])
            return

        if (
            not "cloudService" in apps[userdata["eui"]]["options"]
            or apps[userdata["eui"]]["options"]["cloudService"] != "AZURE"
        ):
            if default_app["apiVersion"] == api_v1_1:
                client.will_set(
                    app_mqtt_v1_1_disconnected_topic % (gw_uuid), None, 1, retain=False
                )
            else:
                client.will_set(
                    app_mqtt_disconnected_topic % (userdata["eui"], gw_uuid),
                    None,
                    1,
                    retain=False,
                )

        if lora_query_available:
            # resubscribe for downlinks
            query = os.popen("lora-query -x session list json file /tmp/sessions.json")
            query.read()
            file = open("/tmp/sessions.json", mode="r")
            dev_list = json.loads(file.read())
            file.close()
            query.close()

        mqtt_subscribe_to_app_topics(userdata["eui"])


def on_mqtt_app_message(client, userdata, msg):
    global local_client
    global gw_uuid
    global gateways
    topic_gwuuid = ""
    deveui = ""
    appeui = appeui_all_devices

    parts = msg.topic.split("/")

    if len(parts) == 3:
        topic_gwuuid = parts[1]
        event = parts[2]
    else:
        appeui = parts[1]
        deveui = parts[2]
        if deveui == gw_uuid:
            topic_gwuuid = gw_uuid
        event = parts[3]

    json_data = json.loads(msg.payload)

    if "deveui" in json_data:
        deveui = json_data["deveui"]

    if not appeui in apps and "appeui" in json_data:
        appeui = json_data["appeui"]

    if (
        default_app["options"]["cloudService"] == "AZURE"
        and "$iothub/methods" in msg.topic
    ):
        logging.debug("Direct Method from AZURE")
        # get event from topic, direct methods: lora_req, api_req, log_req, downlink
        # $iothub/methods/POST/#
        # example received topic: $iothub/methods/POST/api_req/?rid=1
        # response sent to: $iothub/methods/res/0/?rid=1

        appeui = default_app["eui"]
        deveui = gw_uuid
        json_data["topic"] = msg.topic
        if "?" in msg.topic and "=" in msg.topic.split("?")[1]:
            json_data["rid"] = msg.topic.split("?")[1].split("=")[1]
        msg.payload = json.dumps(json_data)

    logging.debug("Device eui: " + deveui)
    logging.debug("App eui: " + appeui)
    logging.debug("Event: " + event)

    if userdata["eui"] == default_app["eui"] and (
        event == "api_req"
        or event == "lora_req"
        or event == "log_req"
        or event == "downlink"
    ):
        if event == "downlink" and "deveui" in json_data:
            new_json_data = {"rid": json_data["rid"]}
            new_json_data["command"] = "packet queue add " + json.dumps(msg.payload)
            app_lora_query_request(apps[appeui], json.dumps(new_json_data))
        # Only the default_app server is allowed to make system requests for this gateway
        elif topic_gwuuid == gw_uuid:
            if (
                "requestOptions" in default_app
                and default_app["requestOptions"]["api"]
                and event == "api_req"
            ):
                # perform api request
                app_api_request(apps[appeui], msg.payload)

            if (
                "requestOptions" in default_app
                and default_app["requestOptions"]["lora"]
                and event == "lora_req"
            ):
                # perform lora request
                app_lora_query_request(apps[appeui], msg.payload)

            if (
                "requestOptions" in default_app
                and default_app["requestOptions"]["log"]
                and event == "log_req"
            ):
                # perform log request
                app_log_query_request(apps[appeui], msg.payload)

            return

    if event == "down":
        # if appeui == gw_uuid use the default app
        if appeui == gw_uuid:
            appeui = default_app["eui"]

        # if appeui == gweui use the default app
        for gweui in gateways:
            if appeui == gweui:
                appeui = default_app["eui"]

        app_schedule_downlink(apps[appeui], deveui, msg.payload)

    if (
        default_app["options"]["overrideTopicsForAllApps"]
        and default_app["options"]["downlinkTopic"] != app_default_mqtt_downlink_topic
    ):
        # the appeui and deveui are not guaranteed to be in the topic, deveui must be in the payload
        appeui = default_app["eui"]
        deveui = json.loads(msg.payload)["deveui"]

        topic = default_app["options"]["downlinkTopic"] % {
            "appeui": appeui,
            "deveui": deveui,
            "client_id": default_app["options"]["client_id"],
        }

        # handle a possible wild cards
        topic = topic.split("#")[0]
        if topic in msg.topic:
            topic_match = True

        if "+" in topic:
            for part in topic.split("+"):
                if part not in msg.topic:
                    topic_match = False
                    break
                else:
                    topic_match = True

        if topic_match:
            app_schedule_downlink(apps[appeui], deveui, msg.payload)
            return

    if (
        "cloudService" in apps[appeui]["options"]
        and apps[appeui]["options"]["cloudService"] == "AZURE"
    ):
        # the deveui are not guaranteed to be in the topic, deveui must be in the payload
        deveui = json.loads(msg.payload)["deveui"]
        topic = apps[appeui]["options"]["downlinkTopic"] % {
            "appeui": appeui,
            "deveui": deveui,
            "client_id": apps[appeui]["options"]["client_id"],
        }

        # handle a possible wild cards
        topic = topic.split("#")[0]
        if topic in msg.topic:
            topic_match = True

        if "+" in topic:
            for part in topic.split("+"):
                if part not in msg.topic:
                    topic_match = False
                    break
                else:
                    topic_match = True

        if topic_match:
            app_schedule_downlink(apps[appeui], deveui, msg.payload)

    if event == "clear":
        topic = local_mqtt_clear_topic % deveui
        with mqtt_client_locks["localhost"]:
            local_client.publish(topic, None, 1, True)


def app_log_query_request(app, msg):
    json_obj = json.loads(msg)
    use_filter = False

    if "filter" in json_obj and not "'" in json_obj["filter"]:
        use_filter = True

    if not ";" in json_obj["file"] and not ".." in json_obj["file"]:
        command = "tail -n " + str(json_obj["lines"]) + " " + json_obj["file"]
        if use_filter:
            command = command + " | grep -Ei '" + json_obj["filter"] + "'"
        stream = os.popen(command)
        output = stream.read()
        stream.close()
    else:
        output = "command rejected, no semi-colons or '..' allowed"

    if "rid" in json_obj:
        data = json.dumps({"result": output, "rid": json_obj["rid"]})
    else:
        data = json.dumps({"result": output})
    if "cloudService" in app["options"] and app["options"]["cloudService"] == "AZURE":
        # app_publish_msg(app, default_app["options"]["uplinkTopic"], data)
        app_publish_msg(app, "$iothub/methods/res/0/?$rid=" + json_obj["rid"], data)
    else:
        if default_app["apiVersion"] == api_v1_1:
            app_publish_msg(app, app_mqtt_v1_1_log_result_topic % (gw_uuid), data)
        else:
            app_publish_msg(
                app, app_mqtt_log_result_topic % (app["eui"], gw_uuid), data
            )


def app_lora_query_request(app, msg):
    json_obj = json.loads(msg)

    if not ";" in json_obj["command"]:
        stream = os.popen("lora-query -x " + json_obj["command"])
        output = stream.read()
        stream.close()
    else:
        output = "command rejected, no semi-colons allowed"

    try:
        # try to parse as json
        json_data = json.loads(output)
        data = json.dumps({"result": json_data})
    except:
        data = json.dumps({"result": output})

    if "cloudService" in app["options"] and app["options"]["cloudService"] == "AZURE":
        # app_publish_msg(app, default_app["options"]["uplinkTopic"], data)
        app_publish_msg(app, "$iothub/methods/res/0/?$rid=" + json_obj["rid"], data)
    else:
        if "rid" in json_obj:
            json_data = json.loads(data)
            json_data["rid"] = json_obj["rid"]
            data = json.dumps(json_data)

        if default_app["apiVersion"] == api_v1_1:
            app_publish_msg(app, app_mqtt_v1_1_lora_result_topic % (gw_uuid), data)
        else:
            app_publish_msg(
                app, app_mqtt_lora_result_topic % (app["eui"], gw_uuid), data
            )


def app_api_request(app, msg):
    local_http_client = http.client.HTTPConnection("127.0.0.1", 80, timeout=20)

    json_obj = json.loads(msg)
    method = json_obj["method"]
    path = json_obj["path"]
    body = json_obj["body"]
    headers = {"Content-type": "application/json", "Accept": "text/plain"}

    # try twice incase of connection error
    attempt = 0
    while attempt < 2:
        try:
            local_http_client.request(method, path, body, headers)
            res = local_http_client.getresponse()
            data = res.read().decode("utf-8")
            # successful
            attempt = 1
        except (IOError, KeyboardInterrupt) as e:
            logging.exception("API Request exception", exc_info=e)
            local_http_client.close()
        except (
            BadStatusLine,
            ResponseNotReady,
            CannotSendRequest,
            CannotSendHeader,
            MemoryError,
        ) as e:
            logging.exception("API Request exception", exc_info=e)
            local_http_client.close()

        attempt = attempt + 1

    if attempt > 2:
        print(data, attempt)
        data = json.dumps({"code": 500, "error": "request failed", "status": "fail"})

    if "cloudService" in app["options"] and app["options"]["cloudService"] == "AZURE":
        # app_publish_msg(app, default_app["options"]["uplinkTopic"], data)
        app_publish_msg(app, "$iothub/methods/res/0/?$rid=" + json_obj["rid"], data)
    else:
        if "rid" in json_obj:
            try:
                json_data = json.loads(data)
                json_data["rid"] = json_obj["rid"]
                data = json.dumps(json_data)
            except:
                data = json.dumps(
                    {
                        "code": 500,
                        "error": "request failed",
                        "status": "fail",
                        "rid": json_obj["rid"],
                    }
                )

        if default_app["apiVersion"] == api_v1_1:
            app_publish_msg(app, app_mqtt_v1_1_api_result_topic % (gw_uuid), data)
        else:
            app_publish_msg(
                app, app_mqtt_api_result_topic % (app["eui"], gw_uuid), data
            )


def app_schedule_downlink(app, deveui, msg):
    topic = local_mqtt_down_topic % (deveui)

    response = custom_app_downlink_handler(app, topic, msg)

    if not response:
        return

    (topic, msg) = response

    if "encodeHex" in default_app and default_app["encodeHex"]:
        payload_json = json.loads(msg)
        try:
            payload_json["data"] = b64encode(
                bytes.fromhex(payload_json["data"])
            ).decode()
            msg = json.dumps(payload_json)
        except Exception as e:
            logging.exception("Downlink encode exception", exc_info=e)
            pass

    # while not local_client.is_connected():
    #     logging.info("Local broker disconnected")
    #     time.sleep(1)

    local_client.publish(topic, msg, 1, True)


def app_publish_msg(app, topic, msg):
    global app_message_queue

    if re.match(".*\/up$", topic):
        logging.debug("Uplink json_data: %s", msg)

        response = custom_app_uplink_handler(app, topic, msg)
        if not response:
            return False
        else:
            (topic, msg) = response

    appeui = app["eui"]

    if app["isMqtt"]:
        with mqtt_client_locks[str(app["eui"])]:
            while apps[str(appeui)]["disconnected_flag"]:
                if len(app_message_queue[appeui]) < 10000:
                    app_message_queue[appeui].insert(0, (topic, msg))
                else:
                    logging.warning("Broker disconnected, packet dropped, queue full")
                return

            result = mqtt_clients[str(appeui)].publish(topic, msg, 1, True)

    elif app["isHttp"]:
        if app["eui"] in http_uplink_queue:
            while (
                http_uplink_queue[app["eui"]].qsize()
                >= http_threads[app["eui"]]["queue_size"]
            ):
                http_uplink_queue[app["eui"]].get()
                http_uplink_queue[app["eui"]].task_done()
        http_uplink_queue[app["eui"]].put((topic, msg))

    return True


def app_publish_http(app, path, msg, retain=False):
    logging.debug("POST to '%s'", path)
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
                    logging.debug("%d %s", res.status, res.reason)
                    data = res.read().decode("utf-8")
                    logging.debug(data)
                    sent = True
                    break
            except (IOError, KeyboardInterrupt) as e:
                logging.error("Request exception", e)
                http_clients[app["eui"]].close()
            except (
                BadStatusLine,
                ResponseNotReady,
                CannotSendRequest,
                CannotSendHeader,
                MemoryError,
            ) as e:
                logging.error("Response exception", e)
                http_clients[app["eui"]].close()
            finally:
                retry = retry - 1
                if not sent:
                    time.sleep(5)

        if not sent and retain:
            while (
                http_uplink_queue[app["eui"]].qsize()
                >= http_threads[app["eui"]]["queue_size"]
            ):
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
                    http_threads[app["eui"]]["downlink_query_interval"] = data_json[
                        "downlink_query_interval"
                    ]
                if "queue_size" in data_json:
                    http_threads[app["eui"]]["queue_size"] = data_json["queue_size"]

                http_threads[app["eui"]]["ready"] = True
        except ValueError:
            logging.error("failed to parse response as json")


def on_mqtt_connect(client, userdata, flags, rc):
    logging.info("Connected with result code " + str(rc))
    client.subscribe(local_mqtt_sub_up, 1)
    client.subscribe(local_mqtt_sub_joined, 1)
    client.subscribe(local_mqtt_sub_moved, 1)
    logging.info(userdata)
    if userdata and "eui" in userdata and userdata["eui"] in apps:
        apps[userdata["eui"]]["disconnected_flag"] = False


def on_mqtt_message(client, userdata, msg):
    global apps
    global mqtt_clients
    global gw_uuid
    global gw_serial

    parts = msg.topic.split("/")
    appeui = ""
    deveui = parts[1]
    event = parts[2]

    if len(parts) > 3:
        appeui = parts[1]
        deveui = parts[2]
        event = parts[3]

    # override appeui for all packets sent to default app client
    device_appeui = appeui

    if default_app["apiVersion"] == api_v1_1 or default_app["disableFilter"]:
        appeui = default_app["eui"]

    logging.debug("Device eui: " + deveui + " App eui: " + appeui + " Event: " + event)

    if event == "joined":
        logging.debug("Device joined " + deveui)

        try:
            json_data = json.loads(msg.payload.decode("utf-8"))

            logging.debug("App eui: " + json_data["appeui"])
            if default_app["apiVersion"] == api_v1_1 or default_app["disableFilter"]:
                device_appeui = json_data["appeui"]
            else:
                appeui = json_data["appeui"]

            gweui = json_data["gweui"]
            json_data["time"] = datetime.datetime.now().isoformat() + "Z"
            json_data["deveui"] = deveui
        except ValueError:
            logging.error("Decoding JSON has failed")
            return

        if appeui not in apps:
            stream = os.popen("lora-query -x appnet get " + appeui)
            output = stream.read()
            stream.close()
            app_data = json.loads(output)

            if "status" in app_data and app_data["status"] == "fail":
                logging.info("Failed to find application from network server")
                return
            else:
                apps[appeui] = app_data
                setup_app(app_data)

        if apps[appeui]["isMqtt"]:
            if default_app["apiVersion"] == api_v1_0:
                mqtt_subscribe_to_app_topics(appeui)
            else:
                if (
                    default_app["options"]["downlinkTopic"]
                    != app_default_mqtt_downlink_topic
                ):
                    mqtt_subscribe_to_custom_topics_v1_1(appeui)

            # Azure will disconnect if unauthorized topics are published
            if (
                not "cloudService" in apps[appeui]["options"]
                or apps[appeui]["options"]["cloudService"] != "AZURE"
            ):
                if default_app["apiVersion"] == api_v1_1:
                    joined_topic = app_mqtt_v1_1_joined_topic % (
                        gw_uuid,
                        device_appeui,
                        deveui,
                    )
                    app_publish_msg(apps[appeui], joined_topic, json.dumps(json_data))
                else:
                    joined_topic = app_mqtt_joined_topic % (device_appeui, deveui)
                    app_publish_msg(apps[appeui], joined_topic, json.dumps(json_data))
                    joined_topic = app_mqtt_joined_topic % (gw_uuid, deveui)
                    app_publish_msg(apps[appeui], joined_topic, json.dumps(json_data))

        elif apps[appeui]["isHttp"]:
            topic = app_http_joined_path % (device_appeui, deveui)
            app_publish_msg(apps[appeui], topic, json.dumps(json_data))
            if not appeui in http_app_devices:
                http_app_devices[appeui] = []

            if deveui not in http_app_devices[appeui]:
                http_app_devices[appeui].append(deveui)

    if event == "up":
        if appeui in apps:
            if apps[appeui]["isMqtt"]:
                if apps[appeui]["disconnected_flag"] == True:
                    # schedule downlink with backhaul down message default port: 1 data: 0xFF ("/w==") payload
                    # downlink should be scheduled only once per X (default:10) minutes to avoid causing data-pending flag to be set and infinite uplinks from end-device
                    backhaul_detect_enabled = False
                    backhaul_timeout = 600
                    backhaul_port = 1
                    backhaul_payload = "/w=="

                    if "backhaulDetect" in default_app:
                        if "enabled" in default_app["backhaulDetect"]:
                            backhaul_detect_enabled = default_app["backhaulDetect"][
                                "enabled"
                            ]

                        if "timeout" in default_app["backhaulDetect"]:
                            backhaul_timeout = default_app["backhaulDetect"]["timeout"]

                        if "port" in default_app["backhaulDetect"]:
                            backhaul_port = default_app["backhaulDetect"]["port"]

                        if "payload" in default_app["backhaulDetect"]:
                            backhaul_payload = b64encode(
                                bytes.fromhex(default_app["backhaulDetect"]["payload"])
                            ).decode()

                    if backhaul_detect_enabled:
                        cur_epoc_time = int(time.time())
                        if deveui in devices:
                            logging.debug(
                                "check backhaul down time %d %d %d",
                                cur_epoc_time,
                                devices[deveui]["last_seen"],
                                (cur_epoc_time - devices[deveui]["last_seen"]),
                            )
                        if not deveui in devices or (
                            deveui in devices
                            and (cur_epoc_time - devices[deveui]["last_seen"])
                            > backhaul_timeout
                        ):
                            devices[deveui] = {"last_seen": cur_epoc_time}
                            app_schedule_downlink(
                                apps[appeui],
                                deveui,
                                json.dumps(
                                    {"port": backhaul_port, "data": backhaul_payload}
                                ),
                            )

                if "encodeHex" in default_app and default_app["encodeHex"]:
                    payload_json = json.loads(msg.payload)
                    payload_json["data"] = b64decode(payload_json["data"]).hex()
                    payload_json["data-format"] = "hexadecimal"
                    msg.payload = json.dumps(payload_json)

                if (
                    "cloudService" in apps[appeui]["options"]
                    and apps[appeui]["options"]["cloudService"] == "AZURE"
                ):
                    json_temp = json.loads(msg.payload)
                    json_temp["client_id"] = default_app["options"]["client_id"]
                    uplink_topic = default_app["options"]["uplinkTopic"] % json_temp
                elif (
                    default_app["options"]["overrideTopicsForAllApps"]
                    and default_app["options"]["uplinkTopic"]
                    != app_default_mqtt_uplink_topic
                ):
                    json_data = json.loads(msg.payload)
                    json_data["gwuuid"] = gw_uuid
                    json_data["gwserial"] = gw_serial
                    uplink_topic = default_app["options"]["uplinkTopic"] % json_data
                elif (
                    "uplinkTopic" in apps[appeui]["options"]
                    and apps[appeui]["options"]["uplinkTopic"]
                    != app_default_mqtt_uplink_topic
                ):
                    json_data = json.loads(msg.payload)
                    json_data["gwuuid"] = gw_uuid
                    json_data["gwserial"] = gw_serial
                    uplink_topic = apps[appeui]["options"]["uplinkTopic"] % json_data
                elif default_app["apiVersion"] == api_v1_1:
                    uplink_topic = app_mqtt_v1_1_uplink_topic % (
                        gw_uuid,
                        device_appeui,
                        deveui,
                    )
                else:
                    uplink_topic = app_mqtt_uplink_topic % (device_appeui, deveui)

                app_publish_msg(apps[appeui], uplink_topic, msg.payload)
            elif apps[appeui]["isHttp"]:
                if "encodeHex" in default_app and default_app["encodeHex"]:
                    payload_json = json.loads(msg.payload)
                    payload_json["data"] = b64decode(payload_json["data"]).hex()
                    payload_json["data-format"] = "hexadecimal"
                    msg.payload = json.dumps(payload_json)

                app_publish_msg(
                    apps[appeui],
                    app_http_uplink_path % (device_appeui, deveui),
                    msg.payload,
                )

    if event == "moved":
        if appeui in apps:
            if apps[appeui]["isMqtt"]:
                if (
                    not "cloudService" in apps[appeui]["options"]
                    or apps[appeui]["options"]["cloudService"] != "AZURE"
                ):
                    if default_app["apiVersion"] == api_v1_1:
                        app_publish_msg(
                            apps[default_app["eui"]],
                            app_mqtt_v1_1_moved_topic
                            % (gw_uuid, device_appeui, deveui),
                            None,
                        )
                    else:
                        app_publish_msg(
                            apps[appeui],
                            app_mqtt_moved_topic % (device_appeui, deveui),
                            msg.payload,
                        )
                else:
                    return

                if (
                    "overrideTopicsForAllApps" in default_app["options"]
                    and default_app["options"]["overrideTopicsForAllApps"]
                    and default_app["options"]["downlinkTopic"]
                    != app_default_mqtt_downlink_topic
                ):
                    if "(deveui)s" in default_app["options"]["downlinkTopic"]:
                        topic = default_app["options"]["downlinkTopic"] % {
                            "appeui": appeui,
                            "deveui": deveui,
                            "gwuuid": gw_uuid,
                            "gwserial": gw_serial,
                        }
                        logging.debug("unsubscribe for app messages: %s", topic)
                        mqtt_clients[appeui].unsubscribe(str(topic), 1)
                elif (
                    "downlinkTopic" in apps[appeui]["options"]
                    and apps[appeui]["options"]["downlinkTopic"]
                    != app_default_mqtt_downlink_topic
                ):
                    if "(deveui)s" in default_app["options"]["downlinkTopic"]:
                        topic = apps[appeui]["options"]["downlinkTopic"] % {
                            "appeui": appeui,
                            "deveui": deveui,
                            "gwuuid": gw_uuid,
                            "gwserial": gw_serial,
                        }
                        logging.debug("unsubscribe from app messages: %s", topic)
                        mqtt_clients[appeui].unsubscribe(str(topic), 1)

                if default_app["apiVersion"] == api_v1_1:
                    return

                # unsubscribe from topic_list using appeui, deveui, gw_uuid
                for _topic in topic_list:
                    topic = _topic % (appeui, deveui)
                    logging.debug("unsubscribe from app messages: %s", topic)
                    mqtt_clients[appeui].unsubscribe(str(topic), 1)

                    topic = _topic % (gw_uuid, deveui)
                    logging.debug("unsubscribe from app messages: %s", topic)
                    mqtt_clients[appeui].unsubscribe(str(topic), 1)

                    topic = _topic % (appeui, gw_uuid)
                    logging.debug("unsubscribe from app messages: %s", topic)
                    mqtt_clients[appeui].unsubscribe(str(topic), 1)

                # unsubscribe from gateway/deveui topics
                for gw in gateways:
                    topic = app_mqtt_downlink_topic % (gw, deveui)
                    logging.debug("unsubscribe from downlinks: %s", topic)
                    mqtt_clients[appeui].unsubscribe(str(topic), 1)

                    topic = app_mqtt_clear_topic % (gw, deveui)
                    logging.debug("unsubscribe from queue clear: %s", topic)
                    mqtt_clients[appeui].unsubscribe(str(topic), 1)


def http_uplink_thread(appeui):
    logging.info("Uplink thread %s started", appeui)

    while http_threads[appeui]["running"]:
        logging.info("Uplink thread %s", appeui)

        # if not http_threads[appeui]["ready"]:
        #     time.sleep(5)
        #     continue

        if http_uplink_queue[appeui].qsize() > 1:
            msg = None
            msgs = []
            cnt = 0
            join_break = False
            while not http_uplink_queue[appeui].empty() and cnt < 10:
                msg = http_uplink_queue[appeui].get()

                if msg is None or (len(msg) != 2 and not (msg[0] or msg[1])):
                    http_uplink_queue[appeui].task_done()
                    break

                if len(msg[1]) > 700 or re.match(".*\/joined$", msg[0]):
                    join_break = True
                    http_uplink_queue[appeui].task_done()
                    break

                msgs.append(json.loads(msg[1]))
                http_uplink_queue[appeui].task_done()
                cnt = cnt + 1

            if len(msgs) > 0:
                app_publish_http(
                    apps[appeui],
                    app_http_uplink_app_path % (appeui),
                    json.dumps(msgs),
                    True,
                )

            if join_break:
                app_publish_http(apps[appeui], msg[0], msg[1], True)
        else:
            msg = http_uplink_queue[appeui].get()
            app_publish_http(apps[appeui], msg[0], msg[1], True)
            http_uplink_queue[appeui].task_done()

    logging.info("Uplink thread %s exited", appeui)
    return


def http_downlink_thread(appeui):
    logging.info("Downlink thread %s started", appeui)

    while http_threads[appeui]["running"]:
        logging.info("Downlink thread %s", appeui)

        if not appeui in http_app_devices:
            logging.info("Device list for %s not found", appeui)
            with http_threads[appeui]["downlink_cond"]:
                http_threads[appeui]["downlink_cond"].wait(5)
            continue

        if not http_threads[appeui]["ready"]:
            with http_threads[appeui]["downlink_cond"]:
                http_threads[appeui]["downlink_cond"].wait(5)
            continue

        path = app_http_downlink_path % (appeui)

        deveuis = http_app_devices[appeui]
        logging.debug("GET from '%s'", path)
        headers = {"Content-type": "application/json", "Accept": "text/plain"}

        data = None

        if appeui in http_clients:
            sent = False
            retry = 3

            while retry and http_threads[appeui]["running"]:
                try:
                    with http_threads[appeui]["lock"]:
                        http_clients[appeui].request(
                            "GET", path, json.dumps(deveuis), headers
                        )
                        res = http_clients[appeui].getresponse()
                        logging.debug("%d %s", res.status, res.reason)
                        data = res.read().decode("utf-8")
                        logging.debug("API Response: " + data)
                        break
                except (IOError, KeyboardInterrupt) as e:
                    print("Exception during request GET", e)
                    http_clients[appeui].close()
                except (
                    BadStatusLine,
                    ResponseNotReady,
                    CannotSendRequest,
                    CannotSendHeader,
                    MemoryError,
                ) as e:
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
                            app_schedule_downlink(
                                apps[appeui], downlink["deveui"], json.dumps(downlink)
                            )
            except ValueError:
                logging.error("failed to parse response as json")

        with http_threads[appeui]["downlink_cond"]:
            http_threads[appeui]["downlink_cond"].wait(
                http_threads[appeui]["downlink_query_interval"]
            )

    logging.info("Downlink thread %s exited", appeui)
    return


format = "%(asctime)s: %(message)s"
logging.basicConfig(format=format, level=logging.INFO, datefmt="%Y-%m-%dT%H:%M:%S%z")
handler = logging.handlers.SysLogHandler("/dev/log")
handler.ident = "lora-app-connect: "

logging.getLogger().addHandler(handler)
# rotate = logging.handlers.RotatingFileHandler('/var/log/lora-app-net.log', 'a', 15*1024, 4)
# rotate.rotator = GZipRotator()
# logging.getLogger().addHandler(rotate)

local_client = None


def setup_local_client():
    global local_client
    local_client = mqtt.Client(userdata={"eui": "localhost"})

    local_client.on_connect = on_mqtt_connect
    local_client.on_message = on_mqtt_message
    local_client.on_subscribe = on_mqtt_subscribe
    local_client.on_disconnect = on_mqtt_disconnect

    mqtt_client_locks["localhost"] = threading.Lock()
    local_client.connect("127.0.0.1", 1883, 60)


setup_local_client()

stream = os.popen("curl -s 127.0.0.1/api/loraNetwork | jsparser --jsobj --path result")
output = stream.read()
stream.close()

lora_config = json.loads(output)

lora_query_available = False
app_list = []

if lora_config["lora"]["enabled"] and not (
    lora_config["lora"]["basicStationMode"]
    or lora_config["lora"]["packetForwarderMode"]
):
    lora_query_available = True


stream = os.popen(
    "curl -s 127.0.0.1/api/loraNetwork/defaultApp | jsparser --jsobj --path result"
)
output = stream.read()
stream.close()


try:
    default_app = json.loads(output)
    # sanitize the appeui
    default_app["eui"] = "-".join(
        re.findall("..", default_app["eui"].replace("-", "").lower())
    )

    if not "apiVersion" in default_app:
        default_app["apiVersion"] = api_v1_0

    if not lora_query_available:
        default_app["requestOptions"]["lora"] = False

    if default_app["apiVersion"] == api_v1_0:
        if "requestOptions" in default_app and default_app["requestOptions"]["api"]:
            api_topic_list.append(app_mqtt_api_request_topic)
        if "requestOptions" in default_app and default_app["requestOptions"]["lora"]:
            api_topic_list.append(app_mqtt_lora_request_topic)
        if "requestOptions" in default_app and default_app["requestOptions"]["log"]:
            api_topic_list.append(app_mqtt_log_request_topic)
    else:
        default_app["eui"] = appeui_all_devices
        if "requestOptions" in default_app and default_app["requestOptions"]["api"]:
            api_topic_list.append(app_mqtt_v1_1_api_request_topic)
        if "requestOptions" in default_app and default_app["requestOptions"]["lora"]:
            api_topic_list.append(app_mqtt_v1_1_lora_request_topic)
        if "requestOptions" in default_app and default_app["requestOptions"]["log"]:
            api_topic_list.append(app_mqtt_v1_1_log_request_topic)

    default_app["disableFilter"] = default_app["eui"] == appeui_all_devices

    if not "overrideTopicsForAllApps" in default_app["options"]:
        default_app["options"]["overrideTopicsForAllApps"] = False

    log_levels = {100: 0, 60: 0, 50: 10, 30: 20, 20: 30, 10: 40, 0: 50}

    if "log" in default_app:
        log_level = log_levels.get(default_app["log"]["level"], 20)
        logging.info("Set log level %d", log_level)
        logging.getLogger().setLevel(log_level)

        if default_app["log"]["destination"] == "FILE":
            file_handler = logging.FileHandler(filename=default_app["log"]["path"])
            logging.getLogger().addHandler(file_handler)
            logging.getLogger().removeHandler(handler)

    else:
        try:
            log_info = lora_config["log"]
            log_level = log_levels.get(log_info["level"], 20)
            logging.info("Set log level %d", log_level)
            logging.getLogger().setLevel(log_level)
        except ValueError:
            time.sleep(5)
            exit(1)

except ValueError:
    logging.error("Network Server is not available")
    time.sleep(5)
    exit(1)


stream = os.popen("cat /sys/devices/platform/mts-io/uuid")
gw_uuid = stream.read()
stream.close()

if default_app["apiVersion"] == api_v1_0:
    gw_uuid = gw_uuid[:-1]
else:
    gw_uuid = str(uuid.UUID(gw_uuid[:-1]))
    app_default_mqtt_uplink_topic = app_default_v1_1_mqtt_uplink_topic
    app_default_mqtt_downlink_topic = app_default_v1_1_mqtt_downlink_topic


stream = os.popen("cat /sys/devices/platform/mts-io/device-id")
gw_serial = stream.read()
stream.close()
gw_serial = gw_serial[:-1]


if not lora_query_available:
    stream = os.popen(
        "curl -s 127.0.0.1/api/system/accessoryCards | jsparser --jsobj --path result"
    )
    output = stream.read()
    stream.close()

    cards = json.loads(output)

    for card in cards:
        gateways.append(card["eui"].replace(":", "-").lower())

else:
    stream = os.popen("lora-query -x gateways list json")
    output = stream.read()
    stream.close()

    try:
        gw_list = json.loads(output)
    except ValueError:
        exit(1)

    for gw in gw_list:
        gateways.append(gw["gweui"])

    stream = os.popen("lora-query -x appnet list json")
    output = stream.read()
    app_list = json.loads(output)
    stream.close()

    for app in app_list:
        apps[app["eui"]] = app
        logging.debug("Setup App", app)
        setup_app(app)

    query = os.popen("lora-query -x session list json file /tmp/sessions.json")
    query.read()
    file = open("/tmp/sessions.json", mode="r")
    dev_list = json.loads(file.read())
    file.close()
    query.close()

    for dev in dev_list:
        if dev["appeui"] in apps:
            if apps[dev["appeui"]]["isMqtt"] and dev["appeui"] in mqtt_clients:
                mqtt_subscribe_to_app_topics(dev["appeui"])

            if apps[dev["appeui"]]["isHttp"] and dev["appeui"] in http_clients:
                if dev["appeui"] not in http_app_devices:
                    http_app_devices[dev["appeui"]] = []
                if dev["appeui"] not in http_app_devices[dev["appeui"]]:
                    http_app_devices[dev["appeui"]].append(dev["deveui"])


# Load default app info after known appnets, this allows default app to override LENS if enabled

if "enabled" in default_app and default_app["enabled"]:
    apps[default_app["eui"]] = default_app
    setup_app(default_app)


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


logging.info("Start client")

local_client.loop_start()

run = True


def handler_stop_signals(signum, frame):
    global run
    run = False


signal.signal(signal.SIGINT, handler_stop_signals)
signal.signal(signal.SIGTERM, handler_stop_signals)

refreshed = time.time()

while run:
    if time.time() - refreshed > 60:
        refreshed = time.time()

        if lora_query_available:
            # refresh the app list in case of changes
            stream = os.popen("lora-query -x appnet list json")
            output = stream.read()
            stream.close()
            try:
                test_app_list = json.loads(output)
            except ValueError:
                continue

            logging.debug("Check for app updates")

            for test_app in test_app_list:
                test_eui = test_app["eui"]
                if not test_eui in apps:
                    apps[test_eui] = test_app
                    setup_app(test_app)
                    continue

                for appeui in apps:
                    if appeui == test_eui and test_eui != default_app["eui"]:
                        if not compare_apps(apps[appeui], test_app):
                            if apps[appeui]["isMqtt"]:
                                mqtt_clients[appeui].publish(
                                    "lorawan/" + appeui + "/" + gw_uuid + "/close",
                                    None,
                                    1,
                                    True,
                                )
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
    logging.info("Closing default app")
    if apps[default_app["eui"]]["isMqtt"]:
        logging.info("default app is connected %s", default_app["eui"])
        if default_app["apiVersion"] == api_v1_1:
            app_publish_msg(
                apps[default_app["eui"]],
                app_mqtt_v1_1_close_topic % (gw_uuid),
                None,
            )
        else:
            app_publish_msg(
                apps[default_app["eui"]],
                app_mqtt_close_topic % (default_app["eui"], gw_uuid),
                None,
            )
        time.sleep(2)
        mqtt_clients[default_app["eui"]].disconnect()
        mqtt_clients[default_app["eui"]].loop_stop()

    if apps[default_app["eui"]]["isHttp"]:
        app_publish_msg(
            apps[default_app["eui"]],
            app_http_close_path % (default_app["eui"], gw_uuid),
            None,
        )

        time.sleep(5)

        http_threads[default_app["eui"]]["running"] = False
        app_publish_msg(apps[default_app["eui"]], "", None)

        with http_threads[default_app["eui"]]["downlink_cond"]:
            http_threads[default_app["eui"]]["downlink_cond"].notify()

        http_threads[default_app["eui"]]["uplink"].join()
        http_threads[default_app["eui"]]["downlink"].join()


logging.info("Closing apps")

for app in app_list:
    if app["eui"] in mqtt_clients:
        if mqtt_clients[app["eui"]].is_connected():
            logging.info("app is connected %s", app["eui"])
            if default_app["apiVersion"] == api_v1_1:
                app_publish_msg(
                    apps[default_app["eui"]],
                    app_mqtt_v1_1_close_topic % (gw_uuid),
                    None,
                )
            else:
                app_publish_msg(
                    apps[default_app["eui"]],
                    app_mqtt_close_topic % (default_app["eui"], gw_uuid),
                    None,
                )
            time.sleep(2)
            mqtt_clients[app["eui"]].disconnect()
            mqtt_clients[app["eui"]].loop_stop()

    if app["eui"] in http_clients:
        app_publish_msg(
            apps[app["eui"]], app_http_close_path % (app["eui"], gw_uuid), None
        )

        time.sleep(5)

        http_threads[app["eui"]]["running"] = False
        app_publish_msg(apps[app["eui"]], "", None)

        with http_threads[app["eui"]]["downlink_cond"]:
            http_threads[app["eui"]]["downlink_cond"].notify()

        http_threads[app["eui"]]["uplink"].join()
        http_threads[app["eui"]]["downlink"].join()


logging.info("app exit")
