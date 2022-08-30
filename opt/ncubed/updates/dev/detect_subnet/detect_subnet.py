import subprocess
import concurrent.futures
import ipaddress

'''
This script will try to detect the network and the gateway for a specific WAN interface
It uses tcpdump to find GARP packets
Then it it activly looks for available ip adresses on an increasing network sizes /30 then /29 etc.
After a network is establisched al ip adresses found are tried as gateway for a default route to internet
'''

MAX_WORKERS=500

def exec_pool(FUNCTION,LIST):
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(FUNCTION,LIST)

def ping_host(IP):
    subprocess.run(f'''
        ip netns exec ns_{WANINTF} ping -c 1 -W 1 {IP}
        ''', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def find_gateway(detected_ips):
    while detected_ips:
        TEST_IP = detected_ips.pop(0)
        print(f"Trying {TEST_IP} as gateway")
        subprocess.run(f'''
            ip netns exec ns_{WANINTF} ip route del 0.0.0.0/0
            ip netns exec ns_{WANINTF} ip route add 0.0.0.0/0 via {TEST_IP}
            ''', shell=True)
        output = subprocess.run(f"ip netns exec ns_{WANINTF} ping -c 1 -W 1 8.8.8.8",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
        if "received, 0% packet loss" in output:
            print(f"Using {TEST_IP} as gateway")
            return 0

    print(f"No usable gateway found!!!")  
    return 1

def test_subnet(WANINTF,reference_ip):
    for CIDR in range(30,23, -1):
        PROBABLE_NETWORK = ipaddress.IPv4Interface(f"{reference_ip}/{CIDR}").network
        subprocess.run(f'''
            ip netns exec ns_{WANINTF} ip addr flush dev br-{WANINTF}_e
            ip netns exec ns_{WANINTF} ip addr add {PROBABLE_NETWORK[0]}/{CIDR} dev br-{WANINTF}_e
            ip netns exec ns_{WANINTF} ip -br -c addr show dev br-{WANINTF}_e
            ''', shell=True)

        exec_pool(ping_host, list(WANINTF,PROBABLE_NETWORK))
        detected_ips = subprocess.run(f"ip netns exec ns_{WANINTF} ip neigh | grep lladdr | cut -d ' ' -f1", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().split()
        if len(detected_ips) < PROBABLE_NETWORK.num_addresses-2:
            available_ips = sorted(set([str(address) for address in list(PROBABLE_NETWORK)[1:-1]])-set(detected_ips))
            subprocess.run(f'''
                ip netns exec ns_{WANINTF} ip addr flush dev br-{WANINTF}_e
                ip netns exec ns_{WANINTF} ip addr add {available_ips[-1]}/{CIDR} dev br-{WANINTF}_e
                ip netns exec ns_{WANINTF} ip -br -c addr show dev br-{WANINTF}_e
                ''', shell=True)
            if find_gateway(detected_ips) == 0:
                return 0

def capture_reference_ip(WANINTF):
    # using Popen to be able to continuously monitor tcpdump output
    with subprocess.Popen(f"ip netns exec ns_{WANINTF} tcpdump -i br-{WANINTF}_e -U -l", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end='')
            if len(line.split(',')) > 1:
                words=line.split(',')[1].split()
                if len(words) > 4:
                    if words[2] == words[4]:
                        p.terminate()
                        return words[2]

def configure_wan_interface(WANINTF):
    reference_ip = capture_reference_ip(WANINTF)
    detected_ips = test_subnet(WANINTF,reference_ip)
    find_gateway(WANINTF,detected_ips)

if __name__ == "__main__":
    configure_wan_interface('WAN0')
    print('END')