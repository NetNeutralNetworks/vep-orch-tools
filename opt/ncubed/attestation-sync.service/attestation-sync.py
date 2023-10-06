#!/bin/python3
import requests, time, json, os, sys, yaml, subprocess
from random import randint

import logging
from logging.handlers import RotatingFileHandler

from pathlib import Path
import subprocess

configfile = Path("/etc/ncubed/config/orchestration.yaml")
WG_PRIV_KEY_FILE = '/etc/wireguard/priv.key'
WG_PUB_KEY_FILE = '/etc/wireguard/pub.key'
WG_QUICK_FILE = '/etc/wireguard/wg0.conf'

# get config
with open(configfile, 'r') as f:
    config = yaml.safe_load(f)

# generate wireguard keys
subprocess.run(f'''
               if [ ! -f {WG_PRIV_KEY_FILE} ]; then
                 wg genkey > {WG_PRIV_KEY_FILE}
               fi
               if [ ! -f {WG_PUB_KEY_FILE} ]; then
                 cat {WG_PRIV_KEY_FILE} | wg pubkey > {WG_PUB_KEY_FILE}
               fi
               ''', stdout=subprocess.PIPE, shell=True)

# validate wg-quick is configured and running
if not Path(WG_QUICK_FILE).is_file():
    with open("/etc/wireguard/wg0.conf", 'r') as f:
        with open(WG_PRIV_KEY_FILE, 'r') as privkey_f:
            f.write(f"""
                    [Interface]
                    Address = {config.get('IPV4_PREFIX')}.0.0/16
                    Address = {config.get('IPV6_PREFIX')}::/64
                    ListenPort = 51820
                    PrivateKey = {privkey_f.readline()}
                    """)

subprocess.run('systemctl start wg-quick@wg0.service', stdout=subprocess.PIPE, shell=True)

# get wireguard public key
with open(WG_PUB_KEY_FILE, 'r') as f:
    PUB_KEY=f.readline().replace('\n','')

logger = logging.getLogger("ncubed attestation sync daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s,Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(message)s', 
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler(config.get('LOG_FILE'), maxBytes=100000, backupCount=5)
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
    KNOWN_HOSTS_FILE = config.get('KNOWN_HOSTS_FILE')
    INVENTORY_FILE = config.get('INVENTORY_FILE')
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
        'token': config.get('TOKEN'),
        'server_pub_key': PUB_KEY
    }
    r = requests.post(
        '{}/api/v1/serverapi/getclients'.format(config.get('DAS_SERVER')),
        json=data)

    results = json.loads(r.text)

    for result in results['results']:
        IPV6 = "{}::{}/128".format(config.get('IPV6_PREFIX'), result['device_id'])
        IPV4 = "{}.{}.{}/32".format(config.get('IPV4_PREFIX'), result['device_id'] >> 8 & 255, result['device_id'] & 255)
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
