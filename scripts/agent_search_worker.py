"""Explicit free Exa search using the installed Hermes provider; no paid fallback."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.tools/hermes-agent'))
from plugins.web.keyless_mcp import exa_search_keyless

if __name__=='__main__':
    payload=json.loads(sys.stdin.read(2000))
    print(json.dumps(exa_search_keyless(payload['query'],payload['limit']),ensure_ascii=False))
