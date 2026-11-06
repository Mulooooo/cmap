"""python -m interface [--port 8000] [--host 127.0.0.1]"""

import argparse

import uvicorn

parser = argparse.ArgumentParser(description="Interface web CMAP")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()

print(f"Interface sur http://{args.host}:{args.port}")
uvicorn.run("interface.server:app", host=args.host, port=args.port, log_level="warning")
