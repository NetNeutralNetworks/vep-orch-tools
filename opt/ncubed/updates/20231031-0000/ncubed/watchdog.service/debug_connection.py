import json
import subprocess

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
COLOR_RESET = "\033[0m\n"

GW_TEST_IP="8.8.8.8"

def get_existing_netnamespaces():
    existing_netnamespaces_json = subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    if existing_netnamespaces_json:
        existing_netnamespaces=json.loads(existing_netnamespaces_json)
        return existing_netnamespaces
    else:
        return {}

netns_info = subprocess.run(f"n3 show netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
route_info = subprocess.run(f"ip route", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
dns_masq = subprocess.run(f"cat /var/lib/misc/dnsmasq.leases", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
dhcp_leases = subprocess.run(f"cat /var/lib/dhcp/dhclient.leases", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
for NETNS in get_existing_netnamespaces():
    print(f"""testing connectivity in: {NETNS.get('name')}
{'='*15}""")
    NETNS = NETNS.get('name')
    output = subprocess.run(f"ip netns exec {NETNS} ping -c 1 -W 1 {GW_TEST_IP}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    if "received, 0% packet loss" in output:
        print(GREEN+GW_TEST_IP+ " is reachable from "+NETNS+COLOR_RESET)
    else:
        print(RED+GW_TEST_IP+" is NOT reachable from "+NETNS+COLOR_RESET)
    route = subprocess.run(f"ip netns exec {NETNS} ip route | grep default", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    route = route.strip()
    if route:
        print(f"{GREEN}{route}{COLOR_RESET}")
    else:
        print(f"{RED}No default route{COLOR_RESET}")

    dns = subprocess.run(f"ip netns exec {NETNS} nslookup google.com | grep Server", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    dns = dns.strip()
    if dns:
        print(f"{GREEN}DNS {dns}{COLOR_RESET}")
    else:
        print(f"{RED}No dns server{COLOR_RESET}")
    
    public_ip = subprocess.run(f"ip netns exec {NETNS} curl ifconfig.me", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=True).stdout.decode()
    public_ip = public_ip.strip()
    if public_ip:
        print(f"{GREEN}Public IP: {public_ip}{COLOR_RESET}")
    else:
        print(f"{RED}Could not find public ip{COLOR_RESET}")
    # print(f"""{subprocess.run(f"ip netns exec {NETNS} nslookup google.com", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, timeout=5).stdout.decode()}""")
    # print(f"""{subprocess.run(f"ip netns exec {NETNS} tracepath {GW_TEST_IP}", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, timeout=5).stdout.decode()}""")
