"""Post-event export and model analysis; never starts or resumes the simulation."""
import argparse,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from residency.final_results import export_bundle,analyze
from residency.hermes import Hermes
from runtime_settings import gateway_settings
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=('export','analyze'));args=p.parse_args();setup=json.loads((ROOT/'.data/live-residency/setup.json').read_text());state=json.loads((ROOT/'.data/live-residency/state/host-event/state.json').read_text());assert state['status'] not in ('running','stopping') and not state.get('thinking');base=ROOT/'.data/live-residency/final-results'/state['event_id']
 if args.command=='export':b=export_bundle(base);print(json.dumps({'runs':len(b['runs']),'messages':sum(len(r['messages']) for r in b['runs'])}))
 else:analyze(base,Hermes(gateway_settings(ROOT/'.data/live-residency/state',setup['join_code'],model='gpt-6.1-sol',reasoning_effort='high')))
