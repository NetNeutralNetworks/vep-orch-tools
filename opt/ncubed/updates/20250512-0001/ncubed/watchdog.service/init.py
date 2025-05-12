#!/bin/python3
import libvirt, subprocess
import logging
import sys, os, json, yaml, datetime, traceback
from logging.handlers import RotatingFileHandler
from time import sleep

logger = logging.getLogger("ncubed watchdog daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s, Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(process)s: %(message)s',
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.watchdogd.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

GW_TEST_IP="8.8.8.8"
INTERNET_IPS = ["1.1.1.1", "8.8.8.8", "208.67.222.222"]
LOCAL_CONFIG_FOLDER = "/opt/ncubed/config/local"
GLOBAL_CONFIG_FOLDER = "/opt/ncubed/config/global"
ORCHESTRATION_V4_PREFIX = "100.71"
ORCHESTRATION_V6_PREFIX = "fd71::"
STATUS_FILE = '/opt/ncubed/status.json'

def check_vm_states(conn):
    for dom in conn.listAllDomains():
        if all([dom.state()[0] is not libvirt.VIR_DOMAIN_RUNNING, dom.autostart() == 1 ]):
            dom.create()
            logger.debug(f'VM {dom.name()} started')

def get_existing_netnamespaces():
    existing_netnamespaces_json = subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    if existing_netnamespaces_json:
        existing_netnamespaces=json.loads(existing_netnamespaces_json)
        return existing_netnamespaces
    else:
        return {}

def get_port_configs():
    try:
        with open(f'{LOCAL_CONFIG_FOLDER}/network.yaml', 'r') as f:
            PORT_CONFIGS = yaml.safe_load(f)
        return PORT_CONFIGS
    except Exception as e:
        logger.error(f"Unable to read: {LOCAL_CONFIG_FOLDER}/network.yaml")
        sys.exit(1)

def get_wan_ports():
    PORT_CONFIGS = get_port_configs()

    DEV_FAMILIY = subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG = [PORT_CONFIG for PORT_CONFIG in PORT_CONFIGS if PORT_CONFIG.get('family') == DEV_FAMILIY]
    if DEV_CONFIG:
        return DEV_CONFIG[0]['portconfig']['WAN'].items()

def cycle_wan_ports():
    if not is_at_night():
        return
    logger.warning("Cycling wan ports")
    for ns, port in get_wan_ports():
        # set port down
        subprocess.run(f"ip netns exec ns_WAN{ns} ip link set {port} down", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

        sleep(1)
        # set port up
        subprocess.run(f"ip netns exec ns_WAN{ns} ip link set {port} up", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

def any_wan_port_connected():
    for ns, port in get_wan_ports():
        port_status = subprocess.run(f"ip netns exec ns_WAN{ns} ip link show {port}", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
        if 'state UP' in port_status:
            return True
    return False
    
def is_at_night():
    now = datetime.datetime.now()
    if now.hour < 6:
        return True
    return False

def request_reboot():
    file_name = '/var/log/panic_reboot.time'
    if any_wan_port_connected():
        if check_internet():
            # We have internet, so we wait untill night to reboot
            if not is_at_night():
                return
            try:
                t = os.path.getmtime(file_name)
                last_rebooted = datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc)
            except OSError:
                last_rebooted = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)

            now = datetime.datetime.now(tz=datetime.timezone.utc)
            if (now - last_rebooted).days > 0:
                logger.warning("Resorting to last option, rebooting platform")
                subprocess.run(f"touch {file_name}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
                subprocess.run(f"init 6",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        else:
            # We dont have internet, so we try to reboot now
            try:
                t = os.path.getmtime(file_name)
                last_rebooted = datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc)
            except OSError:
                last_rebooted = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)

            now = datetime.datetime.now(tz=datetime.timezone.utc)
            if (now - last_rebooted).days > 0:
                logger.warning("Resorting to last option, rebooting platform")
                subprocess.run(f"touch {file_name}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
                subprocess.run(f"init 6",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

def check_connection():
    with open(STATUS_FILE, 'r') as file:
        status = json.load(file)
    orch_status = status.get('orch_status')
    if orch_status == 'FULL' or orch_status == 'PARTIAL':
        return True
    else:
        return False

def check_internet():
    for NETNS in get_existing_netnamespaces():
        NETNS = NETNS.get('name')
        for ip in INTERNET_IPS:
            output = subprocess.run(f"ip netns exec {NETNS} ping -c 1 -W 1 {ip}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
            if "received, 0% packet loss" in output:
                return True
    return False

def restart_network_service():
    logger.error("Restarting ncubed-network.service")
    subprocess.run(f"systemctl restart ncubed-network.service",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)


def debug_connection():
    logger.warning("Not connected. Starting debugging")

    netns_info = subprocess.run(f"n3 show netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    route_info = subprocess.run(f"ip route", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    dns_masq = subprocess.run(f"cat /var/lib/misc/dnsmasq.leases", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    dhcp_leases = subprocess.run(f"cat /var/lib/dhcp/dhclient.leases", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    netns_reachability = []
    for NETNS in get_existing_netnamespaces():
        NETNS = NETNS.get('name')
        output = subprocess.run(f"ip netns exec {NETNS} ping -c 1 -W 1 {GW_TEST_IP}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
        if "received, 0% packet loss" in output:
            netns_reachability.append(f"{GW_TEST_IP} is reachable from {NETNS}")
        else:
            netns_reachability.append(f"{GW_TEST_IP} is NOT reachable from {NETNS}")
        netns_reachability.append(f"""
ROUTE INFO: {NETNS} 
\/ \/ \/ 
{subprocess.run(f"ip netns exec {NETNS} ip route", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()}
DNS INFO: {NETNS}
\/ \/ \/ 
{subprocess.run(f"ip netns exec {NETNS} nslookup google.com", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()}
TRACEROUTE INFO: {NETNS}
\/ \/ \/ 
{subprocess.run(f"ip netns exec {NETNS} tracepath {GW_TEST_IP}", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()}
""")


    with open('/var/log/connection_debug.log', 'w') as connection_debug_file:
        new_line = "\n"
        connection_debug_file.write(f"""
==============
n3 show netns:
{netns_info}
==============
route info:
{route_info}
==============
dnsmasq leases:
{dns_masq}
==============
own dhcp leases:
{dhcp_leases}
==============
netns info:
{new_line.join(f"{item}" for item in netns_reachability)}
==============
        """)
    
if __name__ == '__main__':
    while True:
        with libvirt.open() as conn:
            try:
                check_vm_states(conn)
            except Exception as e:
                logger.error(e)
        try:
            if not check_connection():
                for strategy in [debug_connection, restart_network_service, cycle_wan_ports, request_reboot]:
                    strategy()
                    sleep(10)
                    if check_connection():
                        break
                            
        except Exception as e:
                logger.error(e)
                logger.error(f"Fatal error occured during watchdog connection-test: {traceback.format_exc()}")
        sleep(10)
