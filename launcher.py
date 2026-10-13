"""Cross-platform launcher for the prebuilt offline frontend and local backend."""
import importlib.util
import os
from pathlib import Path
import sys
import threading
import webbrowser

root=Path(__file__).resolve().parent
os.chdir(root)
if sys.version_info < (3,13):
    raise SystemExit('Please use Python 3.13 or newer. See README.md.')
if importlib.util.find_spec('uvicorn') is None:
    raise SystemExit('Install dependencies first: python -m pip install -r backend/requirements.txt')
if not (root/'frontend'/'dist'/'index.html').exists():
    raise SystemExit('Build the frontend first: cd frontend && npm ci && npm run build')
if __name__=='__main__':
    import uvicorn
    threading.Timer(1.5,lambda:webbrowser.open('http://127.0.0.1:8000')).start()
    print('AI Bingo Party · http://127.0.0.1:8000 · Ctrl+C to stop')
    uvicorn.run('backend.main:app',host='127.0.0.1',port=8000)
