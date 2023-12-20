#!/bin/python3
from collections import defaultdict
import requests, time, json, os, sys, yaml, subprocess, ipaddress
from random import randint

import logging
from logging.handlers import RotatingFileHandler

from pathlib import Path
import subprocess

configfolder = Path("/etc/ncubed/config")
configfolder.mkdir(exist_ok=True)
configfile = configfolder.joinpath("orchestration.yaml")
WG_PRIV_KEY_FILE = '/etc/wireguard/priv.key'
WG_PUB_KEY_FILE = '/etc/wireguard/pub.key'
WG_INTERFACE = 'wg0'

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

def update_in_nested_dict(data, keys, value):
    if not keys:
        return value
    
    key = keys[0]
    
    if key not in data:
        if len(keys) == 1:
            data[key] = value
        else:
            data[key] = {}
    
    data[key] = update_in_nested_dict(data[key], keys[1:], value)
    
    return data

def update_ansible(HOST, ACTION, meta_data = {}):
    KNOWN_HOSTS_FILE = config.get('KNOWN_HOSTS_FILE')
    INVENTORY_FILE = config.get('INVENTORY_FILE')
    _inventory_directory = '/'.join(INVENTORY_FILE.split('/')[:-1])
    if not os.path.exists(INVENTORY_FILE):
        logger = logging.getLogger("ncubed attestation sync daemon")
        logger.info("Ansible inventory file does not exists, creating new one")
        Path(_inventory_directory).mkdir(parents=True, exist_ok=True)
        with open(INVENTORY_FILE, 'x'):
            pass

    try:
        with open(INVENTORY_FILE) as f:
            inventory = yaml.load(f, Loader=yaml.FullLoader)
            logger = logging.getLogger("ncubed attestation sync daemon")
            logger.debug(f"Current inventory: {inventory}")
            if not inventory:
                inventory = {}
                logger.info("Ansible inventory file is empty, filling with template")
                inventory = update_in_nested_dict(inventory, ['all','children','BRANCH','hosts'], {})
                logger.info(f"new inventory: {inventory}")
            
        if ACTION=='add':
            if inventory['all']['children']['BRANCH']['hosts'].get(HOST):
                inventory['all']['children']['BRANCH']['hosts'][HOST].update(meta_data)
            else:
                inventory['all']['children']['BRANCH']['hosts'][HOST] = meta_data
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
        logger = logging.getLogger("ncubed attestation sync daemon")
        logger.error(e, exc_info=True)

def update_wg():
    # validate wireguard interface is configured and running
    subprocess.run(f"""
    ip -n UNTRUST link add dev {WG_INTERFACE} type wireguard
    ip netns exec UNTRUST ip link set {WG_INTERFACE} netns 1
    ip address add dev {WG_INTERFACE} {config.get('IPV4_PREFIX')}.0.0/16
    ip address add dev {WG_INTERFACE} {config.get('IPV6_SUPERNET')}
    wg set {WG_INTERFACE} listen-port 51820 private-key {WG_PRIV_KEY_FILE}
    ip link set up dev {WG_INTERFACE}
    """, stdout=subprocess.PIPE, shell=True)

    

    activepeers = subprocess.run(f"wg show wg0 allowed-ips", stdout=subprocess.PIPE, shell=True).stdout.decode().strip('\n').split('\n')
    activepeers = [[i.split(' ') for i in p.split('\t')] for p in activepeers]

    IPV6_PREFIX_NEW = config.get('IPV6_SUPERNET').replace('/64','')
    if activepeers != [[['']]]:
        for peer in activepeers:
            IPV6_PREFIX_OLD = str(ipaddress.ip_interface(peer[1][1].replace('/128','/64')).network.network_address)
            if IPV6_PREFIX_NEW is not IPV6_PREFIX_OLD:
                # update_ansible(IPV6_PREFIX_OLD, 'remove')
                # update_ansible(peer[1][1], 'add', {'wg_public_key': peer[0][0]})
                subprocess.run(f"""
                            wg set wg0 peer {peer[0][0]} allowed-ips {peer[1][0]},{peer[1][1].replace(IPV6_PREFIX_OLD, IPV6_PREFIX_NEW)}
                            """, stdout=subprocess.PIPE, shell=True)
                

def active_peers():
    return [k[4].split(',')[0].split('/')[0] for k in [j for j in [i.split('\t') for i in os.popen("wg show all dump").read().split('\n')] if len(j) == 9 and j[5].isdigit and int(j[5]) > time.time()-300 ]]

# Used in migrating from wg-quick -> Code can be removed after it has run on all Orch servers
def migrate_from_wg_quick():
    logger = logging.getLogger("ncubed attestation sync daemon")
    logger.info("Checking to see if we need to migrate away from wg-quick")
    wg_quick_status = subprocess.run(f"systemctl status wg-quick@wg0", stdout=subprocess.PIPE, shell=True).stdout.decode()
    if 'masked' in wg_quick_status or 'inactive' in wg_quick_status:
        logger.info("wg-quick service is not being used, either masked of never activated")
        # Already disabled so we are running the new version. Nothing to do here
        return
    
    logger.info("Migrating from wg-quick to ansible inventory")
    activepeers = subprocess.run(f"wg show wg0 allowed-ips", stdout=subprocess.PIPE, shell=True).stdout.decode().strip('\n').split('\n')
    activepeers = [[i.split(' ') for i in p.split('\t')] for p in activepeers]
    for peer in activepeers:
        key = peer[0][0]
        allowed_ips = peer[1]
        if allowed_ips == ['(none)']:
            # this tunnel is no longer used?
            logger.debug(f"Not adding {key}, because it has no allowed ips")
            continue
        ipv6 = allowed_ips[1].split('/')[0]
        logger.debug(f"adding {key} to ansible inventory")
        update_ansible(HOST=ipv6, ACTION='add', meta_data={'wg_public_key': key, 'allowed_ips': allowed_ips})
    logger.info("All hosts added to ansible inventory")

    logger.info("Masking old wg-quick service")
    subprocess.run(f"systemctl mask wg-quick@wg0", stdout=subprocess.PIPE, shell=True)

    logger.info("Removing old wg0 interface")
    subprocess.run(f"ip link del wg0", stdout=subprocess.PIPE, shell=True)

    logger.info("Migration done!")


def load_connections_from_inventory():
    logger = logging.getLogger("ncubed attestation sync daemon")
    logger.info("Loading ansible inventory")
    INVENTORY_FILE = config.get('INVENTORY_FILE')
    if not os.path.exists(INVENTORY_FILE):
        logger.info("Ansible inventory file does not exists, cannot setup previous connections")
        return
      
    try:
        with open(INVENTORY_FILE) as f:
            inventory = yaml.load(f, Loader=yaml.FullLoader)
        logger = logging.getLogger("ncubed attestation sync daemon")
        logger.debug(f"Current inventory: {inventory}")
        if not inventory:
            logger.info("Ansible inventory file is empty, filling with template")
            return
        for peer, meta_data in inventory['all']['children']['BRANCH']['hosts'].items():
            if meta_data.get('wg_public_key') and meta_data.get('allowed_ips'):
                os.system("wg set wg0 peer {} allowed-ips {}".format(meta_data['wg_public_key'], ",".join(meta_data['allowed_ips'])))
    except Exception as e:
        logger.warning(f"Error initializing previous known connections: {e}", exc_info=True)

        
logger = logging.getLogger("ncubed attestation sync daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s,Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(message)s', 
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler(config.get('LOG_FILE'), maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

## Start of logic

# Migrate from wg-quick to custom wg init
migrate_from_wg_quick()

# Convert old prefixes to new prefixes
# Setup wg interface in UNTRUST namespace
update_wg()

# Load wg connections from ansible inventory
load_connections_from_inventory()

# get wireguard public key
with open(WG_PUB_KEY_FILE, 'r') as f:
    PUB_KEY=f.readline().replace('\n','')

# TODO: Do a full sync with attestation server

while True:
    data = {
        'token': config.get('TOKEN'),
        'server_pub_key': PUB_KEY,
        'ipv6_supernet': config.get('IPV6_SUPERNET','fd71:ffff::/64')
    }
    r = requests.post(
        '{}/api/v1/serverapi/getclients'.format(config.get('DAS_SERVER')),
        json=data)

    results = json.loads(r.text)
    
    if 'results' in results
        for result in results['results']:
        IPV6 = "{}{}/128".format(config.get('IPV6_SUPERNET').split('/')[0], result['device_id'])
        IPV4 = "{}.{}.{}/32".format(config.get('IPV4_PREFIX'), result['device_id'] >> 8 & 255, result['device_id'] & 255)
        if not result['device_id']:
            continue
        if result['approved']:
            os.system("wg set wg0 peer {} allowed-ips {},{}".format(result['client_pub_key'], IPV4, IPV6))
            update_ansible(IPV6.split('/')[0],"add", {'wg_public_key': result['client_pub_key'], 'allowed_ips': [IPV4, IPV6]})
            logger.info(f"Added {IPV6.split('/')[0]} to inventory")
        else:
            os.system("wg set wg0 peer {} remove".format(result['client_pub_key']))
            update_ansible(IPV6.split('/')[0],"remove")
            logger.info(f"Removed {IPV6.split('/')[0]} from inventory")
    else:
        logger.debug(results)

    time.sleep(10)
