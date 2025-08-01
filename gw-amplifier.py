import socket
import threading
import signal
import sys, json
import traceback
import argparse
import random

# This script is a gateway amplifier that forwards messages from simulated gateways

sim_gateway_count = 10
ip_addr = "172.16.0.221"
ip_gw = "172.16.0.227"
upstream_port = 1780
downstream_port = 1782
listen_up_port = 1780
listen_down_port = 1782
gw_eui_prefix = "008000DDDD00"
sim_gw_rssi = 0
sim_gw_snr = 0

parser = argparse.ArgumentParser()
parser.add_argument('--gw-count', type=int, default=sim_gateway_count, help='Number of simulated gateways')
parser.add_argument('--bind-ip', type=str, default=ip_addr, help='IP address to bind the gateway amplifier')
parser.add_argument('--gw-lns-ip', type=str, default=ip_gw, help='IP address of the gateway LNS')
parser.add_argument('--up-port', type=int, default=upstream_port, help='Upstream port of the gateway LNS (default: 1780)')
parser.add_argument('--down-port', type=int, default=downstream_port, help='Downstream port of the gateway LNS (default: 1782)')
parser.add_argument('--listen-up-port', type=int, default=listen_up_port, help='Amplifier listening port for gateway uplinks (default: 1780)')
parser.add_argument('--listen-down-port', type=int, default=listen_down_port, help='Amplifier listening port gateway downlinks (default: 1782)')
parser.add_argument('--gw-eui-prefix', type=str, default=gw_eui_prefix, help='Prefix for the gateway EUI, 6 bytes hex string, example "008000DDDD00"')
parser.add_argument('--rssi', type=int, default=sim_gw_rssi, help='RSSI value for simulated gateways (default: RANDOM)')
parser.add_argument('--snr', type=int, default=sim_gw_rssi, help='SNR value for simulated gateways (default: RANDOM)')
args = parser.parse_args()


sim_gateway_count = args.gw_count
ip_addr = args.bind_ip
ip_gw = args.gw_lns_ip
upstream_port = args.up_port
downstream_port = args.down_port
listen_up_port = args.listen_up_port
listen_down_port = args.listen_down_port
gw_eui_prefix = args.gw_eui_prefix
sim_gw_rssi = args.rssi
sim_gw_snr = args.snr


PKF_VER=2

PUSH_DATA = 0
PUSH_ACK = 1

PULL_DATA = 2
PULL_RESP = 3
PULL_ACK = 4
TX_ACK = 5

up_messages = {
    PUSH_DATA: "push_data",
    PUSH_ACK: "push_ack",    
}

down_messages = {
    PULL_DATA: "pull_data",
    PULL_RESP: "pull_resp",
    PULL_ACK: "pull_ack",
    TX_ACK: "tx_ack"
}



proc_quit = False

def signal_handler(sig, frame):
    global proc_quit
    print("sig received")
    proc_quit = True
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

socket.setdefaulttimeout(0.1)

up_server = (ip_gw, upstream_port)
down_server = (ip_gw, downstream_port)
bufSize = 1024


upstream_sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
downstream_sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

upstream_sock.bind((ip_addr, listen_up_port))
downstream_sock.bind((ip_addr, listen_down_port))


pkf_up_addr = None
pkf_down_addr = None


gw_euis = []
upstream_clients = []
downstream_clients = []
upstream_threads = []
downstream_threads = []

def upstream_thread(index):
    global pkf_up_addr

    while (not proc_quit):
        try:
            msg = upstream_clients[index].recv(bufSize)
            if pkf_up_addr and not (msg[3] == PUSH_ACK and index != 0):
                print("up  :", up_messages[msg[3]], msg)
                upstream_sock.sendto(msg, pkf_up_addr)
        except:
        # except Exception:
        #    traceback.print_exc()
            pass


def downstream_thread(index):
    global pkf_down_addr

    while (not proc_quit):
        try:
            msg = downstream_clients[index].recv(bufSize)
            # print("down:", msg, len(msg))
            # print("down:", down_messages[msg[3]], msg)
            if pkf_down_addr and not (msg[3] == PULL_ACK and index != 0):
                print("down:", down_messages[msg[3]], msg)
                downstream_sock.sendto(msg, pkf_down_addr)
        except TimeoutError:
            pass
        except Exception:
            traceback.print_exc()
            pass


# Create sockets for passing on actual gateway packets
upstream_clients.append(socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM))
upstream_threads.append(threading.Thread(target=upstream_thread, args=(0,)))
downstream_clients.append(socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM))
downstream_threads.append(threading.Thread(target=downstream_thread, args=(0,)))

# Create sockets for simulated gateways
for i in range(sim_gateway_count):
    gw_euis.append(bytearray.fromhex(gw_eui_prefix + "{:04x}".format(i)))
    upstream_clients.append(socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM))
    upstream_threads.append(threading.Thread(target=upstream_thread, args=(i+1,)))
    downstream_clients.append(socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM))
    downstream_threads.append(threading.Thread(target=downstream_thread, args=(i+1,)))

for t in upstream_threads:
    t.start()

for t in downstream_threads:
    t.start()


log_upstream = False
log_downstream = False
log_exceptions = False

print("Sockets open, forwarding packets to", ip_gw);
while (not proc_quit):
    msg = None
    try:
        msg = upstream_sock.recvfrom(bufSize)
        # Forward original gateway message to server
        upstream_clients[0].sendto(msg[0], up_server)
        pkf_up_addr = msg[1]
        print("upstream rx:", msg) 
        for i in range(sim_gateway_count):
            # replace message gw addr
            if log_upstream: print("upstream fwd:", msg)
            if log_upstream: print("replacing", msg[0][4:12], gw_euis[i])
            new_msg = msg[0].replace(msg[0][4:12], gw_euis[i])
            if log_upstream: print("json parse:", msg[0][12:].decode('utf-8'))
            msg_json = json.loads(msg[0][12:].decode("utf-8"))
            if ("rxpk" in msg_json):
                if (sim_gw_rssi != 0):
                    # Adjust RSSI for simulated gateways
                    if log_upstream: print("ADJUSTING RSSI FOR SIMULATED GATEWAY", i, "to", sim_gw_rssi)
                    msg_json["rxpk"][0]["rssi"] = sim_gw_rssi
                    msg_json["rxpk"][0]["rssis"] = sim_gw_rssi
                else:
                    val = random.randint(-100, -20)
                    msg_json["rxpk"][0]["rssi"] = val 
                    msg_json["rxpk"][0]["rssis"] = val

                if (sim_gw_snr != 0):
                    # Adjust SNR for simulated gateways
                    if log_upstream: print("ADJUSTING SNR FOR SIMULATED GATEWAY", i, "to", sim_gw_snr)
                    msg_json["rxpk"][0]["lsnr"] = sim_gw_snr
                else:
                    val = round((20.0 - random.random() * 40.0), 1)
                    msg_json["rxpk"][0]["lsnr"] = val
            
                new_msg = new_msg[:12] + bytearray(json.dumps(msg_json), 'utf-8')

            if log_upstream: print("ADJUSTED JSON:", msg_json)
            if log_upstream: print("upstream", i, new_msg)
            upstream_clients[i+1].sendto(new_msg, up_server)
    except TimeoutError:
        pass
    except Exception:
        if log_exceptions:
            print("upstream exc :", msg)
            traceback.print_exc()
        pass


    try:
        msg = downstream_sock.recvfrom(bufSize)
        print("downstream rx:", msg)
        print("downstream rx:", down_messages[msg[0][3]], msg)
        # Forward original gateway message to server
        downstream_clients[0].sendto(msg[0], up_server)
        if (msg[0][3] == TX_ACK):
            # TX_ACK is only needed once, so we don't forward it
            print("TX_ACK RECEIVED****")
            continue
        pkf_down_addr = msg[1]
        for i in range(sim_gateway_count):
            # replace message gw addr
            if (len(msg[0]) < 12):
                new_msg = msg[0]
            else:
                new_msg = msg[0].replace(msg[0][4:12], gw_euis[i])
            if log_downstream: print("downstream", i, new_msg)
            downstream_clients[i+1].sendto(new_msg, up_server)
    except TimeoutError:
        pass
    except:
        print("downstream exc :", msg)
        traceback.print_exc()
        pass



