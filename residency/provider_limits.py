"""Provider quota signals; distinct from per-resident allowance decisions."""
from .store import AppError

class ProviderQuotaPause(AppError):
    def __init__(self,detail=None):
        super().__init__('Provider usage limit reached. Networking is paused; resume after credits or quota are available.',429)
        self.detail=detail or {'code':'usage_limit_reached'}


def quota_detail(error):
    body=getattr(error,'body',None)
    if not isinstance(body,dict):return None
    data=body.get('error',body)
    if not isinstance(data,dict):return None
    if not {data.get('type'),data.get('code')}&{'usage_limit_reached','insufficient_quota'}:return None
    result={'code':data.get('type') if data.get('type') in ('usage_limit_reached','insufficient_quota') else data.get('code'),'message':'Provider usage limit reached','status':429}
    reset=data.get('resets_at')
    if type(reset) in (int,float) and reset>0:result['resets_at']=reset
    return result


def check_completion(response):
    detail=response.get('residency_provider_error') if isinstance(response,dict) else None
    if isinstance(detail,dict) and detail.get('code') in ('usage_limit_reached','insufficient_quota'):
        raise ProviderQuotaPause(detail)
    hermes=response.get('hermes',{}) if isinstance(response,dict) else {}
    if hermes.get('failed'):
        raise AppError('Provider did not complete this request. No automatic retry or model fallback was made.',502)
