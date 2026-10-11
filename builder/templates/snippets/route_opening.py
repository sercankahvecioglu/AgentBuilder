# route_opening: after each customer reply in the opening node.
try:
    if _s(vars.get('stage')) == '':
        vars['stage'] = 'opening'
        vars['confirm_asks'] = '1'
        vars['goodbye_prefix'] = ''
        vars['transfer_queue'] = ''
        vars['close_key'] = ''
        vars['goodbye_done'] = ''
        vars['opening_hint'] = ''
        vars['products_json'] = '[]'
        vars['promised_json'] = '[]'
        vars['notes_json'] = '[]'
        today = _today()
        vars['today_iso'] = today.isoformat()
        vars['today_text'] = _fmt(today)
    who = _s(vars.get('who')).lower()
    _pause()
    vars['who'] = 'none'
    frag = _s(vars.get('fragment')).lower() == 'yes'
    vars['fragment'] = 'no'
    asks = _i(vars.get('confirm_asks'), 1)
    mx = _i(CONST.get('max_confirm_asks'), 2)
    nxt = 'opening'
    if who == 'confirms':
        vars['stage'] = 'identity'
        vars['id_hint'] = ''
        nxt = 'identity_start'
    elif who == 'third_party':
        vars['stage'] = 'third_party'
        vars['tp_hint'] = ''
        vars['cb_asks'] = '0'
        nxt = 'third_party'
    elif who == 'wrong_number':
        tp = CONST.get('third_party') or dict()
        _set_close(tp.get('wrong_number_outcome'), tp.get('wrong_number_reason'), '', 'I apologise for the disturbance.')
        nxt = 'wrap_up'
    elif who == 'deceased':
        tp = CONST.get('third_party') or dict()
        sent = _s(tp.get('deceased_sentence'))
        low = sent.lower().strip()
        instr = low.startswith(('say ', 'tell ', 'express ', 'state ', 'offer '))
        if sent and not instr:
            _set_close(tp.get('deceased_outcome'), tp.get('deceased_reason'), '', sent)
        else:
            _set_close(tp.get('deceased_outcome'), tp.get('deceased_reason'), (sent if instr else 'Express condolences in one sentence.') + ' Ask nothing else.')
        nxt = 'wrap_up'
    elif _intent(who) is not None and not (_intent(who) or dict()).get('continue_call'):
        nxt = _apply_intent(who, 'opening') or 'opening'
        if nxt == 'opening':
            vars['opening_hint'] = 'Ask the confirmation question again.'
    elif who == 'asks_question' or _intent(who) is not None:
        ans = 'Answer the question briefly'
        it = _intent(who)
        if it is not None and _s(it.get('say_text')):
            ans = _s(it.get('say_text')).rstrip('.')
        if asks >= mx:
            vars['opening_hint'] = ans + ', then ask the confirmation question one last time.'
        else:
            vars['opening_hint'] = ans + ', then ask the confirmation question again.'
        vars['confirm_asks'] = str(asks + 1)
        if asks > mx:
            op = CONST.get('opening') or dict()
            _set_close(op.get('unclear_outcome'), op.get('unclear_reason'), 'Answer the question briefly. Say you could not confirm who is on the line.')
            nxt = 'wrap_up'
    elif frag and _i(vars.get('opening_frag')) < 2:
        # a cut-off reply is heard again before it counts as an ask
        vars['opening_frag'] = str(_i(vars.get('opening_frag')) + 1)
        vars['opening_hint'] = 'The reply was cut off. Ask the confirmation question again, exactly as before.'
        if CONST.get('opening_again'):
            nxt = 'opening_again'
    else:
        if asks >= mx:
            op = CONST.get('opening') or dict()
            _set_close(op.get('unclear_outcome'), op.get('unclear_reason'), '', 'I could not confirm who is on the line.')
            nxt = 'wrap_up'
        else:
            vars['confirm_asks'] = str(asks + 1)
            vars['opening_hint'] = 'The reply did not confirm who is speaking. Ask the confirmation question again, exactly as before.'
            if CONST.get('opening_again'):
                nxt = 'opening_again'
    vars['opening_next'] = nxt
except Exception as e:
    vars['opening_next'] = 'opening'
    vars['opening_hint'] = 'Ask the confirmation question again.'
    vars['snippet_error'] = 'route_opening: ' + str(e)
