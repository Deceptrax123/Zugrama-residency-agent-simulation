"""Launch the isolated Hermes gateway with residency-only budget guards."""
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'.tools/hermes-agent'))
from residency.gateway_guard import install
install()
sys.argv=['hermes','gateway','run']
runpy.run_module('hermes_cli.main',run_name='__main__')
