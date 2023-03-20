#!/bin/python3
import subprocess
import yaml
import cmd
import sys

class show(cmd.Cmd):
    def do_system(self, args):
        self.do_platform(args)
        self.do_serial(args)
        self.do_version(args)

    def do_serial(self, args):
        asset_tag=subprocess.run(f"cat /sys/devices/virtual/dmi/id/board_asset_tag", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
        print (f"Version: {asset_tag}")
        
    def do_platform(self, args):
        product_name=subprocess.run(f"cat /sys/devices/virtual/dmi/id/product_name", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
        print (f"Platform: {product_name}")

    def do_version(self, args):
        
        with open('/opt/ncubed/meta.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"Version: {data.get('version')}")

    def do_netns(self, args):
        NETNAMESPACES = subprocess.run(f"ls /run/netns/", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().split()
        for NETNS in NETNAMESPACES:
            print(f"\n{50*'#'} {NETNS} {50*'#'}")
            subprocess.run(f'''
                sudo ip -n {NETNS} -br -c addr
                ''', shell=True)
    
    def do_exit(self, args):
            return True

class cli(cmd.Cmd):
    """Accepts commands via the normal interactive prompt or on the command line."""
    prompt = "ncubed >>> "
    def __init__(self):
        cmd.Cmd.__init__(self)

    def do_show(self, args):
        if len(args) > 1:
            show().onecmd(args)

    def complete_show(self, text, line, start_index, end_index):
        return [ t for t in show().completenames('') if text in t]

    def do_exit(self, args):
        return True
    
    def do_connect_USB0(self, args):
        input("""
                Connecting to /dev/ttyUSB0 with baud rate 115200
                to exit screen use: CTRL-A k
                Press any key to continue
        """)
        subprocess.run(f'''
                       sudo python3 /opt/ncubed/bin/reset_usb.py CP210x
                       sudo screen /dev/ttyUSB0 115200
                       ''', shell=True)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cli().onecmd(' '.join(sys.argv[1:]))
    else:
        cli().cmdloop()
