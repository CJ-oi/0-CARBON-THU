from __future__ import annotations

import http.server
import socketserver
from functools import partial
from pathlib import Path


def serve(directory: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with socketserver.ThreadingTCPServer((host, port), handler) as server:
        print(f"Serving {directory} at http://{host}:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped")
