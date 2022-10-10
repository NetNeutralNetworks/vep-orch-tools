#!/bin/python3
import time
import json, yaml
import os, sys
import subprocess

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

def create_trunkports(BONDNAME, INTERFACES, BRIDGENAME):
    logger.info(f"Creating {BONDNAME}")

    subprocess.call(f'''
    ip link add {BONDNAME} type bond
    ip link set {BONDNAME} type bond miimon 100 mode active-backup
    ''', stdout=subprocess.PIPE, shell=True)

    for INTF in INTERFACES:
        logger.info(f"Adding {INTF}")
        subprocess.call(f'''
        ip link set {INTF} down
        ip link set {INTF} master {BONDNAME}
        ''', stdout=subprocess.PIPE, shell=True)

    subprocess.call(f'''
    ip link add {BRIDGENAME} type bridge vlan_filtering 1
    ip link set dev {BONDNAME} master {BRIDGENAME}
    bridge vlan add dev {BRIDGENAME} vid 1-4094 self
    bridge vlan add dev {BONDNAME} vid 1-4094
    bridge vlan add dev {BRIDGENAME} vid 1 pvid self untagged
    bridge vlan add dev {BONDNAME} vid 1 pvid untagged
    ''', stdout=subprocess.PIPE, shell=True)

    subprocess.call(f'''
    ip link set {BONDNAME} up
    ip link set dev {BRIDGENAME} up
    ''', stdout=subprocess.PIPE, shell=True)

    for INTF in INTERFACES:
        subprocess.call(f'''
        ip link set {INTF} up
        ''', stdout=subprocess.PIPE, shell=True)

    return BRIDGENAME

def create_wanport (ID, INTF, TRUNKBRIGE, TRANSIT_PREFIX=None):
    # set vars
    DOMAIN=f"WAN{ID}"
    TRANSIT_PREFIX=f"192.168.{ID}"
    EXTERNAL_NIC=INTF
    NETNS=f"ns_{DOMAIN}"
    BRIDGE_E=f"br-{DOMAIN}_e"
    BRIDGE_I=f"br-{DOMAIN}_nat_i"
    BRIDGE_L2_I=f"br-{DOMAIN}_l2_i"
    VETH_I=f"veth_{DOMAIN}_nat_i"
    VETH_E=f"veth_{DOMAIN}_nat_e"
    VETH_E_IP=f"{TRANSIT_PREFIX}.1/24"
    VETH_L2_I=f"veth_{DOMAIN}_l2_i"
    VETH_L2_E=f"veth_{DOMAIN}_l2_e"
    
    output = subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    if output:
        NETNAMESPACES=json.loads(output)
        if NETNS in [n.get('name')for n in NETNAMESPACES]:
            logger.info(f"Pre cleaning {NETNS}")
            subprocess.call(f'''
            kill $(ip netns pids {NETNS})
            ip netns delete {NETNS}
            ''', stdout=subprocess.PIPE, shell=True)

            time.sleep(0.1)
        else:
            logger.info(f"{NETNS} does not exist yet")

    logger.info(f"Creating {NETNS}")
    subprocess.call(f'''
    ip netns add {NETNS}
    ip netns exec {NETNS} sysctl -w net.ipv4.ip_forward=1
    ip link add {VETH_I} type veth peer name {VETH_E}
    ip link set {EXTERNAL_NIC} netns {NETNS}
    ip link set {VETH_E} netns {NETNS}
    ''', stdout=subprocess.PIPE, shell=True)

    logger.info(f"Creating nat bridge {BRIDGE_I}")
    subprocess.call(f'''
    ip link add {BRIDGE_I} type bridge vlan_filtering 1
    bridge vlan del dev {BRIDGE_I} vid 1 self
    ip link set {VETH_I} master {BRIDGE_I}
    ''', shell=True)
    
    logger.info(f"Creating l2 bridge {BRIDGE_L2_I}")
    subprocess.call(f'''
    ip link add {BRIDGE_L2_I} type bridge vlan_filtering 1 stp_state 1 max_age 15 priority 65535 forward_delay 2
    bridge vlan del dev {BRIDGE_L2_I} vid 1 self
    ip link add {VETH_L2_I} type veth peer name {VETH_L2_E}
    ip link set {VETH_L2_I} master {BRIDGE_L2_I}
    ip link set {VETH_L2_E} netns {NETNS}
    ''', shell=True)
    
    logger.info(f"Configure netns {NETNS}")
    subprocess.call(f'''
    ip netns exec {NETNS} ip link add {BRIDGE_E} type bridge
    ip netns exec {NETNS} ip link set {VETH_L2_E} master {BRIDGE_E}
    ip netns exec {NETNS} ip link set {EXTERNAL_NIC} master {BRIDGE_E}
    ip netns exec {NETNS} ip addr add {VETH_E_IP} dev {VETH_E}
    ip netns exec {NETNS} iptables -t nat -A POSTROUTING -o {BRIDGE_E} -j MASQUERADE
    ''', shell=True)

    logger.info(f"Bring devices up")
    subprocess.call(f'''
    ip link set dev {BRIDGE_I} up
    ip link set dev {BRIDGE_L2_I} up
    ip link set dev {VETH_I} up
    ip link set dev {VETH_L2_I} up
    ip netns exec {NETNS} ip link set dev {VETH_E} up
    ip netns exec {NETNS} ip link set dev {VETH_L2_E} up
    ip netns exec {NETNS} ip link set dev {EXTERNAL_NIC} up
    ip netns exec {NETNS} ip link set dev {BRIDGE_E} up
    ''', shell=True)

    logger.info(f"Create vlans and attach to bridges")
    subprocess.call(f'''
    ip link add link {TRUNKBRIGE} name {TRUNKBRIGE}.31{ID:02} type vlan id 31{ID:02}
    ip link add link {TRUNKBRIGE} name {TRUNKBRIGE}.32{ID:02} type vlan id 32{ID:02}
    ip link set {TRUNKBRIGE}.31{ID:02} master {BRIDGE_I}
    ip link set {TRUNKBRIGE}.32{ID:02} master {BRIDGE_L2_I}
    ip link set dev {TRUNKBRIGE}.31{ID:02} up
    ip link set dev {TRUNKBRIGE}.32{ID:02} up
    ''', shell=True)

    # get ip on outside nic
    logger.info("Setting ip's")

    # Checking configured IP's
    if os.path.exists(f'/opt/ncubed/config/{DOMAIN}.yaml'):
        with open(f'/opt/ncubed/config/{DOMAIN}.yaml') as f:
            wan_config = yaml.load(f, Loader=yaml.FullLoader)
        if wan_config.get('settings', {}).get('ip', None) and wan_config.get('settings', {}).get('gateway', None):
            subprocess.call(f'''
                ip netns exec {NETNS} ip addr add {wan_config.get('settings', {})['ip']} dev {BRIDGE_E}
                ip netns exec {NETNS} ip route add 0.0.0.0/0 via {wan_config.get('settings', {})['gateway']} dev {BRIDGE_E}
                ''', shell=True)
            logger.debug('Created default route')
        else:
            # Falling back to DHCP request
            subprocess.call(f'''
            ip netns exec {NETNS} dhclient {BRIDGE_E} &
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
                    if len([line for line in lines if 'DHCPDISCOVER' in line]) >= 3 or 'DHCPACK' in line:
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
interface={VETH_E}
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

if __name__ == '__main__':
    logger.info(f"Mounting default namespace as ROOT")
    subprocess.run(f'''
        touch /var/run/netns/ROOT
        mount --bind /proc/1/ns/net /var/run/netns/ROOT
    ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().lower()
    
    with open('/opt/ncubed/config/network.yaml') as f:
        PORT_CONFIG = yaml.load(f, Loader=yaml.FullLoader)

    DEV_FAMILIY=subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG=[C for C in PORT_CONFIG if DEV_FAMILIY == C.get('family')]

    if DEV_CONFIG:
        for BOND in DEV_CONFIG[0]['portconfig']['BONDS']:
            create_trunkports(BOND['name'], BOND['interfaces'], BOND['bridgename'])

        BRIDGENAME = DEV_CONFIG[0]['portconfig']['INT'][0]

        from threading import Thread
        threads = []
        for k,v in DEV_CONFIG[0]['portconfig']['WAN'].items():
            thread = Thread(target=create_wanport, args=(k,v, BRIDGENAME))
            thread.start()
            threads.append(thread)
            time.sleep(1)

    if os.path.exists(f'/opt/ncubed/config/vlan_bridges.yaml'):
        logger.info(f"found config for adding vlan bridges")
        with open(f'/opt/ncubed/config/vlan_bridges.yaml') as f:
            logger.info(f"Adding vlan bridges")
            vlan_bridges = yaml.load(f, Loader=yaml.FullLoader)
            for k, v in vlan_bridges.items():
                for vlan in v:
                    logger.info(f"Creating vlan bridge: {vlan} on trunk: {k}")
                    subprocess.run(f'''
                    ip link add name br-{vlan} type bridge
                    sudo ip link add link {k} name {k}.{vlan} type vlan id {vlan}
                    sudo ip link set up dev {k}.{vlan}
                    sudo ip link set {k}.{vlan} master br-{vlan}
                    sudo ip link set up dev br-{vlan}
                    ''', shell=True)

    try:
        subprocess.run(f"python3 /etc/opt/ncubed/custom_network.py", shell=True)
    except Exception as e:
        logger.warning(f"Error running custom network script: {e}")

    while True:
        time.sleep(5)
