# wrap_up: pre-close check, notes to write, outcome selection (close_key). Routers may already have set close_key.
try:
    CL = CONST.get('closing') or dict()
    MULTI = bool(CONST.get('multi'))
    table = _load('products_json', [])
    promised = _load('promised_json', [])
    key = _s(vars.get('close_key'))
    rows = CL.get('rows') or []
    keys = [_row_key(r.get('outcome'), r.get('reason')) for r in rows]
    note_reasons = CL.get('note_reasons') or []
    transfer = _s(vars.get('transfer_queue')) != ''
    # products without a promise get a note reason (multi-product): from the router, or from the close reason
    if MULTI and CL.get('note_unpromised') and not transfer:
        close_reason = ''
        if key:
            for r in rows:
                if _row_key(r.get('outcome'), r.get('reason')) == key:
                    close_reason = _s(r.get('reason'))
        for row in table:
            if row.get('status') in ('promised',):
                continue
            if not _s(row.get('note_reason')):
                if close_reason in note_reasons:
                    row['note_reason'] = close_reason
                elif row.get('status') == 'failed' and _s(CL.get('failure_note_reason')) in note_reasons:
                    row['note_reason'] = _s(CL.get('failure_note_reason'))
                elif _s(CL.get('exhausted_note_reason')) in note_reasons:
                    row['note_reason'] = _s(CL.get('exhausted_note_reason'))
        _save('products_json', table)
    if transfer and CL.get('transfer_wins_over_promise', True):
        pass
    elif promised and CL.get('promise_wins', True):
        key = _s(CL.get('promise_key'))
    elif MULTI and table and not transfer:
        reasons = [_s(r.get('note_reason')) for r in table if r.get('status') != 'promised']
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
                if r and r not in skip and _row_key(CL.get('else_outcome'), r) in keys:
                    key = _row_key(CL.get('else_outcome'), r)
                    break
    if key not in keys:
        key = _s(CL.get('fallback_key'))
    vars['close_key'] = key
    # notes still to write (never on a transfer)
    todo = []
    if MULTI and CL.get('note_unpromised') and not transfer:
        for row in table:
            if row.get('status') != 'promised' and _s(row.get('note_reason')) and not row.get('noted'):
                todo.append(row)
    if todo:
        row = todo[0]
        vars['note_product'] = _s(row.get('id'))
        vars['note_reason'] = _s(row.get('note_reason'))
        vars['note_status'] = ''
        row['noted'] = 1
        _save('products_json', table)
        vars['wrap_next'] = 'do_note'
    elif _s(vars.get('goodbye_done')) == 'yes':
        vars['wrap_next'] = 'pre_close'
    elif _s(vars.get('goodbye_say')) and not _s(vars.get('goodbye_prefix')):
        vars['wrap_next'] = 'goodbye_tts'
    else:
        vars['wrap_next'] = 'goodbye'
except Exception as e:
    vars['close_key'] = _s(CONST.get('closing', dict()).get('fallback_key'))
    vars['wrap_next'] = 'goodbye'
    vars['snippet_error'] = 'wrap_up: ' + str(e)
