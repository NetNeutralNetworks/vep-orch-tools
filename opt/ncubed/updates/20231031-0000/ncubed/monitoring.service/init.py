#!/bin/python3
import subprocess
import logging
import sys, os, json, yaml, datetime, traceback
from logging.handlers import RotatingFileHandler
from time import sleep

logger = logging.getLogger("ncubed monitoring daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s, Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(process)s: %(message)s',
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.monitoring.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

INTERNET_IPS = ["1.1.1.1", "8.8.8.8", "208.67.222.222"]
LOCAL_CONFIG_FOLDER = "/opt/ncubed/config/local"
GLOBAL_CONFIG_FOLDER = "/opt/ncubed/config/global"

STATUS_FILE = "/opt/ncubed/status.json"

ORCH_INFO_FILE = f'{LOCAL_CONFIG_FOLDER}/orch_info.yaml'

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

def get_active_uplinks():
    available_ns = []
    for NETNS in get_existing_netnamespaces():
        NETNS = NETNS.get('name')
        for ip in INTERNET_IPS:
            output = subprocess.run(f"ip netns exec {NETNS} ping -c 1 -W 1 {ip}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
            if "received, 0% packet loss" in output:
                available_ns.append(NETNS)
                break

    # logger.debug(f"Found the following net namespaces with active internet connections: {available_ns}")
    return available_ns

def get_orch_servers():
    try:
        with open(ORCH_INFO_FILE, 'r') as f:
            attestation = yaml.load(f)
            return attestation.get('result', {}).get('servers', [])
    except FileNotFoundError as e:
        return []
    
def orch_server_healthcheck(orch_server):
    if subprocess.run(f"ping {orch_server['ipv6_supernet']} -c 3 | grep -q 'bytes from'", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).returncode:
        logger.warning(f"No active tunnel to Orchestration server: {orch_server['orchestration_server']}")
        return 0
    else:
        return 1

if __name__ == '__main__':
    while True:
        try:
            active_namespaces = get_active_uplinks()
            orch_servers = get_orch_servers()
            orch_status = {}
            for orch_server in orch_servers:
                orch_status[orch_server['orchestration_server']] = orch_server_healthcheck(orch_server)
            if len(orch_servers) < 1:
                connection_status = "NO SERVER"
            elif all(value == 1 for value in orch_status.values()):
                connection_status = "FULL"
            elif any(value == 1 for value in orch_status.values()):
                connection_status = "PARTIAL"
            else:
                connection_status = "DISCONNECTED"
            
            status = {
                "active_namespaces": active_namespaces,
                "orchestration_servers": orch_status,
                "orch_status": connection_status,
            }
            if connection_status != "FULL":
                logger.info(status)
            with open(STATUS_FILE, 'w') as file:
                json.dump(status, file)
            sleep(4)
        except Exception as e:
            logger.critical(f"Crash in monitoringservice: {e}")
