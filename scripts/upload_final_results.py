"""Upload a verified frozen report through the host-authenticated Sites endpoint."""
from pathlib import Path
import argparse,hashlib,json,sys,urllib.request
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local',action='store_true',help='Use the owned local preview on port 7396')
    args=parser.parse_args()
    base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64'
    content=(base/'presentation.json').read_bytes();integrity=json.loads((base/'integrity.json').read_text())
    assert integrity['passed'] and integrity['presentation_sha256']==hashlib.sha256(content).hexdigest(),'Revalidate this exact presentation before uploading'
    if args.local:
        origin='http://127.0.0.1:7396'
        values={}
        for line in (ROOT/'onboarding_site/.dev.vars').read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep:values[key.strip()]=value.strip().strip('\"\'')
        token=values['RESIDENCY_HOST_TOKEN'];code='ABCD-EFGH-IJKL-MNOP'
    else:
        access=json.loads((ROOT/'.data/participant-launch/hosted-access.json').read_text())
        watch=json.loads((ROOT/'.data/live-residency/watch-access.json').read_text())
        origin=watch['origin'].rstrip('/');code=watch['code']
        # Generated hosted-access records keep the host bearer in the host link.
        from urllib.parse import urlsplit,parse_qs
        link=access.get('host_url') or access.get('host_link')
        token=access.get('host_token') or access.get('host_key')
        if not token and link:
            part=urlsplit(link);fragment=parse_qs(part.fragment);token=(fragment.get('key') or fragment.get('host') or [None])[0]
        if not token:raise SystemExit('No recognized host credential field; inspect the private access schema locally')
        if not origin.startswith('https://'):raise SystemExit('Production report requires HTTPS')
    req=urllib.request.Request(origin+'/api/results',data=content,headers={'Authorization':'Bearer '+token,'Origin':origin,'Content-Type':'application/json','User-Agent':'Mozilla/5.0 (Zugrama Report Publisher)'})
    with urllib.request.urlopen(req,timeout=120) as response:receipt=json.load(response)
    assert receipt.get('saved') and receipt['sha256']==hashlib.sha256(content).hexdigest()
    get=urllib.request.Request(origin+'/api/results',headers={'X-Watch-Code':code,'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(get,timeout=120) as response:readback=response.read()
    assert hashlib.sha256(readback).hexdigest()==receipt['sha256'],'Published report differs from verified content'
    receipt['origin']=origin;(base/('local-upload.json' if args.local else 'published-report.json')).write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
