# offer_router: after the customer answers a one-time offer or check (ask_once_first intents).
try:
    key = _s(vars.get('offer_key'))
    _pause()
    it = _intent(key) or dict()
    reply = _s(vars.get('offer_reply')).lower()
    vars['offer_reply'] = 'none'
    nxt = 'offer'
    resume = _s(vars.get('offer_resume')) or 'negotiate'
    if reply == 'none':
        n = _i(vars.get('offer_asks')) + 1
        vars['offer_asks'] = str(n)
        if n >= 2:
            reply = 'declines'
        else:
            vars['offer_hint'] = 'The answer was unclear. Ask only whether that was a yes or a no. Do not repeat or rephrase the offer and add nothing else.'
    if reply == 'accepts':
        if it.get('action_kind') == 'transfer' and _s(it.get('action_queue')):
            vars['transfer_queue'] = _s(it.get('action_queue'))
            _set_close(it.get('close_outcome'), it.get('close_reason'), '', 'I will connect you with the ' + _s(it.get('action_queue')) + ' team now.')
            nxt = 'wrap_up'
        elif _s(it.get('close_outcome')):
            _set_close(it.get('close_outcome'), it.get('close_reason'), '')
            nxt = 'wrap_up'
        else:
            vars['resume_hint'] = 'Continue with your last question.'
            vars['resume_node'] = resume
            nxt = 'resume_router'
    elif reply == 'declines':
        if _s(it.get('declined_close_outcome')):
            _set_close(it.get('declined_close_outcome'), it.get('declined_close_reason'), '', 'I understand.')
            nxt = 'wrap_up'
        else:
            vars['resume_hint'] = 'Continue with your last question.'
            vars['resume_node'] = resume
            nxt = 'resume_router'
    vars['offer_next'] = nxt
except Exception as e:
    vars['offer_next'] = 'wrap_up'
    vars['snippet_error'] = 'offer_router: ' + str(e)
