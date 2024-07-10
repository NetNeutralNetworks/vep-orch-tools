import subprocess, yaml

def to_20231031():
    LOCAL_CONFIG_FOLDER = "/opt/ncubed/config/local"
    ORCH_INFO_FILE = f'{LOCAL_CONFIG_FOLDER}/orch_info.yaml'

    with open(ORCH_INFO_FILE, 'r') as f:
        attestation = yaml.safe_load(f)

    if attestation.get('orchestration_server'):
        # Device has old orch info written to storage
        ipv6_supernet = subprocess.run(f"sudo wg show all allowed-ips", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip().split(' ')[-1]
        if ipv6_supernet == '':
            # This code only runs if the wg tunnel is somehow removed or missing before this migration is complete
            # fd71::/64 was the default pre 20231031
            ipv6_supernet = 'fd71::/64'
        
        new_config = {
            "message": "success",
            "result": {
                "device_id": attestation.get('device_id'),
                "servers":[{
                    "ipv6_supernet": ipv6_supernet,
                    "orchestration_server": attestation.get('orchestration_server').split(':')[0],
                    "server_pub_key": attestation.get('server_pub_key')
                }
                ]
            }
        }
        with open(ORCH_INFO_FILE, 'w') as f:
            f.write(yaml.dump(new_config))
to_20231031()