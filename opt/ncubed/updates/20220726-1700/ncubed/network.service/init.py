#!/bin/python3
import time
import json, yaml
import os, sys
import subprocess

import logging
from logging.handlers import RotatingFileHandler

#logging.basicConfig(filename='/var/log/ncubed.neworkd.log', level=logging.DEBUG)
# logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
#                     level=logging.DEBUG,
#                     datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger("ncubed nework daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s,Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(message)s', 
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.neworkd.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

ifdata = json.loads(subprocess.Popen(f"ip -j addr", stdout=subprocess.PIPE, shell=True).stdout.read())

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
    bridge vlan del dev {BRIDGENAME} vid 1 self
    bridge vlan del dev {BONDNAME} vid 1
    ip link set dev {BONDNAME} master {BRIDGENAME}
    bridge vlan add dev {BRIDGENAME} vid 3100-3299 self
    bridge vlan add dev {BONDNAME} vid 3100-3299
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

    # ORIGINAL_BRIDGELINKS=[L for L in json.loads(subprocess.run(f"bridge -j link", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout) if L.get('master') in [BRIDGE_I, BRIDGE_L2_I]]
    NETNAMESPACES=json.loads(subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout)
    if NETNS in [n.get('name')for n in NETNAMESPACES]:
        logger.info(f"Pre cleaning {NETNS}")
        subprocess.call(f'''
        kill $(ip netns pids {NETNS})
        ip netns delete {NETNS}
        ''', stdout=subprocess.PIPE, shell=True)

        # ip link del {BRIDGE_I}
        # ip link del {BRIDGE_L2_I}
        # Wait artificially to make sure everything is cleaned up before proceding
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
    ip link add {BRIDGE_L2_I} type bridge vlan_filtering 1
    bridge vlan del dev {BRIDGE_L2_I} vid 1 self
    ip link add {VETH_L2_I} type veth peer name {VETH_L2_E}
    ip link set {VETH_L2_I} master {BRIDGE_L2_I}
    ip link set {VETH_L2_E} netns {NETNS}
    ''', shell=True)
    
    logger.info(f"Configure namespace")
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
        # Falling back to DHCP request
        subprocess.call(f'''
        ip netns exec {NETNS} dhclient {BRIDGE_E} &
        ''', shell=True)

        # If all else fails set manually via fancy ARP script
        # TODO: Implement fancy arp script

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
# dhcp-hostsfile=/opt/ncubed/network.service/default.hostsfile
# addn-hosts=/opt/ncubed/network.service/default.addnhosts
    logger.info(f"start dnsmasq in namespace")
    subprocess.Popen(f'''
    ip netns exec {NETNS} /usr/sbin/dnsmasq --conf-file=/opt/ncubed/network.service/dnsmasq/{DOMAIN}.conf
    ''', shell=True)

    logger.info(f"Add bridges to correct firewalld zone")
    subprocess.Popen(f'''
    firewall-cmd --zone=trusted --change-interface={BRIDGE_I}
    firewall-cmd --zone=trusted --change-interface={BRIDGE_I} --permanent
    ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

    # logger.info(f"Reattaching vnet interfaces")
    # CURRENT_BRIDGELINKS=[L for L in json.loads(subprocess.run(f"bridge -j link", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout) if L.get('master') in [BRIDGE_I, BRIDGE_L2_I]]
    # MISSING_BRIDGELINKS=[ L for L in ORIGINAL_BRIDGELINKS if L not in CURRENT_BRIDGELINKS]
    # for BRIDGELINK in MISSING_BRIDGELINKS:
    #     subprocess.Popen(f'''
    #     ip link set {BRIDGELINK.get('ifname')} master {BRIDGELINK.get('master')}
    #     ''', shell=True)
    
    logger.info(f"Finished adding {NETNS}")
    logger.info(100*'#')

if __name__ == '__main__':
    with open('/opt/ncubed/config/network.yaml') as f:
        PORT_CONFIG = yaml.load(f, Loader=yaml.FullLoader)

    DEV_FAMILIY=subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG=[C for C in PORT_CONFIG if DEV_FAMILIY == C.get('family')]

    if DEV_CONFIG:
        for BOND in DEV_CONFIG[0]['portconfig']['BONDS']:
            create_trunkports(BOND['name'], BOND['interfaces'], BOND['bridgename'])

        BRIDGENAME = DEV_CONFIG[0]['portconfig']['INT'][0]
        for k,v in DEV_CONFIG[0]['portconfig']['WAN'].items():
            create_wanport(k,v, BRIDGENAME)

    while True:
        time.sleep(5)
