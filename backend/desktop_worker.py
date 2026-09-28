"""Private subprocess entry point; the WebSocket never accepts shell commands."""
import json
import os
import subprocess
import sys
from .config import ROOT

def main():
    job = json.loads(sys.stdin.buffer.read())
    name, args = job['name'], job['args']
    if name == 'power':
        if os.name != 'nt': raise RuntimeError('Power commands currently support Windows only')
        commands = {'shutdown':['shutdown','/s','/t','5'], 'restart':['shutdown','/r','/t','5'], 'logout':['shutdown','/l']}
        subprocess.run(commands[args['action']], check=True, creationflags=0x08000000)
        print('The operating system accepted the power command.')
    elif name == 'whatsapp':
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(args['contact'], args['message'], wait_time=15, tab_close=False)
        print('WhatsApp send automation finished. Please check the chat for delivery.')
    elif name == 'youtube':
        import pywhatkit
        pywhatkit.playonyt(args['query'])
        print('Opened the first YouTube result for playback; the browser may require a play click.')
    elif name == 'launch_app':
        aliases = json.loads((ROOT / 'apps.json').read_text())
        command = [os.path.expandvars(v) for v in aliases[args['name']]]
        subprocess.Popen(command, shell=False)
        print(f'Launched {args["name"]}.')
    else: raise ValueError('Unsupported desktop action')

if __name__ == '__main__': main()
