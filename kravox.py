"""Kravox 3.0 local web entry point. Run from the project root."""

def main():
    import uvicorn
    uvicorn.run('backend.app:app', host='127.0.0.1', port=8000)

if __name__ == '__main__':
    main()
