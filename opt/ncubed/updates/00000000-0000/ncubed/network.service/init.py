#!/bin/python3
import time
import json, yaml
import os, sys
import subprocess
import netifaces
import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("ncubed network daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s,Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(message)s', 
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.networkd.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

ifdata = json.loads(subprocess.Popen(f"ip -j addr", stdout=subprocess.PIPE, shell=True).stdout.read())

import detect_subnet

def check_ip_configured(WANINTF):
    ip_configured = subprocess.run(f'''ip -4 -n ns_{WANINTF} -br addr show dev br-{WANINTF}_e''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    return ip_configured

def create_interface(NETNS, INTF, TYPE):
    interface_list = subprocess.run(f'''ip netns exec {NETNS} ip -j -br link''',stdout=subprocess.PIPE, shell=True).stdout.decode()
    if interface_list:
        existing_interfaces = [i.get('ifname') for i in json.loads(interface_list)]        
        if TYPE=='veth' and f"{INTF}_i" not in existing_interfaces and f"{INTF}_e" not in existing_interfaces:
            logger.info(f"Creating {INTF} pair of type {TYPE} in netns {NETNS}")
            subprocess.run(f'''
            ip netns exec {NETNS} ip link add dev {INTF}_i type {TYPE} peer name {INTF}_e
            ''', shell=True)  
        elif TYPE!='veth' and INTF not in existing_interfaces:
            logger.info(f"Creating {INTF} of type {TYPE} in netns {NETNS}")
            subprocess.run(f'''
            ip netns exec {NETNS} ip link add dev {INTF} type {TYPE}
            ''', shell=True)      
        else:
            logger.info(f"Found existing {INTF}")

def create_trunkports(BONDNAME, INTERFACES, BRIDGENAME):
    
    for INTF in [{'netns':'ROOT','name':BONDNAME,'type':'bond'},
                 {'netns':'ROOT','name':BRIDGENAME,'type':'bridge'}]:
        create_interface(INTF.get('netns'),INTF.get('name'),INTF.get('type'))

    subprocess.run(f'''
    ip link set {BONDNAME} type bond miimon 100 mode active-backup
    ip link set dev {BRIDGENAME} type bridge vlan_filtering 1
    ip link set dev {BONDNAME} master {BRIDGENAME}
    bridge vlan add dev {BONDNAME} vid 1-4094
    bridge vlan add dev {BONDNAME} vid 1 pvid untagged
    bridge vlan add dev {BRIDGENAME} vid 1-4094 self
    bridge vlan add dev {BRIDGENAME} vid 1 pvid self untagged
    ''', shell=True)
    
    for INTF in INTERFACES:
        logger.info(f"Adding {INTF}")
        subprocess.run(f'''
        ip link set {INTF} down
        ip link set {INTF} master {BONDNAME}
        ''', shell=True)

    for INTF in INTERFACES + [BONDNAME, BRIDGENAME]:
        subprocess.run(f'''
        ip link set dev {INTF} up
        ''', shell=True)

def create_wanport (ID, INTF, TRUNKBRIGE, TRANSIT_PREFIX=None):
    # set vars
    DOMAIN=f"WAN{ID}"
    TRANSIT_PREFIX=f"192.168.{ID}"
    EXTERNAL_NIC=INTF
    NETNS=f"ns_{DOMAIN}"
    BRIDGE_L2_E=f"br-{DOMAIN}_e"
    BRIDGE_NAT_I=f"br-{DOMAIN}_nat_i"
    BRIDGE_L2_I=f"br-{DOMAIN}_l2_i"
    VETH_NAT=f"veth_{DOMAIN}_nat"
    VETH_NAT_E_IP=f"{TRANSIT_PREFIX}.1/24"
    VETH_L2=f"veth_{DOMAIN}_l2"

    existing_netnamespaces_json = subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    if existing_netnamespaces_json:
        existing_netnamespaces=json.loads(existing_netnamespaces_json)
        if NETNS not in [NETNAMESPACE.get('name') for NETNAMESPACE in existing_netnamespaces]:
            logger.info(f"Creating {NETNS}")
            subprocess.run(f'''
            ip netns add {NETNS}
            ip netns exec {NETNS} sysctl -w net.ipv4.ip_forward=1
            ip link set {EXTERNAL_NIC} netns {NETNS}
            ''', stdout=subprocess.PIPE, shell=True)

    existing_interfaces = [interface for interface in netifaces.interfaces()]

    for INTF in [{'netns':'ROOT','name':BRIDGE_NAT_I,'type':'bridge'},
                 {'netns':'ROOT','name':BRIDGE_L2_I,'type':'bridge'},
                 {'netns':'ROOT','name':VETH_NAT,'type':'veth'},
                 {'netns':'ROOT','name':VETH_L2,'type':'veth'},
                 {'netns':NETNS,'name':BRIDGE_L2_E,'type':'bridge'}
                 ]:
        create_interface(INTF.get('netns'),INTF.get('name'),INTF.get('type'))

    logger.info(f"Configuring WAN nat circuit")
    subprocess.run(f'''
    ip link set dev {BRIDGE_NAT_I} type bridge vlan_filtering 1
    bridge vlan del dev {BRIDGE_NAT_I} vid 1 self
    ''', shell=True)
    subprocess.run(f'''
    ip link set {VETH_NAT}_i master {BRIDGE_NAT_I}
    ip link set {VETH_NAT}_e netns {NETNS}
    ip netns exec {NETNS} ip addr add {VETH_NAT_E_IP} dev {VETH_NAT}_e
    ''', shell=True)
    
    logger.info(f"Configuring WAN l2 circuit")
    subprocess.run(f'''
    ip link set {BRIDGE_L2_I} type bridge vlan_filtering 1 stp_state 1 priority 65535
    bridge vlan del dev {BRIDGE_L2_I} vid 1 self
    ip link set {VETH_L2}_i master {BRIDGE_L2_I}
    ip link set {VETH_L2}_e netns {NETNS}
    ip netns exec {NETNS} ip link set {VETH_L2}_e master {BRIDGE_L2_E}
    ''', shell=True)
    
    logger.info(f"Configure SNAT in netns {NETNS}")
    subprocess.call(f'''
    ip netns exec {NETNS} ip link set {EXTERNAL_NIC} master {BRIDGE_L2_E}
    ip netns exec {NETNS} iptables -t nat -A POSTROUTING -o {BRIDGE_L2_E} -j MASQUERADE
    ''', shell=True)

    logger.info(f"Set devices up")
    subprocess.call(f'''
    ip link set dev {BRIDGE_NAT_I} up
    ip link set dev {BRIDGE_L2_I} up
    ip link set dev {VETH_NAT}_i up
    ip link set dev {VETH_L2}_i up
    ip netns exec {NETNS} ip link set dev {VETH_NAT}_e up
    ip netns exec {NETNS} ip link set dev {VETH_L2}_e up
    ip netns exec {NETNS} ip link set dev {EXTERNAL_NIC} up
    ip netns exec {NETNS} ip link set dev {BRIDGE_L2_E} up
    ''', shell=True)


    # get ip on outside nic
    logger.info("Setting ip's")

    # Checking configured IP's
    if os.path.exists(f'/opt/ncubed/config/{DOMAIN}.yaml'):
        with open(f'/opt/ncubed/config/{DOMAIN}.yaml') as f:
            wan_config = yaml.load(f, Loader=yaml.FullLoader)
        if wan_config.get('settings', {}).get('ip', None) and wan_config.get('settings', {}).get('gateway', None):
            subprocess.call(f'''
                ip netns exec {NETNS} ip addr add {wan_config.get('settings', {})['ip']} dev {BRIDGE_L2_E}
                ip netns exec {NETNS} ip route add 0.0.0.0/0 via {wan_config.get('settings', {})['gateway']} dev {BRIDGE_L2_E}
                ''', shell=True)
            logger.debug('Created default route')
        else:
            # Falling back to DHCP request
            subprocess.call(f'''
            ip netns exec {NETNS} dhclient {BRIDGE_L2_E} &
            ''', shell=True)
    else:
        WANINTF = DOMAIN
        while not check_ip_configured(WANINTF):
            if not 'up' in subprocess.run(f'''ip -n ns_{WANINTF} -br addr show dev {EXTERNAL_NIC}''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().lower():
                time.sleep(5)
                continue

            logger.info(f'Trying DHCP on br-{WANINTF}_e')
            with subprocess.Popen(f"ip netns exec ns_{WANINTF} dhclient br-{WANINTF}_e -d", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as p:
                lines = []
                for line in p.stdout:
                    lines.append(line)
                    #print(line, end='')
                    if len([line for line in lines if 'DHCPDISCOVER' in line]) >= 5 or 'DHCPACK' in line:
                        time.sleep(0.2)
                        p.terminate()
                        break
            
            if not check_ip_configured(WANINTF):
                logger.info(f'no DHCP detected trying auto detect script on br-{WANINTF}_e')
                detect_subnet.configure_wan_interface(WANINTF)

    logger.info(subprocess.run(f''' printf "\n\n"
    ip netns exec {NETNS} ip -br addr
    ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode())

    with open(f'/opt/ncubed/network.service/dnsmasq/{DOMAIN}.conf', 'w') as f:
        f.write(f'''\
strict-order
user=libvirt-dnsmasq
pid-file=/opt/ncubed/network.service/dnsmasq/{DOMAIN}.pid
except-interface=lo
bind-dynamic
interface={VETH_NAT}_e
dhcp-range={TRANSIT_PREFIX}.100,{TRANSIT_PREFIX}.199,255.255.255.0
dhcp-no-override
dhcp-authoritative
dhcp-lease-max=253
server=8.8.8.8
server=9.9.9.9
''')
    logger.info(f"start dnsmasq in namespace")
    subprocess.Popen(f'''
    ip netns exec {NETNS} /usr/sbin/dnsmasq --conf-file=/opt/ncubed/network.service/dnsmasq/{DOMAIN}.conf
    ''', shell=True)
    logger.info(f"Finished adding {NETNS}")
    logger.info(100*'#')

from copy import deepcopy



def create_vlan_bridges():
    CONFIG_FOLDER = f'/opt/ncubed/config'
    VLAN_BRIDGES_LOCAL_FILE = f'{CONFIG_FOLDER}/vlan_bridges.yaml'
    VLAN_BRIDGES_GLOBAL_FILE = f'{CONFIG_FOLDER}/vlan_bridges_global.yaml'
    local_vlan_bridges = {}
    global_vlan_bridges = {}
    
    # load global list
    if os.path.exists(VLAN_BRIDGES_LOCAL_FILE):
        with open(VLAN_BRIDGES_LOCAL_FILE) as f:
            logger.info(f"found config for adding localy defined vlan bridges")
            local_vlan_bridges = yaml.load(f, Loader=yaml.FullLoader)
    # load local list                
    if os.path.exists(VLAN_BRIDGES_GLOBAL_FILE):
        with open(VLAN_BRIDGES_GLOBAL_FILE) as f:
            logger.info(f"found config for adding globaly defined vlan bridges")
            global_vlan_bridges = yaml.load(f, Loader=yaml.FullLoader)
    
    # merge vlan interace lists
    vlan_interfaces = set([f"{k}.{i}" for k,v in global_vlan_bridges.items() for i in v] + 
                          [f"{k}.{i}" for k,v in local_vlan_bridges.items() for i in v])

    existing_interfaces = [interface for interface in netifaces.interfaces() if '.' in interface]
    
    # remove vlan bridges and interfaces not in list
    for existing_vlan_interface in existing_interfaces:
        try:
            bridge, vlan = existing_vlan_interface.split('.')
            if existing_vlan_interface not in vlan_interfaces:                
                logger.info(f"Removing vlan bridge: {vlan} on trunk: {bridge}")
                subprocess.run(f'''
                    ip link del link dev {vlan_interface}
                    ip link del link dev br-{vlan}
                ''', shell=True)
        except Exception as e:
            logger.error(e)

    # add vlan bridges and interfaces
    for vlan_interface in vlan_interfaces:
        try:
            bridge, vlan = vlan_interface.split('.')
            if vlan_interface not in existing_interfaces:                
                logger.info(f"Creating vlan bridge: {vlan} on trunk: {bridge}")
                subprocess.run(f'''
                    ip link add name br-{vlan} type bridge
                    ip link add link {bridge} name {vlan_interface} type vlan id {vlan}
                    ip link set dev {vlan_interface} master br-{vlan}
                    ip link set dev {vlan_interface} up
                    ip link set dev br-{vlan} up
                ''', shell=True)
            else:
                logger.info(f"vlan bridge: {vlan} on trunk: {bridge} allready present")
        except Exception as e:
            logger.error(e)

if __name__ == '__main__':
    logger.info(f"Mounting default namespace as ROOT")
    subprocess.run(f'''
        touch /var/run/netns/ROOT
        mount --bind /proc/1/ns/net /var/run/netns/ROOT
    ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().lower()
    
    with open('/opt/ncubed/config/network.yaml') as f:
        PORT_CONFIGS = yaml.load(f, Loader=yaml.FullLoader)

    DEV_FAMILIY = subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG = [PORT_CONFIG for PORT_CONFIG in PORT_CONFIGS if PORT_CONFIG.get('family') == DEV_FAMILIY]

    if DEV_CONFIG:
        for BOND in DEV_CONFIG[0]['portconfig']['BONDS']:
            create_trunkports(BOND['name'], BOND['interfaces'], BOND['bridgename'])

        create_vlan_bridges()

        TRUNKBRIGE = DEV_CONFIG[0]['portconfig']['INT'][0]

        from threading import Thread
        threads = []
        for k,v in DEV_CONFIG[0]['portconfig']['WAN'].items():
            thread = Thread(target=create_wanport, args=(k,v, TRUNKBRIGE))
            thread.start()
            threads.append(thread)
            time.sleep(1)

    try:
        # this is only as a last resort, or for during testing
        CUSTOM_NETWORK_CCONFIG_SCRIPT_FILE = "/etc/opt/ncubed/custom_network.py"
        if os.path.exists(CUSTOM_NETWORK_CCONFIG_SCRIPT_FILE):
            subprocess.run(f"python3 {CUSTOM_NETWORK_CCONFIG_SCRIPT_FILE}", shell=True)
    except Exception as e:
        logger.warning(f"Error running custom network script: {e}")

    while True:
        time.sleep(5)
