"""Validated local entry point: python run_server.py."""
import os
from preflight import check_sources

if __name__ == '__main__':
    check_sources()
    import uvicorn
    uvicorn.run('server:app', host=os.getenv('HOST', '127.0.0.1'),
                port=int(os.getenv('PORT', '8000')), ws_max_size=2 * 1024 * 1024)
