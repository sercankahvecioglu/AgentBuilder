# wrap_up: pre-close check and outcome selection (close_key). Routers may already have set close_key.
try:
    CL = CONST.get('closing') or dict()
    table = _load('products_json', [])
    promised = _load('promised_json', [])
    key = _s(vars.get('close_key'))
    rows = CL.get('rows') or []
    keys = [_row_key(r.get('outcome'), r.get('reason')) for r in rows]
    if _s(vars.get('transfer_queue')) and CL.get('transfer_wins_over_promise', True):
        pass
    elif promised and CL.get('promise_wins', True):
        key = _s(CL.get('promise_key'))
    elif not key and table:
        # multi-product aggregation from notes
        reasons = [_s(r.get('note_reason')) for r in table]
        agg = CL.get('all_noted_as') or []
        done = False
        for a in agg:
            if reasons and all(x == _s(a.get('note_reason')) for x in reasons):
                key = _row_key(a.get('outcome'), a.get('reason'))
                done = True
                break
        if not done:
            skip = CL.get('else_skip_reasons') or []
            for r in reasons:
                if r and r not in skip:
                    key = _row_key(CL.get('else_outcome'), r)
                    break
    if key not in keys:
        key = _s(CL.get('fallback_key'))
    vars['close_key'] = key
    if _s(vars.get('goodbye_done')) == 'yes':
        vars['wrap_next'] = 'pre_close'
    else:
        vars['wrap_next'] = 'goodbye'
except Exception as e:
    vars['close_key'] = _s(CONST.get('closing', dict()).get('fallback_key'))
    vars['wrap_next'] = 'goodbye'
    vars['snippet_error'] = 'wrap_up: ' + str(e)
