"""Install budget bounds only in the residency's isolated gateway process.

Codex subscription routes strip max_output_tokens. Reserve the documented full
128k output instead. Limit the complete serialized native input to 128 KiB,
allow another 8192 input tokens for framing, and reject additional native calls
on the same transport. $1.90 covers uncached input including a 1.25x cache-write
allowance and the full possible output at the published standard Terra rates.
The approved GPT-6.1 Sol route fits within the same conservative reservation.
"""
import json
import threading

GUARD = 'residency-usd-v1'
MAX_INPUT_BYTES = 131072


def bound_native(kwargs):
    if kwargs.get('model') not in ('gpt-5.6-terra','gpt-6.1-sol'):
        raise RuntimeError('Residency budget guard requires an explicitly approved model route')
    if kwargs.get('previous_response_id') or kwargs.get('tools'):
        raise RuntimeError('Residency budget guard requires explicit input and no tools')
    if kwargs.get('service_tier') not in (None,'auto','default'):
        raise RuntimeError('Residency budgets use standard pricing only')
    raw=json.dumps(kwargs,ensure_ascii=False,default=str).encode('utf-8')
    if len(raw)>MAX_INPUT_BYTES:
        raise RuntimeError('Residency native input exceeds the budget guard; no provider call was sent')
    return kwargs


def install():
    from agent.transports.codex import ResponsesApiTransport
    from gateway.platforms.api_server import APIServerAdapter
    from aiohttp import web
    from agent import codex_runtime
    from .provider_limits import quota_detail
    original_stream=codex_runtime.run_codex_stream
    quota_by_session={}
    quota_lock=threading.Lock()

    def stream(agent,*args,**kwargs):
        try:return original_stream(agent,*args,**kwargs)
        except Exception as exc:
            detail=quota_detail(exc)
            if detail:
                with quota_lock:quota_by_session[str(getattr(agent,"session_id",""))]=detail
            raise
    codex_runtime.run_codex_stream=stream
    original_chat=APIServerAdapter._handle_chat_completions

    async def chat(self,request):
        response=await original_chat(self,request)
        session=request.headers.get("X-Hermes-Session-Id","")
        with quota_lock:detail=quota_by_session.pop(session,None)
        if detail and getattr(response,"body",None):
            data=json.loads(response.body)
            data["residency_provider_error"]=detail
            return web.json_response(data,status=response.status)
        return response
    APIServerAdapter._handle_chat_completions=chat
    original_build=ResponsesApiTransport.build_kwargs
    gate=threading.Lock()

    def build(self,*args,**kwargs):
        with gate:
            if getattr(self,'_residency_dispatched',False):
                raise RuntimeError('Residency budget guard blocks repeat provider dispatch')
            result=bound_native(original_build(self,*args,**kwargs))
            self._residency_dispatched=True
            return result
    ResponsesApiTransport.build_kwargs=build
    original_create=APIServerAdapter._create_agent

    def create(self,*args,**kwargs):
        agent=original_create(self,*args,**kwargs)
        agent.max_iterations=1
        agent._api_max_retries=1
        if agent.client is not None:
            agent.client=agent.client.with_options(max_retries=0)
        return agent
    APIServerAdapter._create_agent=create
    original_health=APIServerAdapter._handle_health

    async def health(self,request):
        response=await original_health(self,request)
        data=json.loads(response.body)
        data['residency_budget_guard']=GUARD
        return web.json_response(data)
    APIServerAdapter._handle_health=health
