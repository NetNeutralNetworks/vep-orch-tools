#!/bin/python3
import libvirt
import logging
import sys
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

def check_vm_states(conn):
    for dom in conn.listAllDomains():
        if all([dom.state()[0] is not libvirt.VIR_DOMAIN_RUNNING, dom.autostart() == 1 ]):
            dom.create()
            logger.debug(f'VM {dom.name()} started')

if __name__ == '__main__':
    while True:
        with libvirt.open() as conn:
            try:
                check_vm_states(conn)
            except Exception as e:
                logger.error(e)
        
        sleep(10)
