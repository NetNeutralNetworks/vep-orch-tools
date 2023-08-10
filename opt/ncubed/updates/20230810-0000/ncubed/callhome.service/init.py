#!/bin/python3
import time, traceback
import json, yaml, requests, re
import os, sys
import subprocess

import logging
from logging.handlers import RotatingFileHandler

GW_TEST_IP="8.8.8.8"
LOCAL_CONFIG_FOLDER = "/opt/ncubed/config/local"
GLOBAL_CONFIG_FOLDER = "/opt/ncubed/config/global"
ORCHESTRATION_V4_PREFIX = "100.71"
ORCHESTRATION_V6_PREFIX = "fd71::"

ATTESTATION_SERVER="ncubed-das.westeurope.cloudapp.azure.com"
#ATTESTATION_SERVER="attestation.infra.ncubed.io"
WG_CONFIG_FILE="/etc/wireguard/wg0.conf"
WG_PRIVATE_KEY_FILE="/etc/wireguard/netcube01.private.key"
WG_PUBLIC_KEY_FILE="/etc/wireguard/netcube01.public.key"

ORCH_INFO_FILE = f'{LOCAL_CONFIG_FOLDER}/orch_info.yaml'


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

def check_connection():
    if subprocess.run(f"ping {ORCHESTRATION_V6_PREFIX} -c 3 | grep -q 'bytes from'", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).returncode:
        logger.debug("Connection dead")
        set_led('orange')
        return 0
    else:
        set_led('purple')
        return 1

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
    body = f'{{"asset_tag": "{servicetag}","client_pub_key": "{pub_key.strip()}"}}'

    logger.debug(f"Calling attestation server from: {net_namespace}")
    attestation_result = subprocess.run(f"ip netns exec {net_namespace} curl \
                                        -X POST 'https://{ATTESTATION_SERVER}/api/v1/clientapi/register' \
                                        -H 'Content-Type: application/json' \
                                        -d '{body}'", shell=True, capture_output=True, text=True).stdout
    logger.debug(f"Attestion response: {attestation_result}")
    try:
        orch_server=json.loads(attestation_result)
        if  orch_server['message'].lower() == "success":
            resolve_result = subprocess.run(f"ip netns exec {net_namespace} host {orch_server['result']['orchestration_server'].split(':')[0]}", capture_output=True, shell=True).stdout.decode()
            ip = re.search(r'has address (.*)',resolve_result).group(1)
            orch_server['result'].update({'ip':ip})
            return orch_server.get('result', False)
        elif orch_server['message'] == "Not authorized":
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

def get_orch_info(interface):
    # If config exists
    if os.path.exists(ORCH_INFO_FILE):
        with open(ORCH_INFO_FILE) as f:
            orch_info = yaml.load(f, Loader=yaml.FullLoader)

        # If orch server is already known
        if orch_info.get('orchestration_server', None) and orch_info.get('server_pub_key', None):
            logger.debug(f"found existing orchestration info: {orch_info.get('orchestration_server')}, {orch_info.get('server_pub_key', None)}")
            return orch_info
        # Orch server is not known, but config file is there (probably with ip info)

    logger.debug(f'Orchestration info not found, calling DAS')
    # Get Orchestration server info
    attestation_server_result = callhome(net_namespace=f"{interface}")
    # Save Orch info to file
    if attestation_server_result:
        with open(ORCH_INFO_FILE, 'w') as f:
                yaml.dump(attestation_server_result, f)
        return attestation_server_result
    
    # No info known and DAS is not responing correctly
    return False

def create_wireguard_interface(NETNS, config):
    logger.debug(f"trying to establish new tunnel on {NETNS}")
    WG_INTF_NAME = f"wg_{NETNS}"

    server = f"{config['ip']}:{config['orchestration_server'].split(':')[-1]}"
    logger.debug(f"Setting up connection to: {server}")
    subprocess.call(f'''
        ip netns exec {NETNS} ip link add dev {WG_INTF_NAME} type wireguard
        ip netns exec {NETNS} ip link set {WG_INTF_NAME} netns 1
        ip addr add dev {WG_INTF_NAME} {ORCHESTRATION_V4_PREFIX}.0.{config['device_id']}/32
        ip addr add dev {WG_INTF_NAME} {ORCHESTRATION_V6_PREFIX}{config['device_id']}/128
        wg set {WG_INTF_NAME} \
            listen-port 51820 \
            private-key /etc/wireguard/netcube01.private.key \
            peer {config['server_pub_key']} \
            persistent-keepalive 20 \
            allowed-ips {ORCHESTRATION_V4_PREFIX}.0.0/32,{ORCHESTRATION_V6_PREFIX}/128 \
            endpoint {server}
        ip link set up dev {WG_INTF_NAME}
        ip route add {ORCHESTRATION_V4_PREFIX}.0.0/32 dev {WG_INTF_NAME}
        ip route add {ORCHESTRATION_V6_PREFIX}/128 dev {WG_INTF_NAME}
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

if __name__ == '__main__':
    logger.debug("Starting callhome service")
    subprocess.run(f"/usr/bin/efibootmgr -O", shell=True)
    clean_up_wg_quick()
    
    while True:
        try:
            if not check_connection():
                for active_uplink in check_active_uplinks():
                    attestation_server_result = get_orch_info(active_uplink)
                    if attestation_server_result:
                        logger.debug("removing possible existing wireguard interfaces")
                        for wg_interface in get_existing_wireguard_interfaces():
                            logger.debug(f"removing {wg_interface}")
                            subprocess.run(f"ip link del {wg_interface}", shell=True)

                        create_wireguard_interface(active_uplink, attestation_server_result)
                        # if connection has been made, no need to try other namespaces
                        if check_connection():
                            logger.debug(f"Connection succesfull!")
                            break
                    else:
                        logger.debug(f"No right response from DAS")

        except Exception as e:
            set_led('red')
            logger.error(f"Fatal error occured during callhome: {traceback.format_exc()}")
            
        time.sleep(5)
