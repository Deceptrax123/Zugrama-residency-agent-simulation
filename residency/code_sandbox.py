"""Bounded, no-file/no-network Python worker transport."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

WORKER=Path(__file__).resolve().parents[1]/'scripts/agent_code_worker.py'


def execute(code,timeout=5):
    if not isinstance(code,str) or len(code)>16000:raise ValueError('Use Python code below 16,000 characters')
    child=subprocess.Popen([sys.executable,'-I','-B',str(WORKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        cwd='/tmp',env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'},start_new_session=True,close_fds=True)
    output=bytearray();deadline=time.monotonic()+timeout
    try:
        child.stdin.write(json.dumps({'code':code}).encode());child.stdin.close()
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout,selectors.EVENT_READ)
            while selector.get_map():
                if time.monotonic()>=deadline:return {'ok':False,'error':'Code exceeded wall-clock limit'}
                for key,_ in selector.select(min(.2,max(0,deadline-time.monotonic()))):
                    data=os.read(key.fd,8192)
                    if not data:selector.unregister(key.fileobj);continue
                    output.extend(data)
                    if len(output)>64000:return {'ok':False,'error':'Code exceeded output limit'}
        child.wait(timeout=1)
        if child.returncode:return {'ok':False,'error':'Code worker stopped at a resource limit or sandbox failure','exit_code':child.returncode}
        try:return json.loads(output)
        except ValueError:return {'ok':False,'error':'Code worker returned an invalid result'}
    finally:
        if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait()
        child.stdout.close()
