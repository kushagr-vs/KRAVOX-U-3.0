"""Generate the requested complete code listing without secrets or private logs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.py','.js','.jsx','.css','.mjs','.json','.txt','.html','.md'}
EXCLUDE = {'node_modules','dist','public','__pycache__','models'}

def sources():
    for name in ['.gitignore','kravox.py','kravox_core.py','kravox_gui.py','test.py','requirements.txt',
                 'README.md','PROTOCOL.md','TEST_CHECKLIST.md','FILE_MANIFEST.md']:
        path = ROOT / name
        if path.exists(): yield path
    for directory in ['backend','frontend','scripts','tests']:
        for path in sorted((ROOT/directory).rglob('*')):
            if path.is_file() and not any(part in EXCLUDE for part in path.relative_to(ROOT/directory).parts):
                if path.name == '.env.example' or (path.suffix in EXTENSIONS and path.name not in ('contacts.json',)):
                    yield path

def main():
    paths = list(sources())
    output = ['# Full source delivery\n\nEach new or changed source file is included below. Credentials, personal data, binaries and generated dependencies are excluded. See FILE_MANIFEST.md for those artifacts.\n']
    for path in paths:
        suffix = path.suffix.lstrip('.')
        language = {'py':'python','jsx':'jsx','mjs':'javascript','js':'javascript','example':'dotenv'}.get(suffix, suffix)
        code = path.read_text(encoding='utf-8-sig')
        # Four backticks allow source Markdown to contain ordinary fenced examples.
        output.append(f'\n## `{path.relative_to(ROOT).as_posix()}`\n\n````{language}\n{code.rstrip()}\n````\n')
    (ROOT/'SOURCE_DELIVERY.md').write_text(''.join(output), encoding='utf-8')
    print(f'Exported {len(paths)} files; credentials excluded.')

if __name__ == '__main__': main()
