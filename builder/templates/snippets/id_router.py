# id_router: a non-answer reply in an identity question node (decline, purpose question, human, not talk).
try:
    idc = CONST.get('identity') or dict()
    _pause()
    reply = _s(vars.get('id_reply')).lower()
    vars['id_reply'] = 'none'
    cur = _s(vars.get('id_node')) or 'identity_q0'
    nxt = cur
    if reply == 'chatter':
        vars['id_hint'] = 'Say in a few words that you are listening, then ask the same question again.'
        if CONST.get('id_again'):
            nxt = cur + '_again'
    elif reply == 'asks_why':
        vars['id_hint'] = _s(idc.get('explain_once_text')) + ' Then ask the same question again.'
    elif reply in ('declines', 'asks_purpose'):
        if reply == 'asks_purpose' and not idc.get('purpose_question_counts', True):
            vars['id_hint'] = 'Say you can explain after the security check, then ask the question again.'
        else:
            n = _i(vars.get('id_declines')) + 1
            vars['id_declines'] = str(n)
            if n >= _i(idc.get('max_declines'), 2):
                _set_close(idc.get('decline_outcome'), idc.get('decline_reason'), '', _ph('no_security'))
                nxt = 'wrap_up'
            else:
                vars['id_hint'] = _s(idc.get('explain_once_text')) + ' Then ask the same question again.'
    elif _intent(reply) is not None:
        nxt = _apply_intent(reply, cur) or cur
    else:
        vars['id_hint'] = 'Ask the question again.'
    vars['id_next'] = nxt
except Exception as e:
    vars['id_next'] = _s(vars.get('id_node')) or 'identity_q0'
    vars['snippet_error'] = 'id_router: ' + str(e)
