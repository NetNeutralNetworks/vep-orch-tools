#!/bin/python3
import time
import json, yaml
import os, sys
import subprocess
import netifaces
import logging
import multiprocessing
from logging.handlers import RotatingFileHandler
# custom libs
import detect_subnet

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


def check_ip_configured(WANINTF):
    ips_configured = subprocess.run(f'''ip -4 -n ns_{WANINTF} -br addr show dev br-{WANINTF}_e''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().split()[2:]
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

def create_trunkports(BONDNAME, INTERFACES, BRIDGENAME):

    for INTF in [{'netns':'ROOT','name':BONDNAME,'type':'bond'},
                 {'netns':'ROOT','name':BRIDGENAME,'type':'bridge'}]:
        create_interface(INTF.get('netns'),INTF.get('name'),INTF.get('type'))

    subprocess.run(f'''
    ip link set {BONDNAME} type bond miimon 100 mode active-backup
    ip link set dev {BRIDGENAME} type bridge vlan_filtering 1 stp_state 0 priority 65535
    ip link set dev {BONDNAME} master {BRIDGENAME}
    bridge vlan add dev {BONDNAME} vid 1-4094
    bridge vlan add dev {BONDNAME} vid 1 pvid untagged
    bridge vlan add dev {BRIDGENAME} vid 1-4094 self
    bridge vlan add dev {BRIDGENAME} vid 1 pvid self untagged
    ''', shell=True)

    for INTF in INTERFACES:
        logger.info(f"Adding {INTF} to bond {BONDNAME}")
        subprocess.run(f'''
        ip link set {INTF} down
        ip link set {INTF} master {BONDNAME}
        ''', shell=True)

    for INTF in INTERFACES + [BONDNAME, BRIDGENAME]:
        subprocess.run(f'''
        ip link set dev {INTF} up
        ''', shell=True)

def get_local_system_config():
    # load local list
    if os.path.exists(LOCAL_SYSTEM_CONFIG_FILE):
        with open(LOCAL_SYSTEM_CONFIG_FILE) as f:
            logger.info(f"Found config for adding globaly defined vlan bridges")
            return yaml.load(f, Loader=yaml.FullLoader)
    else:
        return {}

def create_wanport (status,ID, INTF, TRUNKBRIGE, TRANSIT_PREFIX=None):
    # set vars
    DOMAIN=f"WAN{ID}"
    if not TRANSIT_PREFIX:
        TRANSIT_PREFIX=f"192.168.{ID}"
    EXTERNAL_NIC=INTF
    NETNS=f"ns_{DOMAIN}"
    BRIDGE_E=f"br-{DOMAIN}_e"
    BRIDGE_NAT_I=f"br-{DOMAIN}_nat_i"
    BRIDGE_L2_I=f"br-{DOMAIN}_l2_i"
    VETH_NAT=f"veth_{DOMAIN}_nat"
    VETH_NAT_E_IP=f"{TRANSIT_PREFIX}.1/24"
    VETH_L2=f"veth_{DOMAIN}_l2"

    LOCAL_SYSTEM_CONFIG = get_local_system_config()

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
                 {'netns':NETNS,'name':BRIDGE_E,'type':'bridge'}
                 ]:
        create_interface(INTF.get('netns'),INTF.get('name'),INTF.get('type'))

    logger.info(f"Configuring WAN nat circuit")
    subprocess.run(f'''
    ip link set dev {BRIDGE_NAT_I} type bridge vlan_filtering 1 stp_state 0 priority 65535
    bridge vlan del dev {BRIDGE_NAT_I} vid 1 self
    ''', shell=True)
    subprocess.run(f'''
    ip link set {VETH_NAT}_i master {BRIDGE_NAT_I}
    ip link set {VETH_NAT}_e netns {NETNS}
    ip netns exec {NETNS} ip addr add {VETH_NAT_E_IP} dev {VETH_NAT}_e
    ''', shell=True)

    logger.info(f"Configuring WAN l2 circuit")
    subprocess.run(f'''
    ip link set {BRIDGE_L2_I} type bridge vlan_filtering 1 stp_state 0 priority 65535
    bridge vlan del dev {BRIDGE_L2_I} vid 1 self
    ip link set {VETH_L2}_i master {BRIDGE_L2_I}
    ip link set {VETH_L2}_e netns {NETNS}
    ip netns exec {NETNS} ip link set {VETH_L2}_e master {BRIDGE_E}
    ''', shell=True)

    logger.info(f"Configure SNAT in netns {NETNS}")
    subprocess.call(f'''
    ip netns exec {NETNS} ip link set {EXTERNAL_NIC} master {BRIDGE_E}
    ip netns exec {NETNS} iptables -t nat -A POSTROUTING -o {BRIDGE_E} -j MASQUERADE
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
    ip netns exec {NETNS} ip link set dev {BRIDGE_E} up
    ''', shell=True)

    if LOCAL_SYSTEM_CONFIG:
        CLUSTER_MEMBER_ID = LOCAL_SYSTEM_CONFIG.get('cluster').get('member')
        VID = f"{CLUSTER_MEMBER_ID}{ID:02}"
        BRIDGE_NAT_I = BRIDGE_NAT_I.format(ID)
        logger.info(f"Creating vlan interface: {TRUNKBRIGE}.{VID} with master {BRIDGE_NAT_I}")
        create_interface('ROOT',f"{TRUNKBRIGE}.{VID}",'vlan')
        subprocess.call(f'''
        ip link set {TRUNKBRIGE}.{VID} master {BRIDGE_NAT_I}
        ip link set dev {TRUNKBRIGE}.{VID} up
        ''', shell=True)

        VID = f"{CLUSTER_MEMBER_ID}{ID+50:02}"
        logger.info(f"Creating vlan interface: {TRUNKBRIGE}.{VID} with master {BRIDGE_L2_I}")
        create_interface('ROOT',f"{TRUNKBRIGE}.{VID}",'vlan')
        subprocess.call(f'''
        ip link set {TRUNKBRIGE}.{VID} master {BRIDGE_L2_I}
        ip link set dev {TRUNKBRIGE}.{VID} up
        ''', shell=True)

        all_members = list(range(1,LOCAL_SYSTEM_CONFIG.get('cluster').get('size')+1))
        for CID in [member for member in all_members if member != CLUSTER_MEMBER_ID]:
            try:
                for DATA in [[f"{CID}{ID:02}",f"br-WAN{CID}{ID:02}_nat_i"],
                             [f"{CID}{ID+50:02}",f"br-WAN{CID}{ID+50:02}_l2_i"]
                             ]:
                    VID = DATA[0]
                    MASTERBRIDGE=DATA[1]
                    logger.info(f"Creating vlan interface: {TRUNKBRIGE}.{VID} with master {MASTERBRIDGE}")
                    create_interface('ROOT',MASTERBRIDGE,'bridge')
                    create_interface('ROOT',f"{TRUNKBRIGE}.{VID}",'vlan')

                    subprocess.run(f'''
                        #sysctl -w net.ipv6.conf.{MASTERBRIDGE}.disable_ipv6=1
                        ip link set {MASTERBRIDGE} type bridge vlan_filtering 1 stp_state 0 priority 65535
                        bridge vlan del dev {MASTERBRIDGE} vid 1 self

                        ip link set dev {TRUNKBRIGE}.{VID} master {MASTERBRIDGE}
                        ip link set dev {TRUNKBRIGE}.{VID} up
                        ip link set dev {MASTERBRIDGE} up
                    ''', shell=True)
            except Exception as e:
                logger.error(e)

    logger.info(f"start dnsmasq in namespace {DOMAIN}")
    subprocess.run(f'''
    ip netns exec {NETNS} /usr/sbin/dnsmasq --user=libvirt-dnsmasq \
                                            --except-interface=lo \
                                            --interface={VETH_NAT}_e \
                                            --bind-interfaces \
                                            --dhcp-range={TRANSIT_PREFIX}.100,{TRANSIT_PREFIX}.199,255.255.255.0 \
                                            --dhcp-no-override \
                                            --dhcp-authoritative \
                                            --dhcp-lease-max=20 \
                                            --log-facility=/var/log/ncubed-dnsmasq.log
    ''', shell=True)
    logger.info(f"Finished adding {NETNS}")

    # signal thread init has finished
    status.set()

    logger.info(100*'#')
    logger.info(f"Starting external interface deamon {NETNS}")

    configure_wan_ip(DOMAIN, EXTERNAL_NIC)

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
        configured_dns_servers=''

    dns_servers = ''.join([f"nameserver {s}\n" for s in dns_servers])

    if dns_servers != configured_dns_servers:
        with open(resolve_file, 'w') as f:
            f.write(dns_servers)
            logger.info(f'Configured dns servers in netnamespace {NETNS}')

def configure_wan_ip(DOMAIN, EXTERNAL_NIC):
    # get ip on outside nic
    logger.info(f"Setting ip's in {DOMAIN}")
    NETNS=f"ns_{DOMAIN}"
    BRIDGE_E=f"br-{DOMAIN}_e"

    # Checking configured IP's
    while True:
        try:
            # check if intf is up and conifgure ip from config file
            if check_interface_is_up(NETNS,EXTERNAL_NIC):
                # set external brigde up
                subprocess.call(f'''ip netns exec {NETNS} ip link set dev {BRIDGE_E} up''', shell=True)

                wan_config = get_yaml_config(f'{LOCAL_CONFIG_FOLDER}/{DOMAIN}.yaml')
                dns_servers = wan_config.get('settings', {}).get('dnsservers', ["1.1.1.1","8.8.8.8","9.9.9.9"])

                if wan_config.get('settings', {}).get('ip', None) and wan_config.get('settings', {}).get('gateway', None):
                    if wan_config.get('settings', {})['ip'] not in check_ip_configured(DOMAIN):
                        subprocess.call(f'''
                            ip netns exec {NETNS} ip addr add {wan_config.get('settings', {})['ip']} dev {BRIDGE_E}
                            ip netns exec {NETNS} ip route add 0.0.0.0/0 via {wan_config.get('settings', {})['gateway']} dev {BRIDGE_E}
                        ''', shell=True)
                        log_netns_ip_addr(NETNS)

                if not check_ip_configured(DOMAIN):
                    logger.info(f'Trying DHCP on {BRIDGE_E}')
                    with subprocess.Popen(f"ip netns exec {NETNS} dhclient {BRIDGE_E} -d", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as p:
                        lines = []
                        for line in p.stdout:
                            lines.append(line)
                            if len([line for line in lines if 'DHCPDISCOVER' in line]) >= 5:
                                p.terminate()
                                break
                            if 'DHCPACK' in line:
                                break

                        if 'DHCPACK' in line:
                            # keep DHCP service running as long as nic stays up
                            while check_interface_is_up(NETNS,EXTERNAL_NIC):
                                time.sleep(5)
                            p.terminate()
                            continue

                if not check_ip_configured(DOMAIN):
                    logger.info(f'no DHCP detected trying auto detect script on {BRIDGE_E}')
                    detect_subnet.configure_wan_interface(DOMAIN)

                # configure dns servers
                if check_ip_configured(DOMAIN):
                    set_dns_servers(NETNS,dns_servers)

            elif check_interface_is_up(NETNS, BRIDGE_E):
                logger.info(f'External interface is down, unconfiguring {BRIDGE_E}')
                subprocess.call(f'''
                    ip netns exec {NETNS} ip addr flush dev {BRIDGE_E}
                    ip netns exec {NETNS} ip link set dev {BRIDGE_E} down
                ''', shell=True)

        except Exception as e:
            logger.error(e)

        time.sleep(5)

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

def create_vlan_bridges():
    VLAN_BRIDGES_LOCAL_FILE = f'{LOCAL_CONFIG_FOLDER}/vlan_bridges.yaml'
    VLAN_BRIDGES_GLOBAL_FILE = f'{GLOBAL_CONFIG_FOLDER}/vlan_bridges.yaml'
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
    vlan_bridges = mergeDictionary(global_vlan_bridges, local_vlan_bridges)
    configured_vlan_interfaces = [f"{k}.{i.get('vid')}" for k,v in vlan_bridges.items() for i in v.get('vlans')]
    existing_vlan_interfaces = [interface for interface in netifaces.interfaces() if '.' in interface]
    bridge_reserved_ranges = {k:[i for r in v.get('reserved',{}) for i in list(range(*[int(s)for s in r.get('range','').split('-')]))] for k,v in global_vlan_bridges.items()}

    # remove vlan bridges and interfaces not in list
    for existing_vlan_interface in existing_vlan_interfaces:
        try:
            bridge, vlan = existing_vlan_interface.split('.')
            if int(vlan) in bridge_reserved_ranges[bridge]:
                logger.info(f"Ignoring reserved vlan interface: {bridge}.{vlan}")
            elif existing_vlan_interface not in configured_vlan_interfaces:
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
            if vlan_interface not in existing_vlan_interfaces:
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
        time.sleep(1)
        logger.info(f"Mounting default namespace as ROOT")
        subprocess.run(f'''
            touch {ROOT_NS_FILE}
            mount --bind /proc/1/ns/net {ROOT_NS_FILE}
        ''', shell=True)

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
            create_trunkports(BOND['name'], BOND['interfaces'], BOND['bridgename'])

        create_vlan_bridges()

        TRUNKBRIGE = DEV_CONFIG[0]['portconfig']['INT'][0]

        processes = []
        for k,v in DEV_CONFIG[0]['portconfig']['WAN'].items():
            status = multiprocessing.Event()
            process = multiprocessing.Process(name=f'Setup WAN{k}', target=create_wanport, args=(status,k,v, TRUNKBRIGE))
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
    import systemd.daemon
    systemd.daemon.notify('READY=1')
