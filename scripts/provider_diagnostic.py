"""Print only provider status and model IDs, never credentials or response bodies."""
import asyncio
import httpx
from backend.config import PROVIDERS

async def main():
    for name, url, model, key in PROVIDERS:
        if not key: print(name, 'not configured'); continue
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                result = await client.get(url + '/models', headers={'Authorization':f'Bearer {key}'})
                print(name, 'models status', result.status_code, 'configured model', model)
                if result.is_success:
                    models = [m['id'] for m in result.json().get('data', [])]
                    print('Available models:', ', '.join(models[:30]))
        except Exception as exc: print(name, type(exc).__name__)

if __name__ == '__main__': asyncio.run(main())
