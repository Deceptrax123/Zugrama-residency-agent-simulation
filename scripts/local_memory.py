"""Start/stop the dedicated local GPU memory stack; benchmark uses synthetic data."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from residency.local_mem0 import LocalMemoryClient
DATA=ROOT/'.data/local-memory'


def private(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as handle: json.dump(value,handle,indent=2)


def init():
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not (DATA/'service.json').exists():
        private(DATA/'service.json',{'url':'http://127.0.0.1:7371','key':secrets.token_urlsafe(36)})
    key=json.loads((DATA/'service.json').read_text())['key']
    fd=os.open(DATA/'inference.key',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as handle:handle.write(key+'\n')


def environment():
    # No cloud keys, personal provider settings, proxy, or global cache changes.
    allowed=('PATH','LANG','LC_ALL','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES')
    env={key:os.environ[key] for key in allowed if key in os.environ}
    lib=ROOT/'.tools/ollama-local/lib/ollama'
    env.update(MEM0_TELEMETRY='false',MEM0_DIR=str(DATA/'mem0-home'),
               CUDA_CACHE_PATH=str(DATA/'cuda-cache'),XDG_CACHE_HOME=str(DATA/'cache'),
               GGML_BACKEND_PATH=str(lib/'cuda_v13/libggml-cuda.so'),
               LD_LIBRARY_PATH=str(lib/'cuda_v13')+':'+str(lib), PYTHONUNBUFFERED='1')
    return env


def pid():
    try:
        saved=json.loads((DATA/'process.json').read_text())
        args=(Path('/proc')/str(saved['pid'])/'cmdline').read_bytes().split(b'\0')
    except (OSError,ValueError):return None
    return saved['pid'] if str(Path(__file__).resolve()).encode() in args and b'run' in args else None


def run():
    init()
    private(DATA/'process.json',{'pid':os.getpid()})
    stopped=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stopped.set())
    binary=ROOT/'.tools/ollama-local/lib/ollama/llama-server'
    common=['--host','127.0.0.1','--api-key-file',str(DATA/'inference.key'),
            '-ngl','all','-t','4','-np','1','-fa','on']
    commands=[
        [str(binary),'-m',str(ROOT/'.tools/memory-models/qwen3-4b.gguf'),
         '--port','11439','--alias','qwen3-4b','-c','32768','--jinja',
         '--chat-template-file',str(ROOT/'residency/prompts/memory-chat.jinja'),
         '--reasoning','off',*common],
        [str(binary),'-m',str(ROOT/'.tools/memory-models/qwen3-embedding-06b.gguf'),
         '--port','11440','--alias','qwen3-embedding-0.6b','-c','8192',
         '--embedding','--pooling','last',*common],
        [str(ROOT/'.tools/mem0-venv/bin/python'),'-B',str(ROOT/'scripts/memory_service.py')]]
    children=[]
    try:
        for index,command in enumerate(commands):
            if index==2:
                deadline=time.monotonic()+120
                while time.monotonic()<deadline and not stopped.is_set():
                    try:
                        for port in (11439,11440):
                            urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=2).read()
                        break
                    except OSError:stopped.wait(.5)
                else:raise RuntimeError('GPU inference endpoints did not become ready')
            with (DATA/f'worker-{index}.log').open('ab') as log:
                children.append(subprocess.Popen(command,cwd=ROOT,env=environment(),
                    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT))
        while not stopped.wait(.5):
            if any(child.poll() is not None for child in children):
                raise RuntimeError('A local memory worker exited; no automatic restart')
    finally:
        for child in reversed(children):
            if child.poll() is None:child.terminate()
        for child in children:
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill()


def start():
    init()
    if pid():raise ValueError('Local memory stack already running')
    with (DATA/'supervisor.log').open('ab') as log:
        process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'run'],cwd=ROOT,
            env=environment(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    private(DATA/'process.json',{'pid':process.pid})
    return {'status':'starting','pid':process.pid,'data':str(DATA)}


def benchmark():
    client=LocalMemoryClient()
    import hashlib
    scope=hashlib.sha256(('synthetic-benchmark-'+secrets.token_hex(12)).encode()).hexdigest()
    sources=[{'key':'synthetic:1','speaker_id':'synthetic-asha','body':'Synthetic Asha enjoys repairing bicycles and can teach Python. She wants help with interface design.',
              'kind':'joined_conversation','occurred_at':time.time()}]
    before=time.perf_counter();added=client.add(scope,sources,{'instructions':'Remember skills, interests and requests.'})
    add_seconds=time.perf_counter()-before
    times=[]
    for _ in range(3):
        before=time.perf_counter();found=client.search(scope,'Who can teach programming and needs design help?')
        times.append(time.perf_counter()-before)
    if not added.get('results') or not found.get('results'):raise ValueError('Synthetic memory round trip returned no memories')
    report={'synthetic_only':True,'extraction_seconds':round(add_seconds,3),
            'search_seconds':[round(t,3) for t in times],'extracted_memories':len(added['results']),
            'retrieved_memories':len(found['results']), 'hosted_comparison':'Not measured; no hosted credentials used'}
    private(DATA/'benchmark.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('init','start','run','status','stop','benchmark'))
    args=parser.parse_args()
    if args.command=='run':return run()
    if args.command=='init':init();result={'status':'configured'}
    elif args.command=='start':result=start()
    elif args.command=='stop':
        current=pid()
        if not current:raise SystemExit('No verified local-memory supervisor; nothing signalled')
        os.kill(current,signal.SIGTERM);result={'status':'shutdown_requested'}
    elif args.command=='benchmark':result=benchmark()
    else:
        result={'running':bool(pid())}
        if result['running']:
            try:result.update(LocalMemoryClient().health())
            except Exception:result['status']='starting_or_unavailable'
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
