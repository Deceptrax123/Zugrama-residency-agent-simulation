"""Pure configuration for the residency's dedicated Hermes gateway."""
from copy import deepcopy
import re


def configure_gateway(original, provider=None, model=None):
    if provider is not None and provider not in ('nous', 'openai-codex'):
        raise ValueError('Choose nous or openai-codex for this dedicated gateway')
    if model is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9:._/\-]{0,150}', model):
        raise ValueError('Invalid model identifier')
    config = deepcopy(original)
    chosen = config.setdefault('model', {})
    if provider is not None:
        if chosen.get('provider') != provider:
            chosen.pop('base_url', None)
        chosen['provider'] = provider
    else:
        chosen.setdefault('provider', 'nous')
    if model is not None:
        chosen['default'] = model
    chosen['openai_runtime'] = 'auto'  # Native Hermes loop; no Codex app-server tools.
    config.setdefault('platform_toolsets', {})['api_server'] = []
    config.setdefault('memory', {}).update(memory_enabled=False, user_profile_enabled=False)
    config.setdefault('auxiliary', {}).setdefault('background_review', {})['enabled'] = False
    config['auxiliary'].setdefault('title_generation', {})['enabled'] = False
    config['fallback_providers'] = []
    config.pop('fallback_model', None)
    if model is not None:
        extra = config.setdefault('platforms', {}).setdefault('api_server', {}).setdefault('extra', {})
        extra['model_routes'] = {model: {'model': model, 'provider': chosen['provider']}}
    return config
