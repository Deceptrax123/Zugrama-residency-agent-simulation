"""Repair retrospective packets affected by native input normalization. No event writes."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,sys,shutil,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from residency.final_results import load,save,compact,ReportModel,ROOM_SYSTEM,check_refs,cited_complete,validate_assessment
from residency.hermes import Hermes
from residency.report_transport import request_coverage,check_answer_exposure
from runtime_settings import gateway_settings

def main():
    base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64'
    bundle=load(base/'bundle.json');run=next(r for r in bundle['runs'] if r['id']==bundle['current_event_id'])
    setup=load(ROOT/'.data/live-residency/setup.json')
    model=ReportModel(base,Hermes(gateway_settings(ROOT/'.data/live-residency/state',setup['join_code'],model='gpt-6.1-sol',reasoning_effort='high')),budget_usd=25)
    proof_context={'synthetic_rows':[{'ordinal':n,'text':'ordinary synthetic filler '*40} for n in range(78)],'tail_sentinel':'zugrama-native-json-tail-20261030'}
    def proof_valid(value):
        if value!={'tail_sentinel':proof_context['tail_sentinel'],'rows':78}:raise ValueError('Native tail did not survive transport')
        return value
    model.complete('transport-json-synthetic-proof','Integration test only. Return JSON with the exact tail_sentinel from the input and rows equal to the synthetic_rows array length. Ignore filler. Do not use tools.',proof_context,proof_valid)
    progress={'status':'running','room_batches':0,'questionnaires':0,'errors':[]};save(base/'transport-repair-progress.json',progress)
    # Every retained quote in the first questionnaire was checked against what
    # the actual native parser could receive, not merely the application log.
    q1coverage={}
    for path in (base/'assessments').glob('*/ANSWER.json'):
        answer=load(path)
        for response_path in (base/'model').glob('*'+path.parent.name+'*/response.json'):
            try:
                raw=json.loads(load(response_path)['choices'][0]['message']['content'])
                if raw.get('networking',raw)!=answer['networking']:continue
            except (ValueError,KeyError,TypeError):continue
            q1coverage[path.parent.name]=check_answer_exposure(response_path.parent,[v for k,v in answer['networking'].items() if k!='ranking']);break
        if path.parent.name not in q1coverage:raise ValueError('Cannot establish original Q1 request provenance')
    save(base/'questionnaire-native-coverage.json',{'networking':q1coverage})
    jobs=[]
    for path in (base/'model').glob('rooms-*/request.json'):
        if path.parent.name.endswith('-correction'):continue
        context=json.loads(load(path)['messages'][-1]['content'])
        if len(compact(context))>65536:jobs.append(('rooms',path.parent.name,context))
    for path in (base/'assessments').glob('*/ANSWER.json'):
        directory=base/'model'/('assessment2-'+path.parent.name)
        if request_coverage(directory).get('reference_guide')!='full':jobs.append(('questionnaire',path.parent.name,directory))
    def job(kind,key,context):
        if kind=='rooms':
            rooms=context['rooms'];sources=[m for r in rooms for m in r['messages']]
            def valid(value):
                if set(value)!={'rooms'} or [r['room_id'] for r in value['rooms']]!=[r['room_id'] for r in rooms]:raise ValueError('Missing/reordered repaired room')
                return check_refs(value,sources,run['people'],[r['room_id'] for r in rooms],[a['id'] for r in rooms for a in r['artifacts']])
            value=cited_complete(model,'transport-safe-'+key,ROOM_SYSTEM,context,valid,sources)
            return kind,key,value
        directory=context;request=load(directory/'request.json');context=json.loads(request['messages'][-1]['content'])
        answer=load(base/'assessments'/key/'ANSWER.json')
        questions=load(ROOT/'onboarding_site/lib/questionnaires.json')['questionnaires'];packet={**context,'questionnaires':questions}
        def valid(value):
            placeholder={'favorite':{'answer':'Not assessed','evidence':[]},'ranking':[c['id'] for c in context['contacts']],**{k:{'answer':'Not assessed','evidence':[]} for k in ('skills','interesting','problem_solving','interests')}}
            validate_assessment({'story':{'chapters':[]},'networking':placeholder,'judgment':value},packet);return value
        result=cited_complete(model,'assessment2-transport-safe-'+key,request['messages'][0]['content'],context,valid,context['messages'])
        target=base/'assessments'/key/'ANSWER.json';backup=target.with_name('ANSWER.before-transport-repair.json')
        if not backup.exists():shutil.copyfile(target,backup)
        answer['judgment']=result;answer['judgment_request']='assessment2-transport-safe-'+key;answer['answered_at']=time.time();save(target,answer)
        return kind,key,answer
    repaired={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(job,*args):args[:2] for args in jobs}
        for future in as_completed(futures):
            try:
                kind,key,value=future.result()
                if kind=='rooms':
                    repaired.update({r['room_id']:r for r in value['rooms']});progress['room_batches']+=1
                else:progress['questionnaires']+=1
            except Exception as error:progress['errors'].append({'job':futures[future],'error':str(error)[:300]})
            save(base/'transport-repair-progress.json',progress);print(compact(progress),flush=True)
    if progress['errors']:raise RuntimeError('Transport repair needs review; retained receipts prevent blind retries')
    save(base/'transport-safe-room-overrides.json',repaired)
    run['analysis']['rooms']=[repaired.get(r['room_id'],r) for r in run['analysis']['rooms']]
    run['analysis']['agents']=[load(p) for p in (base/'assessments').glob('*/ANSWER.json')]
    save(base/'bundle.json',bundle)
    from final_synthesis import synthesize
    run['analysis']['event']=synthesize(base,model,run,key_prefix='transport-safe-')
    save(base/'bundle.json',bundle)
    progress['status']='completed';save(base/'transport-repair-progress.json',progress)

if __name__=='__main__':main()
