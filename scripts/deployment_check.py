"""Read-only deployment readiness. Makes no model completion or event Start call."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from live_residency import config,DATA
from residency.hermes import Hermes
from residency.local_mem0 import LocalMemoryClient
from residency.markdown_memory import write_private


def main():
    report={'model_calls':0,'event_started_by_check':False,'checks':{}}
    checks=report['checks']
    for unit in ('zugrama-gateway','zugrama-memory','zugrama-cv-extractor','zugrama-residency'):
        checks[unit]=subprocess.run(['systemctl','--user','is-active',unit+'.service'],text=True,capture_output=True).stdout.strip()
    failures=[]
    try:
        hermes=Hermes(config());checks['hermes']=hermes.check()
        checks['budget_guard']=hermes.request('/health',timeout=5).get('residency_budget_guard')=='residency-usd-v1'
        checks['memory']=LocalMemoryClient().health()
        for port in (11439,11440):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=5) as response:checks[str(port)]=response.status==200
        with urllib.request.urlopen('http://127.0.0.1:7380/healthz',timeout=5) as response:checks['frontend_backend']=json.load(response)
        with urllib.request.urlopen('http://127.0.0.1:7380/api/setup',timeout=5) as response:checks['host_setup']=json.load(response)
        with sqlite3.connect('file:'+str(DATA/'state/residency.sqlite3')+'?mode=ro',uri=True) as db:report['enrolled_residents']=db.execute('SELECT count(*) FROM agent_identities').fetchone()[0]
        path=DATA/'state/host-event/state.json'
        if path.exists():
            event=json.loads(path.read_text());report['event']={key:event.get(key) for key in ('status','calls','completed_calls','message_count')}
        else:report['event']={'status':'not_started','calls':0}
        if (DATA/'site-bridge.json').exists():
            status=json.loads((DATA/'site-bridge-status.json').read_text())
            checks['hosted_access_bridge']={'connected':status.get('connected') is True,'fresh':time.time()-status.get('at',0)<90}
            if not all(checks['hosted_access_bridge'].values()):failures.append('Hosted residency access is disconnected or stale')
    except Exception as exc:failures.append(str(exc))
    if any(checks.get(unit)!='active' for unit in ('zugrama-gateway','zugrama-memory','zugrama-cv-extractor','zugrama-residency')):failures.append('One or more supervised services are inactive')
    if checks.get('budget_guard') is not True:failures.append('Budget guard unavailable')
    report.update(passed=not failures,failures=failures)
    write_private(ROOT/'test-results/deployment-readiness.json',json.dumps(report,indent=2));print(json.dumps(report,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':sys.exit(main())
