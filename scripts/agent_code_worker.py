"""One isolated Python evaluation. Fails closed if kernel filtering is unavailable.

The trusted loader preloads advertised standard-library modules, closes extra
descriptors, drops privilege gains, installs a syscall allowlist and hard resource
limits, then executes the supplied code. No file or network syscalls are allowed.
"""
import collections
import contextlib
import ctypes
import ctypes.util
import decimal
import fractions
import functools
import io
import itertools
import json
import math
import cmath
import operator
import os
import random
import resource
import statistics
import sys


def restrict():
    name=ctypes.util.find_library('seccomp')
    if not name:raise RuntimeError('Kernel sandbox library unavailable')
    seccomp=ctypes.CDLL(name,use_errno=True);libc=ctypes.CDLL(None,use_errno=True)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(2,2))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    resource.setrlimit(resource.RLIMIT_NOFILE,(16,16))
    resource.setrlimit(resource.RLIMIT_NPROC,(0,0))
    os.closerange(3,1024)
    seccomp.seccomp_init.argtypes=[ctypes.c_uint32];seccomp.seccomp_init.restype=ctypes.c_void_p
    seccomp.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    seccomp.seccomp_load.argtypes=[ctypes.c_void_p];seccomp.seccomp_release.argtypes=[ctypes.c_void_p]
    seccomp.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];seccomp.seccomp_syscall_resolve_name.restype=ctypes.c_int
    if libc.prctl(38,1,0,0,0)!=0:raise RuntimeError('Cannot prevent privilege gains')
    # Default EPERM, including open/openat, exec, fork/clone, sockets, ptrace,
    # process signalling and attempts to change the filter or resource limits.
    filter=seccomp.seccomp_init(0x00050000|1)
    if not filter:raise RuntimeError('Cannot create kernel sandbox')
    try:
        for name in ('read','write','writev','close','exit','exit_group','brk','mmap','munmap','mremap','mprotect','madvise',
                     'rt_sigaction','rt_sigprocmask','rt_sigreturn','sigaltstack','clock_gettime','clock_getres','futex','sched_yield','getpid','gettid','getrandom'):
            syscall=seccomp.seccomp_syscall_resolve_name(name.encode())
            if syscall>=0 and seccomp.seccomp_rule_add(filter,0x7fff0000,syscall,0)!=0:raise RuntimeError('Cannot configure kernel sandbox')
        if seccomp.seccomp_load(filter)!=0:raise RuntimeError('Cannot activate kernel sandbox')
    finally:seccomp.seccomp_release(filter)


class Output:
    def __init__(self):self.text='';self.truncated=False
    def write(self,value):
        value=str(value);remaining=8000-len(self.text)
        self.text+=value[:max(0,remaining)];self.truncated|=len(value)>remaining
        return len(value)
    def flush(self):pass


def main():
    raw=sys.stdin.buffer.read(24001)
    if len(raw)>24000:raise ValueError('Code packet too large')
    payload=json.loads(raw);code=payload['code']
    if not isinstance(code,str) or len(code)>16000:raise ValueError('Use code below 16,000 characters')
    namespace={'__name__':'__residency_code__',**{m.__name__:m for m in (math,cmath,statistics,decimal,fractions,itertools,functools,collections,operator,random,json)}}
    output=Output();restrict()
    try:
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):exec(compile(code,'<resident-code>','exec'),namespace,namespace)
        result={'ok':True,'stdout':output.text,'truncated':output.truncated,'result':namespace.get('result'),'sandbox':'python-seccomp-v1'}
        encoded=json.dumps(result,ensure_ascii=False,allow_nan=False,default=lambda x:str(x)[:1000])
        if len(encoded.encode())>32000:encoded=json.dumps({'ok':False,'error':'Result exceeds output limit','stdout':output.text[:1000],'sandbox':'python-seccomp-v1'})
    except BaseException as error:encoded=json.dumps({'ok':False,'error':type(error).__name__+': '+str(error)[:1000],'stdout':output.text,'sandbox':'python-seccomp-v1'},ensure_ascii=False)
    sys.__stdout__.write(encoded);sys.__stdout__.flush()


if __name__=='__main__':main()
