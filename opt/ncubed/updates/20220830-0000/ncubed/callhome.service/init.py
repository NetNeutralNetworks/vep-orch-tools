#!/bin/python3
import time
import json, yaml, requests, re
import os, sys
import subprocess

import logging
from logging.handlers import RotatingFileHandler

ATTESTATION_SERVER="ncubed-das.westeurope.cloudapp.azure.com"
#ATTESTATION_SERVER="attestation.infra.ncubed.io"
WG_CONFIG_FILE="/etc/wireguard/wg0.conf"
WG_PRIVATE_KEY_FILE="/etc/wireguard/netcube01.private.key"
WG_PUBLIC_KEY_FILE="/etc/wireguard/netcube01.public.key"

#logging.basicConfig(filename='/var/log/ncubed.networkd.log', level=logging.DEBUG)
# logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
#                     level=logging.DEBUG,
#                     datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger("ncubed callhome")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s,Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(message)s', 
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.callhome.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

# Goes through all the namespaces and checks if the hardware interface is up
def check_active_uplinks():
    with open('/opt/ncubed/config/network.yaml') as f:
        PORT_CONFIG = yaml.load(f, Loader=yaml.FullLoader)

    DEV_FAMILIY=subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG=[C for C in PORT_CONFIG if DEV_FAMILIY == C.get('family')]
    available_ns = []
    for k,v in DEV_CONFIG[0]['portconfig']['WAN'].items():
        result = subprocess.run(f"ip netns exec ns_WAN{k} ip addr show {v} | grep -q 'state UP'", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).returncode
        logger.debug(f"checking namespace WAN{k}:  {result}")
        if result == 0:
            # 0 returncode means grep found the interface to be up
            available_ns.append(f"WAN{k}")
    logger.debug(f"Found the following active net namespaces: {available_ns}")
    return available_ns

def get_all_namespaces():
    with open('/opt/ncubed/config/network.yaml') as f:
        PORT_CONFIG = yaml.load(f, Loader=yaml.FullLoader)

    DEV_FAMILIY=subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG=[C for C in PORT_CONFIG if DEV_FAMILIY == C.get('family')]
    namespaces = []
    for k in DEV_CONFIG[0]['portconfig']['WAN']:
        namespaces.append(k)
    return namespaces

def callhome(net_namespace):
    if os.path.exists(WG_PRIVATE_KEY_FILE):
        logger.debug("Using existing key")
    else:
        logger.debug("Generating keys")
        subprocess.run(f"wg genkey | tee {WG_PRIVATE_KEY_FILE} | wg pubkey > {WG_PUBLIC_KEY_FILE}")
        subprocess.run(f"chmod 600 {WG_PRIVATE_KEY_FILE} {WG_PUBLIC_KEY_FILE}")

    servicetag=subprocess.run(f"dmidecode -s system-serial-number", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    logger.debug(f"Service tag: {servicetag}")
    with open(WG_PUBLIC_KEY_FILE, 'r') as f:
        pub_key = f.read()
        logger.debug(pub_key)
    body = f'{{"asset_tag": "{servicetag}","client_pub_key": "{pub_key.strip()}"}}'

    logger.debug(f"Calling attestation server from: {net_namespace}")

    # is needed because the resolve file keeps autocleaning?!?
    subprocess.run(f"echo nameserver 1.1.1.1 > /etc/resolv.conf", shell=True)
    attestation_result = subprocess.run(f"ip netns exec {net_namespace} curl -X POST 'https://{ATTESTATION_SERVER}/api/v1/clientapi/register' \
                            -H 'Content-Type: application/json' \
                            -d '{body}'", shell=True, capture_output=True, text=True).stdout
    logger.debug(f"Attestion response: {attestation_result}")
    try:
        orch_server=json.loads(attestation_result)
        resolve_result = subprocess.run(f"ip netns exec {net_namespace} host {orch_server['result']['orchestration_server'].split(':')[0]}", capture_output=True, shell=True).stdout.decode()
        ip = re.search(r'has address (.*)',resolve_result).group(1)
        orch_server['result'].update({'ip':ip})
        return orch_server
    except ValueError as e:
        return False
    

def check_connection():
    if subprocess.run(f"ping fd71:: -c 3 | grep -q 'bytes from'", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).returncode:
        logger.debug("Connection dead")
        return 0
    else:
        logger.debug("Connection alive")
        return 1

if __name__ == '__main__':
    logger.debug("Starting callhome service")
    subprocess.run(f"/usr/bin/efibootmgr -O", shell=True)

    subprocess.run(f"/opt/ncubed/bin/led blue", shell=True)
    while True:
        subprocess.run(f"echo nameserver 1.1.1.1 > /etc/resolv.conf", shell=True)

        if not check_connection():
            subprocess.run(f"/opt/ncubed/bin/led orange", shell=True)
            subprocess.run(f"wg-quick down wg0", shell=True)
            for interface in check_active_uplinks():
                logger.debug(f'Trying to find config for {interface}')
                
                # If config exists
                if os.path.exists(f'/opt/ncubed/config/{interface}.yaml'):
                    with open(f'/opt/ncubed/config/{interface}.yaml') as f:
                        wan_config = yaml.load(f, Loader=yaml.FullLoader)

                    # If orch server is already known
                    if wan_config.get('result', {}).get('orchestration_server', None) and wan_config.get('result', {}).get('server_pub_key', None):
                        logger.debug(f'found and using existing config')
                        attestation_server_result = wan_config
                    # Orch server is not known, but config file is there (probably with ip info)
                    else:
                        logger.debug(f'file found, but does not contain orch info, calling DAS')

                        # Get Orchestration server info
                        attestation_server_result = callhome(net_namespace=f"ns_{interface}")
                        # Config file exists and we want to keep it there in case it contains info.
                        if attestation_server_result:
                            attestation_server_result.update(wan_config)
                            with open(f'/opt/ncubed/config/{interface}.yaml', 'w') as f:
                                yaml.dump(attestation_server_result, f)
                
                # No config file exists                        
                else:
                    logger.debug(f'no existing config found, calling DAS...')
                    attestation_server_result = callhome(net_namespace=f"ns_{interface}")
                    # Save attestation result in config file
                    if attestation_server_result:
                        with open(f'/opt/ncubed/config/{interface}.yaml', 'w') as f:
                                yaml.dump(attestation_server_result, f)
                if attestation_server_result and attestation_server_result['message'] == 'success':
                    logger.debug("removing possible existing wireguard interfaces")
                    for namespace in get_all_namespaces():
                        subprocess.run(f"ip link del wg_WAN{namespace}", shell=True)

                
                    logger.debug(f"trying to establish new tunnel on {interface}")
                    result = attestation_server_result['result']
                
                    # is needed because the resolve file keeps autocleaning?!?
                    subprocess.run(f"echo nameserver 1.1.1.1 > /etc/resolv.conf", shell=True)
                    server = f"{result['ip']}:{result['orchestration_server'].split(':')[-1]}"
                    logger.debug(f"setting up connection to: {server}") 
                    subprocess.call(f'''
                    ip netns exec ns_{interface} ip link add dev wg_{interface} type wireguard
                    ip netns exec ns_{interface} ip link set wg_{interface} netns 1
                    ip addr add dev wg_{interface} 100.71.0.{result['device_id']}/32
                    ip addr add dev wg_{interface} fd71::{result['device_id']}/128
                    wg set wg_{interface} listen-port 51820 private-key /etc/wireguard/netcube01.private.key peer {result['server_pub_key']} persistent-keepalive 20 allowed-ips 100.71.0.0/32,fd71::/128 endpoint {server}
                    ip link set up dev wg_{interface}
                    ip route add 100.71.0.0/32 dev wg_{interface}
                    ip route add fd71::/128 dev wg_{interface}
                    ''', shell=True)
                    # if connection has been made, no need to try other namespaces
                    if check_connection():
                        logger.debug(f"Connection succesfull!")
                        break
            if not check_connection():
                logger.debug(f"No connection on WAN interfaces: Checking lagacy MGMT tunnel")
                subprocess.run(f"wg-quick up wg0", shell=True)
        else:
            subprocess.run(f"/opt/ncubed/bin/led purple", shell=True)
    
        time.sleep(10)
