#!/bin/python3
import time
import ipaddress
import re
import json, yaml
import os, sys
import subprocess
import netifaces
import logging
import multiprocessing
from logging.handlers import RotatingFileHandler
# custom libs
import detect_subnet
import systemd.daemon

logger = logging.getLogger("ncubed network daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s, Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(process)s: %(message)s',
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.networkd.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

ROOT_FOLDER = "/opt/ncubed"
LOCAL_CONFIG_FOLDER = f"{ROOT_FOLDER}/config/local"
GLOBAL_CONFIG_FOLDER = f"{ROOT_FOLDER}/config/global"
LOCAL_SYSTEM_CONFIG_FILE = f'{LOCAL_CONFIG_FOLDER}/system.yaml'
CUSTOM_NETWORK_CCONFIG_SCRIPT_FILE = "/etc/opt/ncubed/custom_network.py"
DEFAULT_DNS_SERVERS=["1.1.1.1","8.8.8.8","9.9.9.9"]

def check_ip_configured(NETNS, BRIDGE_E):
    ips_configured = subprocess.run(f'''ip -4 -n {NETNS} -br addr show dev {BRIDGE_E}''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().split()[2:]
    return ips_configured

def create_interface(NETNS, INTF, TYPE):
    interface_list = subprocess.run(f'''ip netns exec {NETNS} ip -j -br link''',stdout=subprocess.PIPE, shell=True).stdout.decode()
    if interface_list:
        existing_interfaces = [i.get('ifname') for i in json.loads(interface_list)]
        if TYPE=='veth' and f"{INTF}_i" not in existing_interfaces and f"{INTF}_e" not in existing_interfaces:
            logger.info(f"Creating {INTF} pair of type {TYPE} in netns {NETNS}")            
            subprocess.run(f'''
            ip netns exec {NETNS} ip link add dev {INTF}_i type {TYPE} peer name {INTF}_e
            ''', shell=True)
        elif TYPE=='vlan' and INTF not in existing_interfaces:
            logger.info(f"Creating {INTF} of type {TYPE} in netns {NETNS}")
            TRUNKBRIGE,VID = INTF.split('.')
            subprocess.run(f'''
            ip link add link {TRUNKBRIGE} name {INTF} type {TYPE} id {VID}
            ''', shell=True)
        elif TYPE!='veth' and INTF not in existing_interfaces:
            logger.info(f"Creating {INTF} of type {TYPE} in netns {NETNS}")
            subprocess.run(f'''
            ip netns exec {NETNS} ip link add dev {INTF} type {TYPE}
            ''', shell=True)
        else:
            logger.info(f"Found existing {INTF}")

def create_trunkport(BONDNAME, INTERFACES, BRIDGENAME, BONDTYPE):
    # delete bond if type has changed
    if os.path.exists(f'/proc/net/bonding/{BONDNAME}'):
        if BONDTYPE not in subprocess.run(f'cat /proc/net/bonding/{BONDNAME} | grep "Bonding Mode: "',shell=True, stdout=subprocess.PIPE).stdout.decode():
            subprocess.run(f'ip link del {BONDNAME}',shell=True)
    
    if not subprocess.run(f'ip -j link show dev {BRIDGENAME}',shell=True, stdout=subprocess.PIPE).stdout.decode():
        create_interface('ROOT', BRIDGENAME, 'bridge')

    if not os.path.exists(f'/proc/net/bonding/{BONDNAME}'):
        create_interface('ROOT', BONDNAME, 'bond')
        if BONDTYPE in [0, 'balance-rr']:      # Requires static Etherchannel enabled (not LACP-negotiated) 
            subprocess.run(f'ip link set {BONDNAME} type bond mode 0',shell=True)
        elif BONDTYPE in [1, 'active-backup']: # Requires autonomous ports
            subprocess.run(f'ip link set {BONDNAME} type bond mode 1 miimon 100',shell=True)
        elif BONDTYPE in [2, 'balance-xor']:   # Requires static Etherchannel enabled (not LACP-negotiated)
            subprocess.run(f'ip link set {BONDNAME} type bond mode 2',shell=True)
        elif BONDTYPE in [3, 'broadcast']:     # Requires static Etherchannel enabled (not LACP-negotiated)
            subprocess.run(f'ip link set {BONDNAME} type bond mode 3',shell=True)
        elif BONDTYPE in [4, '802.3ad']:       # Requires LACP-negotiated Etherchannel enabled
            subprocess.run(f'ip link set {BONDNAME} type bond mode 4 lacp_rate fast',shell=True)
        elif BONDTYPE in [5, 'balance-tlb']:   # Requires autonomous ports
            subprocess.run(f'ip link set {BONDNAME} type bond mode 5',shell=True)
        elif BONDTYPE in [6, 'balance-alb']:   # Requires autonomous ports
            subprocess.run(f'ip link set {BONDNAME} type bond mode 6',shell=True)

    subprocess.run(f'''
        ip link set dev {BRIDGENAME} type bridge vlan_filtering 1 stp_state 0 priority 65535
        ip link set dev {BONDNAME} master {BRIDGENAME}
        bridge vlan add dev {BONDNAME} vid 1-4094
        bridge vlan add dev {BONDNAME} vid 1 pvid untagged
        bridge vlan add dev {BRIDGENAME} vid 1-4094 self
        bridge vlan add dev {BRIDGENAME} vid 1 pvid self untagged
        ''', shell=True)

    for i, INTF in enumerate(INTERFACES):
        interface_config = json.loads(subprocess.run(f'''ip -j link show {INTF}''',stdout=subprocess.PIPE, shell=True).stdout.decode())
        if interface_config[0].get('master', '') == BONDNAME:
            logger.info(f"{INTF} already added to bond {BONDNAME}")
            continue
        logger.info(f"Adding {INTF} to bond {BONDNAME}")
        subprocess.run(f'''
            ip link set {INTF} down
            ip link set {INTF} master {BONDNAME}
            ''', shell=True)
        
        # if BONDTYPE in [1, 'active-backup'] and i == 0:
        #     subprocess.run(f'ip link set dev {BONDNAME} type bond primary {INTF}',shell=True)

    for INTF in INTERFACES + [BONDNAME, BRIDGENAME]:
        subprocess.run(f'ip link set dev {INTF} up', shell=True)

def get_local_system_config():
    # load local list
    if os.path.exists(LOCAL_SYSTEM_CONFIG_FILE):
        with open(LOCAL_SYSTEM_CONFIG_FILE) as f:
            logger.info(f"Found config for adding globaly defined vlan bridges")
            return yaml.load(f, Loader=yaml.FullLoader)
    else:
        return {}
    
def start_dnsmasq(DOMAIN, NETNS, VETH_NAT, TRANSIT_PREFIX):
    logger.info(f"start dnsmasq in namespace {DOMAIN}")
    resolve_file = f'/etc/netns/{NETNS}/resolv.conf'
    
    if not os.path.exists(resolve_file):
        set_dns_servers(NETNS,[]) 
    
    subprocess.run(f'''
    ip netns exec {NETNS} /usr/sbin/dnsmasq --pid-file=/run/dnsmasq_ns_{DOMAIN}.pid \
                                            --except-interface=lo \
                                            --interface={VETH_NAT}_e \
                                            --bind-dynamic \
                                            --dhcp-range={TRANSIT_PREFIX}.100,{TRANSIT_PREFIX}.199,255.255.255.0 \
                                            --dhcp-no-override \
                                            --dhcp-authoritative \
                                            --dhcp-lease-max=20 \
                                            --resolv-file={resolve_file} \
                                            --log-facility=/var/log/ncubed-dnsmasq.log
    ''', shell=True)
    logger.info(f"Finished wanport cluster configuration")

def create_clustered_wanport (status,ID, INTF, TRUNKBRIGE, TRANSIT_PREFIX=None):
    # set vars
    LOCAL_SYSTEM_CONFIG = get_local_system_config()
    if LOCAL_SYSTEM_CONFIG:
        # validate cluster values 
        pass
    else:
        exit()

    CLUSTER_MEMBER_ID = LOCAL_SYSTEM_CONFIG.get('cluster').get('member')
    if not TRANSIT_PREFIX:
        TRANSIT_PREFIX=f"100.{100+CLUSTER_MEMBER_ID}.{ID}"

    NETNS=f"ns_WAN{ID}"
    BRIDGE_E=f"br-WAN{ID}_e"
    VID = f"{CLUSTER_MEMBER_ID}{ID:02}"
    DOMAIN=f"WAN{VID}"
    BRIDGE_NAT_I=f"br-{DOMAIN}_nat_i"
    BRIDGE_L2_I=f"br-WAN{CLUSTER_MEMBER_ID}{ID+50:02}_l2_i"
    VETH_NAT=f"_{DOMAIN}_nat"
    VETH_NAT_E_IP=f"{TRANSIT_PREFIX}.1/24"
    VETH_L2=f"_{DOMAIN}_l2"

    create_l3_circuit(NETNS, VETH_NAT, BRIDGE_NAT_I, VETH_NAT_E_IP)
    start_dnsmasq(DOMAIN, NETNS, VETH_NAT, TRANSIT_PREFIX)
    create_l2_circuit(NETNS, VETH_L2, BRIDGE_L2_I, BRIDGE_E)

    # nat vlans x00-x49, l2 vlans x50-x99
    create_vlan_interface(f"{TRUNKBRIGE}.{VID}", BRIDGE_NAT_I)
    VID = f"{CLUSTER_MEMBER_ID}{ID+50:02}"
    create_vlan_interface(f"{TRUNKBRIGE}.{VID}", BRIDGE_L2_I)

    # create all cluster member bridges and vlans 
    all_members = list(range(1,LOCAL_SYSTEM_CONFIG.get('cluster').get('size')+1))
    for CID in [member for member in all_members if member != CLUSTER_MEMBER_ID]:
        try:
            for DATA in [[f"{CID}{ID:02}",f"br-WAN{CID}{ID:02}_nat_i"],
                         [f"{CID}{ID+50:02}",f"br-WAN{CID}{ID+50:02}_l2_i"]
                        ]:
                VID = DATA[0]
                MASTERBRIDGE = DATA[1]

                create_wan_bridge(MASTERBRIDGE)
                subprocess.run(f'''ip link set dev {MASTERBRIDGE} up''', shell=True)
                create_vlan_interface(f"{TRUNKBRIGE}.{VID}", MASTERBRIDGE)
                
        except Exception as e:
            logger.error(e)

def create_vlan_interface(vlan_interface, bridge):
    logger.info(f"Creating vlan interface: {vlan_interface} with master {bridge}")
    create_interface('ROOT',f"{vlan_interface}",'vlan')
    subprocess.call(f'''
    ip link set dev {vlan_interface} master {bridge}
    ip link set dev {vlan_interface} up
    ''', shell=True)
   
def create_wan_bridge(bridge):
    create_interface('ROOT',bridge,'bridge')
    logger.info(f"Configuring WAN bridge")
    subprocess.run(f'''
    #sysctl -w net.ipv6.conf.{bridge}.disable_ipv6=1
    ip link set dev {bridge} type bridge vlan_filtering 1 stp_state 0 priority 65535
    bridge vlan del dev {bridge} vid 1 self
    ''', shell=True)
    
def veth_ok(bridge, veth):
    try:
        for intf in json.loads(subprocess.run(f"ip -j link show type veth master {bridge}", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()):
            ifname = intf.get('ifname')
            if ifname != veth:
                subprocess.run(f"ip link del {ifname}", shell=True)
        return True
    except:
        return False

def create_wan_circuit(netns, veth, bridge):
    create_wan_bridge(bridge)
    if veth_ok(bridge, f"{veth}_i"):
        create_interface('ROOT',veth,'veth')
        subprocess.run(f'''
        ip link set {veth}_i master {bridge}
        ip link set {veth}_e netns {netns}
        ''', shell=True)

def create_l2_circuit(netns, veth, bridge, external_bridge):
    create_wan_circuit(netns, veth, bridge)
    subprocess.run(f'''
    ip netns exec {netns} ip link set {veth}_e master {external_bridge}
    ''', shell=True)

def create_l3_circuit(netns, veth, bridge, external_ip):
    create_wan_circuit(netns, veth, bridge)
    subprocess.run(f'''
    ip netns exec {netns} ip addr add {external_ip} dev {veth}_e
    ''', shell=True)

def configure_external_bridge(netns, bridge, nic):
    logger.info(f"Configure SNAT in netns {netns}")
    create_interface(netns, bridge, 'bridge')
    subprocess.call(f'''
    ip netns exec {netns} ip link set {nic} master {bridge}
    ip netns exec {netns} iptables -t nat -A POSTROUTING -o {bridge} -j MASQUERADE
    ip netns exec {netns} ip link set dev {nic} up
    ''', shell=True)

def create_netns(netns, nic):
    existing_netnamespaces_json = subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    if existing_netnamespaces_json:
        existing_netnamespaces=json.loads(existing_netnamespaces_json)
        if netns not in [NETNAMESPACE.get('name') for NETNAMESPACE in existing_netnamespaces]:
            logger.info(f"Creating {netns}")
            subprocess.run(f'''
            ip netns add {netns}
            ip netns exec {netns} sysctl -w net.ipv4.ip_forward=1
            ''', stdout=subprocess.PIPE, shell=True)

    if nic in netifaces.interfaces():
        subprocess.run(f'''ip link set {nic} netns {netns}''', shell=True)        

def create_wanport (status,ID, INTF, TRUNKBRIGE, TRANSIT_PREFIX=None):
    # set vars
    DOMAIN=f"WAN{ID}"
    if not TRANSIT_PREFIX:
        TRANSIT_PREFIX=f"192.168.{ID}"
    else:
        TRANSIT_PREFIX='.'.join(TRANSIT_PREFIX.split('.')[:2]) + f".{ID}"
    EXTERNAL_NIC=INTF
    NETNS=f"ns_{DOMAIN}"
    BRIDGE_E=f"br-{DOMAIN}_e"
    BRIDGE_NAT_I=f"br-{DOMAIN}_nat_i"
    BRIDGE_L2_I=f"br-{DOMAIN}_l2_i"
    VETH_NAT=f"_{DOMAIN}_nat"
    VETH_NAT_E_IP=f"{TRANSIT_PREFIX}.1/24"
    VETH_L2=f"_{DOMAIN}_l2"

    LOCAL_SYSTEM_CONFIG = get_local_system_config()

    create_netns(NETNS, EXTERNAL_NIC)
    configure_external_bridge(NETNS, BRIDGE_E, EXTERNAL_NIC)
    
    create_l3_circuit(NETNS, VETH_NAT, BRIDGE_NAT_I, VETH_NAT_E_IP)
    create_l2_circuit(NETNS, VETH_L2, BRIDGE_L2_I, BRIDGE_E)

    if LOCAL_SYSTEM_CONFIG:
        create_clustered_wanport(status,ID, INTF, TRUNKBRIGE, TRANSIT_PREFIX=None)

    start_dnsmasq(DOMAIN, NETNS, VETH_NAT, TRANSIT_PREFIX)

    # signal thread init has finished
    status.set()

    logger.info(100*'#')
    logger.info(f"Starting external interface deamon {NETNS}")

    monitor_interface(DOMAIN, EXTERNAL_NIC)

def check_interface_is_up(NETNS, INTF):
    if 'up' in subprocess.run(f'''ip -n {NETNS} -br addr show dev {INTF}''',
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              shell=True).stdout.decode().lower():
        return True
    else:
        return False

def log_netns_ip_addr(NETNS):
    logger.info(subprocess.run(f''' printf "\n\n"
        ip netns exec {NETNS} ip -br addr
    ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode())

def get_yaml_config(file):
     if os.path.exists(file):
         with open(file) as f:
             wan_config = yaml.load(f, Loader=yaml.FullLoader)
     else:
         wan_config = {}
     return wan_config

def set_dns_servers(NETNS,dns_servers):
    resolve_file_path = f"/etc/netns/{NETNS}"
    resolve_file = f"{resolve_file_path}/resolv.conf"

    if not os.path.exists(resolve_file_path):
        os.makedirs(resolve_file_path)

    if os.path.exists(resolve_file):
        with open(resolve_file, 'r') as f:
            configured_dns_servers = f.read()
    else:
        configured_dns_servers=None

    dns_servers = ''.join([f"nameserver {s}\n" for s in dns_servers])

    if dns_servers != configured_dns_servers:
        with open(resolve_file, 'w') as f:
            f.write(dns_servers)
            logger.info(f'Configured dns servers in netnamespace {NETNS}')

def get_dhcp_leases():
    DHCP_LEASES_FILE = '/var/lib/dhcp/dhclient.leases'
    if os.path.exists(DHCP_LEASES_FILE):
        with open(DHCP_LEASES_FILE, 'r') as f: 
            return f.read().replace('  ','').replace('"','').split('lease {\n')[1:]
    else:
        return []

def get_dhcp_dns_servers(domain):
    nameservers = []
    for lease in get_dhcp_leases():
        if domain in lease:
            dns_as_string = [ip.split(',') for ip in re.findall('domain-name-servers (.*);',lease)]
            nameservers += [str(ipaddress.ip_address(ip)) for ip in dns_as_string[0]]
    return nameservers

def get_dhcp_ip_leases(domain):
    ip_leases = []
    for lease in get_dhcp_leases():
        if domain in lease:
            ip_leases.append(str(ipaddress.ip_interface('/'.join([''.join(i) for i in re.findall('fixed-address (.*);|subnet-mask (.*);', lease)]))))
    return ip_leases

def if_up(DOMAIN, EXTERNAL_NIC, NETNS, BRIDGE_E):
    logger.info(f'External interface is up, configuring {BRIDGE_E}')
    subprocess.run(f'''
        ip link set dev _{DOMAIN}_nat_i up
        ip link set dev _{DOMAIN}_l2_i up
        ip link set dev br-{DOMAIN}_nat_i up
        ip link set dev br-{DOMAIN}_l2_i up
        ip netns exec {NETNS} ip link set dev {BRIDGE_E} up
        ip netns exec {NETNS} ip link set dev _{DOMAIN}_nat_e up
        ip netns exec {NETNS} ip link set dev _{DOMAIN}_l2_e up
    ''', shell=True)
    configure_wan_ip(DOMAIN, EXTERNAL_NIC)
    
def if_down(DOMAIN, NETNS, BRIDGE_E):
    logger.info(f'External interface is down, unconfiguring {BRIDGE_E}')
    subprocess.run(f'''
        ip netns exec {NETNS} ip route flush dev {BRIDGE_E}
        ip netns exec {NETNS} ip addr flush dev {BRIDGE_E}
        ip netns exec {NETNS} ip link set dev {BRIDGE_E} down
        ip netns exec {NETNS} ip link set dev _{DOMAIN}_nat_e down
        ip netns exec {NETNS} ip link set dev _{DOMAIN}_l2_e down
    ''', shell=True)
    
    subprocess.run(f'''
        pgrep -f "dhclient {BRIDGE_E}" | xargs kill
        pgrep -f "tcpdump -i {BRIDGE_E}" | xargs kill
    ''', shell=True)
    
    set_dns_servers(NETNS,[])  

def monitor_interface(DOMAIN, EXTERNAL_NIC):
    NETNS=f"ns_{DOMAIN}"
    BRIDGE_E=f"br-{DOMAIN}_e"
    logger.info(f"Monitoring {EXTERNAL_NIC} in {NETNS}")

    if check_interface_is_up(NETNS,EXTERNAL_NIC):
        if_up(DOMAIN, EXTERNAL_NIC, NETNS, BRIDGE_E)
    else:
        if_down(DOMAIN, NETNS, BRIDGE_E)

    with subprocess.Popen(f"ip -o -n {NETNS} monitor link dev {EXTERNAL_NIC}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as mon:
        for line in mon.stdout:
            if "state UP group" in line and check_interface_is_up(NETNS,EXTERNAL_NIC):
                if_up(DOMAIN, EXTERNAL_NIC, NETNS, BRIDGE_E)
            elif "state DOWN group" in line and not check_interface_is_up(NETNS,EXTERNAL_NIC):
                if_down(DOMAIN, NETNS, BRIDGE_E)
            else:
                continue
            # interface flapping dampening
            time.sleep(2)

def configure_wan_ip(DOMAIN, EXTERNAL_NIC):
    try:
        # get ip on outside nic
        logger.info(f"Setting ip's in {DOMAIN}")
        NETNS=f"ns_{DOMAIN}"
        BRIDGE_E=f"br-{DOMAIN}_e"

        # set external brigde up
        wan_config = get_yaml_config(f'{LOCAL_CONFIG_FOLDER}/{DOMAIN}.yaml')
        configured_dns_servers = wan_config.get('settings', {}).get('dnsservers', [])

        if wan_config.get('settings', {}).get('ip', None) and wan_config.get('settings', {}).get('gateway', None):
            if wan_config.get('settings', {})['ip'] not in check_ip_configured(NETNS, BRIDGE_E):
                subprocess.call(f'''
                    ip netns exec {NETNS} ip addr add {wan_config.get('settings', {})['ip']} dev {BRIDGE_E}
                    ip netns exec {NETNS} ip route add 0.0.0.0/0 via {wan_config.get('settings', {})['gateway']} dev {BRIDGE_E}
                ''', shell=True)
                log_netns_ip_addr(NETNS)

        # check if no ip is configured and when there is check if that has been issued by dhcp
        if not check_ip_configured(NETNS, BRIDGE_E) or any(True for ip in get_dhcp_ip_leases(DOMAIN) if ip in check_ip_configured(NETNS, BRIDGE_E)):
            logger.info(f'Trying DHCP on {BRIDGE_E}')
            if len(subprocess.run(f'''pgrep -f "dhclient {BRIDGE_E}"    ''', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode().split('\n')) < 3:                
                p = subprocess.Popen(f"ip netns exec {NETNS} dhclient {BRIDGE_E} -d", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True)
                lines = []
                for line in p.stdout:
                    lines.append(line)
                    if len([line for line in lines if 'DHCPDISCOVER' in line]) >= 5:
                        p.terminate()
                        break
                    
                    if 'bound to' in line:           
                        break                        
                
            if not configured_dns_servers:
                configured_dns_servers = get_dhcp_dns_servers(DOMAIN)

        if not check_ip_configured(NETNS, BRIDGE_E):
            logger.info(f'no DHCP detected trying auto detect script on {BRIDGE_E}')
            detect_subnet.configure_wan_interface(DOMAIN)

        # configure dns servers
        if check_ip_configured(NETNS, BRIDGE_E):
            if configured_dns_servers:
                set_dns_servers(NETNS, configured_dns_servers)
            else:
                set_dns_servers(NETNS, DEFAULT_DNS_SERVERS)
            
    except Exception as e:
        logger.error(e)

def mergeDictionary(dict_1, dict_2):
    dict_3 = {**dict_1, **dict_2}
    for key, value in dict_3.items():
        if key in dict_1 and key in dict_2:
            if type(dict_3[key]) == str:
                dict_3[key] = [value , dict_1[key]]
            elif type(dict_3[key]) == list:
                dict_3[key] += dict_1[key]
            elif type(dict_3[key]) == dict:
                dict_3[key] = mergeDictionary(value , dict_1[key])
    return dict_3

def load_vlan_bridges_from_config(FILENAME):
    if os.path.exists(FILENAME):
        with open(FILENAME) as f:
            logger.info(f"found defined vlan bridges in {FILENAME}")
            return yaml.load(f, Loader=yaml.FullLoader)
    else:
        return {}

def create_vlan_bridges():
    local_vlan_bridges = load_vlan_bridges_from_config(f'{LOCAL_CONFIG_FOLDER}/vlan_bridges.yaml')
    global_vlan_bridges = load_vlan_bridges_from_config(f'{GLOBAL_CONFIG_FOLDER}/vlan_bridges.yaml')

    # merge vlan interace lists
    vlan_bridges = mergeDictionary(global_vlan_bridges, local_vlan_bridges)
    configured_vlan_interfaces = [f"{k}.{i.get('vid')}" for k,v in vlan_bridges.items() for i in v.get('vlans')]
    existing_vlan_interfaces = [interface for interface in netifaces.interfaces() if '.' in interface]
    bridge_reserved_ranges = {k:[i for r in v.get('reserved',{}) for i in range(*map(int,r.get('range','').split('-')))] for k,v in vlan_bridges.items()}

    # remove vlan bridges and interfaces not in list
    for existing_vlan_interface in existing_vlan_interfaces:
        try:
            bridge, vlan = existing_vlan_interface.split('.')
            if existing_vlan_interface not in configured_vlan_interfaces:
                logger.info(f"Removing vlan interface: {bridge}.{vlan} and master br-{vlan}")
                subprocess.run(f'''
                    ip link del link dev {existing_vlan_interface}
                    ip link del link dev br-{vlan}
                ''', shell=True)
        except Exception as e:
            logger.error(e)

    # add vlan bridges and interfaces
    for vlan_interface in configured_vlan_interfaces:
        try:
            bridge, vlan = vlan_interface.split('.')
            if int(vlan) in bridge_reserved_ranges[bridge]:
                logger.info(f"Ignoring reserved vlan interface: {bridge}.{vlan}")
            elif vlan_interface not in existing_vlan_interfaces:
                logger.info(f"Creating vlan interface: {bridge}.{vlan} with master br-{vlan}")
                subprocess.run(f'''
                    ip link add name br-{vlan} type bridge
                    ip link add link {bridge} name {vlan_interface} type vlan id {vlan}
                    ip link set dev {vlan_interface} master br-{vlan}
                    ip link set dev {vlan_interface} up
                    ip link set dev br-{vlan} up
                ''', shell=True)
            else:
                logger.info(f"Ignoring existing vlan interface: {bridge}.{vlan} with master br-{vlan}")
        except Exception as e:
            logger.error(e)

def mount_default_namespace_as_root():
    ROOT_NS_FILE="/run/netns/ROOT"
    while not os.path.exists(ROOT_NS_FILE):
        logger.info(f"Mounting default namespace as ROOT")
        subprocess.run(f'''
            touch {ROOT_NS_FILE}
            mount --bind /proc/1/ns/net {ROOT_NS_FILE}
        ''', shell=True)
        time.sleep(0.5)

def get_port_configs():
    try:
        if not os.path.exists(f'{LOCAL_CONFIG_FOLDER}/network.yaml'):
            subprocess.run(f'''cp {GLOBAL_CONFIG_FOLDER}/network.yaml {LOCAL_CONFIG_FOLDER}/network.yaml''', shell=True)

        with open(f'{LOCAL_CONFIG_FOLDER}/network.yaml') as f:
            PORT_CONFIGS = yaml.load(f, Loader=yaml.FullLoader)
        return PORT_CONFIGS
    except Exception as e:
        logger.error(f"Unable to read: {LOCAL_CONFIG_FOLDER}/network.yaml")
        sys.exit(1)

if __name__ == '__main__':
    mount_default_namespace_as_root()
    PORT_CONFIGS = get_port_configs()

    DEV_FAMILIY = subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG = [PORT_CONFIG for PORT_CONFIG in PORT_CONFIGS if PORT_CONFIG.get('family') == DEV_FAMILIY]

    if DEV_CONFIG:
        for BOND in DEV_CONFIG[0]['portconfig']['BONDS']:
            create_trunkport(BOND['name'], BOND['interfaces'], BOND['bridgename'], BOND.get('type','active-backup'))

        create_vlan_bridges()

        TRUNKBRIGE = DEV_CONFIG[0]['portconfig']['INT'][0]
        TRANSIT_PREFIX=DEV_CONFIG[0].get('internal_prefix',None)

        processes = []
        
        for k,v in DEV_CONFIG[0]['portconfig']['WAN'].items():
            status = multiprocessing.Event()
            process = multiprocessing.Process(name=f'Setup WAN{k}', target=create_wanport, args=(status,k,v, TRUNKBRIGE, TRANSIT_PREFIX))
            process.start()
            processes.append([process,status])

        # wait for all threads to have finished initial setup
        while not all([ s.is_set() for t,s in processes ]):
            time.sleep(1)

    try:
        # this is only as a last resort, or for during testing
        if os.path.exists(CUSTOM_NETWORK_CCONFIG_SCRIPT_FILE):
            subprocess.run(f"python3 {CUSTOM_NETWORK_CCONFIG_SCRIPT_FILE}", shell=True)
    except Exception as e:
        logger.warning(f"Error running custom network script: {e}")

    # notify systemd daemon is ready
    systemd.daemon.notify('READY=1')
