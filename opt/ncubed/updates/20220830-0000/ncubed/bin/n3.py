#!/bin/python3
import subprocess
import yaml
import cmd
import sys
import json

class configure(cmd.Cmd):
    prompt = "ncubed configure >>> "

    def do_version(self, args):
        
        with open('/opt/ncubed/meta.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"Version: {data.get('version')}")
    
    def do_exit(self, args):
            return True

class show(cmd.Cmd):
    prompt = "ncubed show >>> "

    def do_version(self, args):
        
        with open('/opt/ncubed/meta.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"Version: {data.get('version')}")

    def do_netns(self, args):
        print(f"\n{50*'#'} DEFAULT {50*'#'}")
        subprocess.run(f'''ip -br -c addr''', shell=True)
        NETNAMESPACES = json.loads(subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode())
        for NETNS in [n.get('name')for n in NETNAMESPACES]:
            print(f"\n{50*'#'} {NETNS} {50*'#'}")
            subprocess.run(f'''ip -n {NETNS} -br -c addr''', shell=True)
    
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

    def do_configure(self, args):
        if len(args) > 1:
            configure().onecmd(args)
        else:
            configure().cmdloop()

    def complete_configure(self, text, line, start_index, end_index):
        return [ t for t in configure().completenames('') if text in t]

    def do_exit(self, args):
        return True

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cli().onecmd(' '.join(sys.argv[1:]))
    else:
        subprocess.run(f"clear", shell=True)
        cli().cmdloop()
