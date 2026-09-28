"""Validated tool handlers adapted from the original Kravox command features."""
import asyncio
import json
import os
import re
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import httpx
from .config import ROOT

def tool(name, description, properties=None, required=None):
    return {'type':'function','function':{'name':name,'description':description,
        'parameters':{'type':'object','properties':properties or {},'required':required or [],'additionalProperties':False}}}

def string(description, enum=None):
    return {'type':'string','description':description, **({'enum':enum} if enum else {})}

TOOLS = [
    tool('google_search', 'Open Google search or homepage.', {'query':string('Search words, or empty for homepage')}),
    tool('youtube', 'Open YouTube, search, or play the first result.', {'query':string('Search words'), 'play':{'type':'boolean'}}),
    tool('music', 'Play or control local music.', {'command':string('Control', ['play','pause','resume','stop','next']), 'query':string('Optional filename fragment')}, ['command']),
    tool('wikipedia', 'Look up a topic on Wikipedia.', {'query':string('Topic')}, ['query']),
    tool('launch_app', 'Launch an app configured in apps.json. Default names: vscode, notepad, calculator.', {'name':string('App alias')}, ['name']),
    tool('power', 'Request shutdown, restart, or logout. Server asks for spoken confirmation.', {'action':string('Action', ['shutdown','restart','logout'])}, ['action']),
    tool('whatsapp', 'Request a WhatsApp message. Ask for missing contact and message first. Server requires spoken confirmation.', {'contact':string('Contact alias or international phone number'), 'message':string('Exact message supplied by the user')}, ['contact','message']),
    tool('language', 'Set reply language.', {'language':string('Language', ['en','hi','auto'])}, ['language']),
    tool('voice_expression', 'Describe the latest uncertain pitch and energy expression estimation.'),
    tool('face_expression', 'Request one webcam frame for expression estimation.'),
    tool('iot', 'Placeholder for a future MQTT/ESP32 device.', {'device':string('Device'), 'action':string('Requested operation')}, ['device','action']),
    tool('current_time', 'Read the local time.'),
]

def validate(name, args):
    schema = next((t['function']['parameters'] for t in TOOLS if t['function']['name'] == name), None)
    if schema is None or not isinstance(args, dict): raise ValueError('Unknown action')
    if set(args) - set(schema['properties']): raise ValueError('Unexpected action arguments')
    for key in schema['required']:
        if key not in args or not str(args[key]).strip(): raise ValueError(f'Please provide {key}.')
    for key, value in args.items():
        spec = schema['properties'][key]
        if spec['type'] == 'string' and (not isinstance(value, str) or len(value) > 2000): raise ValueError('Invalid text argument')
        if spec['type'] == 'boolean' and not isinstance(value, bool): raise ValueError('Invalid boolean argument')
        if 'enum' in spec and value not in spec['enum']: raise ValueError('Unsupported action option')

async def desktop_job(name, args):
    """Isolate blocking desktop libraries in a killable subprocess, without a shell."""
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'backend.desktop_worker',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=str(ROOT.parent), creationflags=0x08000000 if os.name == 'nt' else 0)
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(json.dumps({'name':name,'args':args}).encode()), 60)
        if process.returncode: raise RuntimeError('Desktop action failed. Check app installation and WhatsApp Web login.')
        return stdout.decode().strip().splitlines()[-1]
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise

class MusicPlayer:
    def __init__(self): self.index = -1
    def control(self, command, query=''):
        import pygame
        directory = Path(os.getenv('MUSIC_DIR') or Path.home() / 'Music')
        files = sorted(p for p in directory.glob('*') if p.suffix.lower() in ('.mp3','.wav','.ogg','.flac'))
        if not pygame.mixer.get_init(): pygame.mixer.init()
        if command in ('pause','resume','stop'):
            {'pause':pygame.mixer.music.pause,'resume':pygame.mixer.music.unpause,'stop':pygame.mixer.music.stop}[command]()
            return f'Music {command} requested.'
        if not files: return 'No MP3, WAV, OGG or FLAC music was found in your configured Music folder.'
        if query:
            matches = [i for i,p in enumerate(files) if query.lower() in p.stem.lower()]
            if not matches: return 'No local song matched that name.'
            self.index = matches[0]
        else: self.index = (self.index + 1) % len(files)
        pygame.mixer.music.load(str(files[self.index])); pygame.mixer.music.play()
        return f'Playing {files[self.index].stem}.'

music = MusicPlayer()
music_lock = asyncio.Lock()

class ActionRouter:
    def __init__(self, session):
        self.session = session
        self.pending = None

    async def confirm(self, text, spoken):
        if not self.pending: return None
        pending, self.pending = self.pending, None
        if time.monotonic() > pending['expires']: return 'That confirmation expired. Please request the action again.'
        answer = re.sub(r'[.!?।]', '', text.lower()).strip()
        if answer not in ('yes','confirm','yes confirm','yes please','हाँ','हां','हाँ करो','करो'):
            return 'Cancelled. I did not perform that action.'
        if not spoken:
            self.pending = pending
            return 'Please say yes using the microphone to confirm, or say no to cancel.'
        await self.session.send('action', name=pending['name'], result='Confirmed; submitting the action.')
        try:
            result = await desktop_job(pending['name'], pending['args'])
        except asyncio.CancelledError:
            await self.session.send('action', name=pending['name'], result='Interrupted. The desktop action may already have been submitted; check before retrying.')
            raise
        await self.session.send('action', name=pending['name'], result=result)
        return result

    async def handle(self, name, args):
        try:
            validate(name, args)
            result = await self._handle(name, args)
        except asyncio.CancelledError: raise
        except Exception as exc:
            result = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else f'Action unavailable ({type(exc).__name__}). Check local setup.'
        await self.session.send('action', name=name, result=result)
        return result

    async def _handle(self, name, args):
        if name in ('google_search','youtube'):
            query = args.get('query', '').strip()
            if name == 'youtube' and args.get('play'):
                if not query: return 'What would you like to play on YouTube?'
                return await desktop_job('youtube', {'query':query})
            url = ('https://www.google.com/search?q=' if name == 'google_search' else 'https://www.youtube.com/results?search_query=') + quote(query)
            if not query: url = 'https://www.google.com' if name == 'google_search' else 'https://www.youtube.com'
            opened = await asyncio.to_thread(webbrowser.open, url)
            return 'Opened your search in the browser.' if opened else 'The browser could not be opened.'
        if name == 'music':
            async with music_lock:
                return music.control(args['command'], args.get('query',''))
        if name == 'current_time': return datetime.now().strftime('It is %I:%M %p.')
        if name == 'wikipedia':
            language = 'hi' if self.session.language == 'hi' else 'en'
            async with httpx.AsyncClient(timeout=8, headers={'User-Agent':'KravoxLocal/3.0 (personal voice assistant)'}) as client:
                r = await client.get(f'https://{language}.wikipedia.org/w/api.php', params={
                    'action':'query','generator':'search','gsrsearch':args['query'],'gsrlimit':1,
                    'prop':'extracts','exintro':1,'explaintext':1,'exsentences':3,'format':'json'})
                r.raise_for_status()
                pages = r.json().get('query',{}).get('pages',{})
                return next(iter(pages.values()), {}).get('extract','No Wikipedia result found.')[:3000]
        if name == 'launch_app':
            aliases = json.loads((ROOT / 'apps.json').read_text())
            alias = args['name'].lower()
            if alias not in aliases: return 'That app is not configured in backend/apps.json.'
            return await desktop_job('launch_app', {'name':alias})
        if name in ('whatsapp','power'):
            if name == 'whatsapp':
                contacts_file = ROOT / 'contacts.json'
                contacts = json.loads(contacts_file.read_text()) if contacts_file.exists() else {}
                phone = contacts.get(args['contact'].lower(), args['contact'])
                phone = re.sub(r'[\s()-]', '', phone)
                if not re.fullmatch(r'\+[1-9]\d{7,14}', phone): return 'Please provide the contact’s phone number with country code, such as plus 91 followed by the number.'
                args = {'contact':phone,'message':args['message']}
                prompt = f'Send this WhatsApp message to {phone}: {args["message"]}? Say yes to confirm, or no to cancel.'
            else: prompt = f'Do you want me to {args["action"]} this computer? Say yes to confirm, or no to cancel.'
            self.pending = {'name':name,'args':dict(args),'prompt':prompt,'expires':time.monotonic()+60}
            return prompt
        if name == 'language':
            self.session.language = args['language']
            return f'Language preference changed to {args["language"]}.'
        if name == 'voice_expression': return getattr(self.session, 'voice_estimate', 'Please speak a sentence first, then ask for voice expression estimation.')
        if name == 'face_expression':
            await self.session.send('camera_request')
            return 'I requested a camera frame for expression estimation. Allow the browser camera prompt to continue.'
        if name == 'iot':
            from .mqtt import MQTTInterface
            return await MQTTInterface().command(args['device'], args['action'])
        raise ValueError('Unknown action')
