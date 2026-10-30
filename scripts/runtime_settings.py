"""Production gateway settings without depending on a test sandbox's data."""
from pathlib import Path
from residency.config import Settings
from host import read_env
ROOT=Path(__file__).resolve().parents[1]


def gateway_settings(data_dir,join_code,origin='http://127.0.0.1:7380',model=None,reasoning_effort=None):
    env=read_env(ROOT/'.env')
    selected=model if model is not None else env.get('HERMES_MODEL')
    if selected not in ('gpt-5.6-terra','gpt-6.1-sol'):raise ValueError('Configure an approved residency model explicitly; no fallback is allowed')
    return Settings(data_dir=data_dir,join_code=join_code,public_origin=origin,
        hermes_url=env.get('HERMES_API_URL','http://127.0.0.1:8642'),hermes_key=env.get('HERMES_API_KEY',''),
        hermes_model=selected,hermes_reasoning_effort=reasoning_effort,hermes_timeout=180)
