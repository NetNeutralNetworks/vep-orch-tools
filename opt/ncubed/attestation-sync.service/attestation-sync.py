#!/bin/python3
import requests, time, json, os, sys, yaml, subprocess
from random import randint

import logging
from logging.handlers import RotatingFileHandler

INVENTORY_FILE='/opt/ncubed/ansible/inventories/hosts.yaml'
KNOWN_HOSTS_FILE='/etc/ssh/ssh_known_hosts'
LOG_FILE='/var/log/ncubed.attestation_sync.log'

DAS_SERVER = "https://ncubed-das.westeurope.cloudapp.azure.com"
TOKEN = "Hd4Ir161R8HygS8WVXmh4Rvoll1NgduHweVXGQRQREU"
PUB_KEY = "odz9hZVQO2maqpaFIG33Tv5ihBAD+1/SxI8Ko2FSFzM="

IPV4_PREFIX="100.71"
IPV6_PREFIX="fd71"

logger = logging.getLogger("ncubed attestation sync daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s,Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(message)s', 
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler(LOG_FILE, maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

def update_cockpit(host, action):
    dirname = '/etc/cockpit/machines.d/'
    filename = f'{dirname}00-autopop.json'

    if not os.path.isdir(dirname):
        return False

    if os.path.isfile(filename):
        with open(filename, "r") as file:
            data = json.load(file)
    else:
        data = json.loads('{}')

    if action=='add':
        entry = {host : {
                "visible" : True,
                "color" : f"rgb({randint(0, 255)}, {randint(0, 255)}, {randint(0, 255)})",
                "address" : host,
                "label" : host,
                "user" : "nc-admin"
                }}
        data.update(entry)
    elif action=='remove':
        if host in data:
            data.pop(host)
    else:
        return False

    with open(filename, "w+") as file:
        json.dump(data, file, indent=4, sort_keys=True)
    return True

def update_ansible(HOST, ACTION):
    try:
        with open(INVENTORY_FILE) as f:
            inventory = yaml.load(f, Loader=yaml.FullLoader)
        if ACTION=='add':
            inventory['all']['children']['BRANCH']['hosts'].update({HOST:{}})
            subprocess.call(f'''
                            sleep 10
                            ssh-keyscan -H {HOST} >> {KNOWN_HOSTS_FILE}
                            chmod 644 {KNOWN_HOSTS_FILE}
                            ''', stdout=subprocess.PIPE, shell=True)
        elif ACTION=='remove':
            inventory['all']['children']['BRANCH']['hosts'].pop(HOST)
            subprocess.call(f'''
                            ssh-keygen -f {KNOWN_HOSTS_FILE} -R {HOST}
                            chmod 644 {KNOWN_HOSTS_FILE}
                            ''', stdout=subprocess.PIPE, shell=True)
        with open(INVENTORY_FILE, 'w') as outfile:
            yaml.dump(inventory, outfile, default_flow_style=False)
        return 0
    except Exception as e:
        return e

def active_peers():
    return [k[4].split(',')[0].split('/')[0] for k in [j for j in [i.split('\t') for i in os.popen("wg show all dump").read().split('\n')] if len(j) == 9 and j[5].isdigit and int(j[5]) > time.time()-300 ]]

while True:
    data = {
        'token': TOKEN,
        'server_pub_key': PUB_KEY
    }
    r = requests.post(
        '{}/api/v1/serverapi/getclients'.format(DAS_SERVER),
        json=data)

    results = json.loads(r.text)

    for result in results['results']:
        IPV6 = "{}::{}/128".format(IPV6_PREFIX, result['device_id'])
        IPV4 = "{}.{}.{}/32".format(IPV4_PREFIX, result['device_id'] >> 8 & 255, result['device_id'] & 255)
        if not result['device_id']:
            continue
        if result['approved']:
            os.system("wg set wg0 peer {} allowed-ips {},{}".format(result['client_pub_key'], IPV4, IPV6))
            os.system("wg-quick save wg0")
            update_cockpit(IPV4.split('/')[0],"add")
            update_ansible(IPV6.split('/')[0],"add")
            logger.info(f"Added {IPV6.split('/')[0]} to inventory")
        else:
            os.system("wg set wg0 peer {} remove".format(result['client_pub_key']))
            os.system("wg-quick save wg0")
            update_cockpit(IPV4.split('/')[0],"remove")
            update_ansible(IPV6.split('/')[0],"remove")
            logger.info(f"Removed {IPV6.split('/')[0]} from inventory")

    time.sleep(10)
