#!/bin/python3
import re
import os
import logging
import libvirt
import tty
import termios
import atexit
import time
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter
from typing import Optional  # noqa F401

def error_handler(unused, error) -> None:
    # The console stream errors on VM shutdown; we don't care
    if error[0] == libvirt.VIR_ERR_RPC and error[1] == libvirt.VIR_FROM_STREAMS:
        return
    logging.warn(error)


class Console(object):
    def __init__(self, uri: str, uuid: str) -> None:
        self.uri = uri
        self.uuid = uuid
        self.connection = libvirt.open(uri)
        self.domain = self.connection.lookupByUUIDString(uuid)
        self.state = self.domain.state(0)
        self.connection.domainEventRegister(lifecycle_callback, self)
        self.stream = None  # type: Optional[libvirt.virStream]
        self.run_console = True
        self.stdin_watch = -1
        self.text= ''
        logging.info("%s initial state %d, reason %d",
                     self.uuid, self.state[0], self.state[1])


def check_console(console: Console) -> bool:
    if (console.state[0] == libvirt.VIR_DOMAIN_RUNNING or console.state[0] == libvirt.VIR_DOMAIN_PAUSED):
        if console.stream is None:
            console.stream = console.connection.newStream(libvirt.VIR_STREAM_NONBLOCK)
            console.domain.openConsole(None, console.stream, 0)
            console.stream.eventAddCallback(libvirt.VIR_STREAM_EVENT_READABLE, stream_callback, console)
    else:
        if console.stream:
            console.stream.eventRemoveCallback()
            console.stream = None

    return console.run_console


def stdin_callback(watch: int, fd: int, events: int, console: Console) -> None:
    readbuf = os.read(fd, 1024)
    print(readbuf)
    if readbuf.startswith(b""):
        console.run_console = False
        return
    if console.stream:
        console.stream.send(readbuf)


def stream_callback(stream: libvirt.virStream, events: int, console: Console) -> None:
    try:
        assert console.stream
        received_data = console.stream.recv(1024)
        console.text += received_data.decode()
    except Exception:
        return
    return received_data
    ##os.write(0, received_data)


def lifecycle_callback(connection: libvirt.virConnect, domain: libvirt.virDomain, event: int, detail: int, console: Console) -> None:
    console.state = console.domain.state(0)
    logging.info("%s transitioned to state %d, reason %d",
                 console.uuid, console.state[0], console.state[1])


uri = 'qemu:///system'
connection = libvirt.open(uri)
vm = connection.lookupByName('ION')
uuid = vm.UUIDString()

# print("Escape character is ^]")
logging.basicConfig(filename='msg.log', level=logging.DEBUG)
logging.info("URI: %s", uri)
logging.info("UUID: %s", uuid)

libvirt.virEventRegisterDefaultImpl()
libvirt.registerErrorHandler(error_handler, None)

console = Console(uri, uuid)
console.stdin_watch = libvirt.virEventAddHandle(0, libvirt.VIR_EVENT_HANDLE_READABLE, stdin_callback, console)

console.stream = console.connection.newStream(libvirt.VIR_STREAM_NONBLOCK)
console.domain.openConsole(None, console.stream, 0)
console.stream.eventAddCallback(libvirt.VIR_STREAM_EVENT_READABLE, stream_callback, console)
# while check_console(console):
def send_command(command='',waitfor='(Q)uit', timeout=1, stdout=False):
    START_TIME = time.time()
    command = f"{command}\r".encode()
    console.text = '\n'
    console.stream.send(command)
    last_text = ''
    #print(f'\n{time.time() - START_TIME} Waiting for: {waitfor}\n')
    while True:
        libvirt.virEventRunDefaultImpl()
        if stdout:
            if waitfor in console.text or '\n' in console.text[len(last_text):]:
                print(console.text[len(last_text):].replace('\n',''))
                last_text = console.text
        
        if waitfor in console.text:
            break
        else:
            pass
            
        if time.time() - START_TIME > timeout:
            print('Invalid arguments provided')
            exit()
            break

    #print(f"\n{100*'#'}\nThis is the end result: {console.text}")
    return console.text  

# main
send_command(timeout=120)
if "Select an item to modify, or submit config:" in console.text:
    # if in main menu enter model select
    send_command(command='1')

output=send_command()
model_menu='\n'.join([i for i in output.replace('\t','').split('\r\n') if ') ' in i])

parser = ArgumentParser(epilog=f"""
Available models: 
{model_menu}

The ION_KEY and SECRET_KEY need to be obtained from the sdwan portal
example:

{__file__} 2 00000000000-00000000-0000-0000-0000-000000000000 {40*'0'}
""", formatter_class=RawTextHelpFormatter)
parser.add_argument("MODEL_ID")
parser.add_argument("ION_KEY")
parser.add_argument("SECRET_KEY")

try:
    args = parser.parse_args()
except:
    parser.print_help()
    exit(0)

def menu(text_on_screen, key):
    items = re.findall(f'(\d*)\) \t*?{re.escape(key)}', text_on_screen)
    if len(items) == 1:
        return items[0]
    else:
        raise Exception("\n\nMenu has changed, please contact your nearest programmer to fix the code")

# set model
text_on_screen = send_command(command=args.MODEL_ID, waitfor="Choose a Number or (Q)uit:")
# set ION key
text_on_screen = send_command(command=menu(text_on_screen, 'ION Key'), waitfor="Enter ION Key[")
text_on_screen = send_command(command=args.ION_KEY, waitfor="Choose a Number or (Q)uit:")
# set Secret key
text_on_screen = send_command(command=menu(text_on_screen, 'Secret Key'), waitfor="Enter ION secret[")
text_on_screen = send_command(command=args.SECRET_KEY, waitfor="Choose a Number or (Q)uit:")
# set first wan nic to dhcp
text_on_screen = send_command(command=menu(text_on_screen, 'Port 1'), waitfor="Choose a Number or (Q)uit:")
text_on_screen = send_command(command=menu(text_on_screen, 'Role'), waitfor="Choose a Number or (Q)uit:")
text_on_screen = send_command(command=menu(text_on_screen, 'Internet facing port (PublicWAN)'), waitfor="Choose a Number or (Q)uit:")
text_on_screen = send_command(command=menu(text_on_screen, 'Apply and return'), waitfor="Choose a Number or (Q)uit:")
# save exit and reboot
text_on_screen = send_command(command=menu(text_on_screen, 'Submit and restart'), waitfor='Submit these changes now?[N]:')
text_on_screen = send_command(command='Y', waitfor='login:', timeout=120, stdout=True)
