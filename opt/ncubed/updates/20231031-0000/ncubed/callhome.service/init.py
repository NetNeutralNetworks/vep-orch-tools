#!/bin/python3
import time, traceback
import json, yaml, requests, re
import os, sys
import subprocess
import ipaddress

import logging
from logging.handlers import RotatingFileHandler
from shutil import copy

GW_TEST_IP="8.8.8.8"
LOCAL_CONFIG_FOLDER = "/opt/ncubed/config/local"
GLOBAL_CONFIG_FOLDER = "/opt/ncubed/config/global"
ORCHESTRATION_V4_PREFIX = "100.71"

# ATTESTATION_SERVER="attestation.d0001.ncubed.io"
#ATTESTATION_SERVER="attestation.infra.ncubed.io"
WG_CONFIG_FILE="/etc/wireguard/wg0.conf"
WG_PRIVATE_KEY_FILE="/etc/wireguard/netcube01.private.key"
WG_PUBLIC_KEY_FILE="/etc/wireguard/netcube01.public.key"

STATUS_FILE = "/opt/ncubed/status.json"

ORCH_INFO_FILE = f'{LOCAL_CONFIG_FOLDER}/orch_info.yaml'

def get_attestation_config():
    if os.path.exists(f'{LOCAL_CONFIG_FOLDER}/attestation.yaml'):
        with open(f'{LOCAL_CONFIG_FOLDER}/attestation.yaml') as f:
            attestation_config = yaml.load(f, Loader=yaml.FullLoader)
            return attestation_config.get('attestation_server')
    else:
        with open(f'{GLOBAL_CONFIG_FOLDER}/attestation.yaml') as f:
            attestation_config = yaml.load(f, Loader=yaml.FullLoader)
            return attestation_config.get('attestation_server')


logger = logging.getLogger("ncubed callhome")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s,Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(message)s',
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.callhome.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

# Goes through all the namespaces and checks if the hardware interface is up
def get_device_config():
    with open(f'{GLOBAL_CONFIG_FOLDER}/network.yaml') as f:
        PORT_CONFIGS = yaml.load(f, Loader=yaml.FullLoader)
    DEV_FAMILIY=subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG=[C for C in PORT_CONFIGS if DEV_FAMILIY == C.get('family')]
    return DEV_CONFIG

def get_existing_netnamespaces():
    existing_netnamespaces_json = subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    if existing_netnamespaces_json:
        existing_netnamespaces=json.loads(existing_netnamespaces_json)
        return existing_netnamespaces
    else:
        return {}

def get_existing_wireguard_interfaces():
     wg_interfaces = subprocess.run(f"wg show interfaces", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().split()
     return wg_interfaces

def check_active_uplinks():
    available_ns = []
    for NETNS in get_existing_netnamespaces():
        NETNS = NETNS.get('name')
        logger.debug(f"Test {NETNS}")
        output = subprocess.run(f"ip netns exec {NETNS} ping -c 1 -W 1 {GW_TEST_IP}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
        if "received, 0% packet loss" in output:
            available_ns.append(NETNS)

    logger.debug(f"Found the following active net namespaces: {available_ns}")
    return available_ns

def callhome(net_namespace):
    if os.path.exists(WG_PRIVATE_KEY_FILE):
        logger.debug("Using existing key")
    else:
        logger.debug("Generating keys")
        subprocess.run(f"wg genkey | tee {WG_PRIVATE_KEY_FILE} | wg pubkey > {WG_PUBLIC_KEY_FILE}", shell=True)
        subprocess.run(f"chmod 600 {WG_PRIVATE_KEY_FILE} {WG_PUBLIC_KEY_FILE}", shell=True)

    servicetag = subprocess.run(f"dmidecode -s system-serial-number", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    logger.debug(f"Service tag: {servicetag}")
    with open(WG_PUBLIC_KEY_FILE, 'r') as f:
        pub_key = f.read()
        logger.debug(pub_key)
  
        body = f'{{"asset_tag": "{servicetag}","client_pub_key": "{pub_key.strip()}","additional_info": {{"version": "new"}} }}'

        logger.debug(f"Calling attestation server from: {net_namespace}")
        attestation_result = subprocess.run(f"ip netns exec {net_namespace} curl \
                                            -X POST 'https://{get_attestation_config()}/api/v1/clientapi/register' \
                                            -H 'Content-Type: application/json' \
                                            -d '{body}'", shell=True, capture_output=True, text=True).stdout
        logger.debug(f"Attestion response: {attestation_result}")
        try:
            attestation_result=json.loads(attestation_result)
            if  attestation_result['message'].lower() == "success":
                # servers = orch_server['result']['servers']
                # device_id = orch_server['result']['device_id']
                return attestation_result
            elif attestation_result['message'] == "Not authorized":
                for i in range(3):
                    subprocess.run(f"/opt/ncubed/bin/led cyan", shell=True)
                    time.sleep(.5)
                    subprocess.run(f"/opt/ncubed/bin/led orange", shell=True)
                    time.sleep(.5)
                    subprocess.run(f"/opt/ncubed/bin/led red", shell=True)
                    time.sleep(.5)
                return False
        except ValueError as e:
            return False

def create_wireguard_interface(NETNS, config, device_id, id):
    logger.debug(f"trying to establish new tunnel on {NETNS}")
    WG_INTF_NAME = f"wg_{id}_{NETNS}"

    
    logger.debug(f"Setting up connection to: {config['orchestration_server']}")
    # IPv4 is still being used for libre monitoring. This should not be used for anyhting else
    #         listen-port 51821 \
    ipv6_network = str(ipaddress.ip_network(config['ipv6_supernet']).network_address)
    try:
        ipaddress.ip_address(config['orchestration_server'])
        orch_ip = config['orchestration_server']
    except ValueError:
        # server is not an IP address
        resolve_text = subprocess.run(f"ip netns exec {NETNS} host {config['orchestration_server']}", shell=True, capture_output=True, text=True).stdout
        try:
            ipaddress.ip_address(resolve_text.split(" ")[-1].strip())
            orch_ip = resolve_text.split(" ")[-1].strip()
        except:
            logger.debug(f"Could not resolve Orch server: {config['orchestration_server']}")
            return False

    server = f"{orch_ip}:51820"
    subprocess.call(f'''
        ip netns exec {NETNS} ip link add dev {WG_INTF_NAME} type wireguard
        ip netns exec {NETNS} ip link set {WG_INTF_NAME} netns 1
        ip addr add dev {WG_INTF_NAME} {ORCHESTRATION_V4_PREFIX}.0.{device_id}/32
        ip addr add dev {WG_INTF_NAME} {ipv6_network}{device_id}/128
        wg set {WG_INTF_NAME} \
            listen-port {51820 + id} \
            private-key /etc/wireguard/netcube01.private.key \
            peer {config['server_pub_key']} \
            persistent-keepalive 20 \
            allowed-ips {ORCHESTRATION_V4_PREFIX}.0.0/32,{ipv6_network}/128 \
            endpoint {server}
        ip link set up dev {WG_INTF_NAME}
        ip route add {ORCHESTRATION_V4_PREFIX}.0.0/32 dev {WG_INTF_NAME}
        ip route add {ipv6_network}/128 dev {WG_INTF_NAME}
    ''', shell=True)
    logger.debug(f"Created wireguard interface {WG_INTF_NAME}")

def set_led(color):
    try:
        subprocess.run(f"/opt/ncubed/bin/led {color.lower()}", shell=True)
    except Exception as e:
        logger.error(e)    

def clean_up_wg_quick():
    try:
        if os.path.exists(WG_CONFIG_FILE):
            
            subprocess.run(f"""
                        wg-quick down wg0
                        rm {WG_CONFIG_FILE}
                        """, shell=True)
            
    except Exception as e:
        logger.error(e)

           
def connect_to_orch_over_ns(orch_server, orch_info, ns):
    create_wireguard_interface(config=orch_server[1], device_id=orch_info.get('device_id'), NETNS=ns, id=orch_server[0])
    orch_server_ipv6 = str(ipaddress.ip_network(orch_server[1]['ipv6_supernet']).network_address)
    if subprocess.run(f"ping {orch_server_ipv6} -c 3 | grep -q 'bytes from'", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).returncode:
        # Not able to connect to orch_server in this netns

        logger.debug(f"Not able to connect to Orch: {orch_server[1]['orchestration_server']}. Removing wg tunnel.")
        # Remove interface
        subprocess.run(f"ip link del wg_{orch_server[0]}_{ns}", shell=True)

        # Try next netns
        return False
    else:
        # Device is connected to orch_server in this netns
        logger.debug(f"Succesful connection to {orch_server[1]['orchestration_server']}")
        return True

def connect_to_orch(name):
    with open(STATUS_FILE, 'r') as file:
        status = json.load(file)
    with open(ORCH_INFO_FILE, 'r') as file:
        orch_info = yaml.load(file).get('result', {})
    active_namespaces = status.get('active_namespaces', [])
    orchestration_servers = orch_info.get('servers', [])
    orch_server = [(index, x) for index, x in enumerate(orchestration_servers) if x['orchestration_server'] == name][0]
    current_tunnels = get_existing_wireguard_interfaces()

    used_namespaces = []

    for tunnel in current_tunnels:
        # Check all wg interfaces to see in what namespace they are being used
        if f"wg_{orch_server[0]}" in tunnel:
            subprocess.run(f"ip link del {tunnel}", shell=True)
        for ns in active_namespaces:
            if ns in tunnel:
                used_namespaces.append(ns)
    for ns in active_namespaces:
        # Try to find an unused namespace
        if ns in used_namespaces:
            # This Namespace is already used
            continue
        else:
            # This namespace in not in use
            if connect_to_orch_over_ns(orch_server, orch_info, ns):
                return True
            
    # No unused namespaces available
    for ns in used_namespaces:
        if connect_to_orch_over_ns(orch_server, orch_info, ns):
                return True
    # Orchserver not reachable over any namespace
    return False
    

def refresh_attestation():
    with open(STATUS_FILE, 'r') as file:
        status = json.load(file)
    for active_uplink in status.get('active_namespaces'):
        attestation_server_result = callhome(active_uplink)
        if attestation_server_result:
            with open(ORCH_INFO_FILE, 'w') as f:
                yaml.dump(attestation_server_result, f)
            return True
        else:
            logger.debug(f"No right response from DAS")
    return False


if __name__ == '__main__':
    logger.debug("Starting callhome service")
    subprocess.run(f"/usr/bin/efibootmgr -O", shell=True)
    clean_up_wg_quick()
    
    attempts = 0
    while True:
        try:
            with open(STATUS_FILE, 'r') as file:
                status = json.load(file)
            orch_status = status.get('orch_status')
            if orch_status == 'FULL':
                # Connection to all known orchestration servers are healthy
                set_led('purple')
                attempts = 0
                time.sleep(5)
                continue
            elif orch_status == 'NO SERVER':
                # No orch servers are known -> Do a callhome
                set_led('blue')
                time.sleep(1)
                set_led('red')
                refresh_attestation()
            elif orch_status == 'DISCONNECTED':
                set_led('green')
                time.sleep(1)
                set_led('red')
                attempts += 1
                # one hour = 600
                if attempts > 600:
                    logger.info(f"one hour without connection, checking to see if DAS is updated")
                    copy(ORCH_INFO_FILE, ORCH_INFO_FILE+".backup")
                    if not refresh_attestation():
                        logger.info(f"No good response from Attestation server, reverting to backup info.")
                        copy(ORCH_INFO_FILE+".backup", ORCH_INFO_FILE)
                for server, server_status in status.get('orchestration_servers', {}).items():
                    
                    if server_status == 0:
                        # try and reconnect the server
                        connect_to_orch(server)
            else:
                attempts = 0
                for server, server_status in status.get('orchestration_servers', {}).items():
                    
                    if server_status == 0:
                        # try and reconnect the server
                        connect_to_orch(server)

        except Exception as e:
            set_led('red')
            logger.error(f"Fatal error occured during callhome: {traceback.format_exc()}")
            
        time.sleep(5)
