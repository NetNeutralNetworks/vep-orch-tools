#!/bin/python3
import requests, time, json, os

DAS_SERVER = "https://ncubed-das.westeurope.cloudapp.azure.com"
TOKEN = "Hd4Ir161R8HygS8WVXmh4Rvoll1NgduHweVXGQRQREU"
PUB_KEY = "odz9hZVQO2maqpaFIG33Tv5ihBAD+1/SxI8Ko2FSFzM="

IPV4_PREFIX="100.71"
IPV6_PREFIX="fd71"

import json, os.path
from random import randint
def update_cockpit(host, action):
    dirname = '/etc/cockpit/machines.d/'
    filename = f'{dirname}00-autopop.json'

    if not os.path.isdir(dirname):
        return False

    if os.path.isfile(filename):
        with open(filename, "r") as file:
            data = json.load(file)
    else:
        data = json.loads('{}')

    if action=='add':
        entry = {host : {
                "visible" : True,
                "color" : f"rgb({randint(0, 255)}, {randint(0, 255)}, {randint(0, 255)})",
                "address" : host,
                "label" : host,
                "user" : "nc-admin"
                }}
        data.update(entry)
    elif action=='remove':
        if host in data:
            data.pop(host)
    else:
        return False

    with open(filename, "w+") as file:
        json.dump(data, file, indent=4, sort_keys=True)
    return True


def active_peers():
    return [k[4].split(',')[0].split('/')[0] for k in [j for j in [i.split('\t') for i in os.popen("wg show all dump").read().split('\n')] if len(j) == 9 and j[5].isdigit and int(j[5]) > time.time()-300 ]]

while True:
    data = {
        'token': TOKEN,
        'server_pub_key': PUB_KEY
    }
    r = requests.post(
        '{}/api/v1/serverapi/getclients'.format(DAS_SERVER),
        json=data)

    print(r)
    results = json.loads(r.text)

    print(results)

    for result in results['results']:
        ipv6 = "{}::{}/128".format(IPV6_PREFIX, result['device_id'])
        ipv4 = "{}.{}.{}/32".format(IPV4_PREFIX, result['device_id'] >> 8 & 255, result['device_id'] & 255)
        if not result['device_id']:
            continue
        if result['approved']:
            os.system("wg set wg0 peer {} allowed-ips {},{}".format(result['client_pub_key'], ipv4, ipv6))
            os.system("wg-quick save wg0")
            update_cockpit(ipv4.split('/')[0],"add")
        else:
            os.system("wg set wg0 peer {} remove".format(result['client_pub_key']))
            os.system("wg-quick save wg0")
            update_cockpit(ipv4.split('/')[0],"remove")

    time.sleep(10)
