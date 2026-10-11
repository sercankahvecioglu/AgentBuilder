# readback_router: after the customer answers the read-back.
try:
    rb = _s(vars.get('rb')).lower()
    _pause()
    vars['rb'] = 'none'
    table = _load('products_json', [])
    idx = _i(vars.get('cur_idx'))
    p = table[idx] if idx < len(table) else None
    nxt = 'readback'
    frag = _s(vars.get('fragment')).lower() == 'yes'
    vars['fragment'] = 'no'
    if frag and rb != 'confirms' and _i(vars.get('rb_asks')) < 4:
        # a cut-off answer to the read-back is not a change or a refusal: ask again for a clear answer
        rb = 'none'
    if rb == 'confirms':
        nxt = 'promise_guard'
    elif rb == 'changes':
        # the read-back was not accepted: every agreed product goes back to open; the named product gets the change first
        k = 0
        while k < len(table):
            q = table[k]
            if q.get('status') == 'agreed':
                q['status'] = 'open'
                q['pending_amount'] = _f(q.get('agreed_amount'))
                q['deadline_note'] = ''
            k += 1
        _save('products_json', table)
        vars['nego_cmd'] = 'proposes'
        vars['stage'] = 'negotiation'
        nxt = 'negotiation_router'
    elif rb == 'refuses':
        if p is not None:
            p['status'] = 'open'
            table[idx] = p
            _save('products_json', table)
        vars['nego_cmd'] = 'refuses'
        vars['stage'] = 'negotiation'
        _reset_date_parts()
        nxt = 'negotiation_router'
    elif rb == 'asks_question' or _intent(rb) is not None:
        vars['nego_cmd'] = rb
        vars['stage'] = 'negotiation'
        nxt = 'negotiation_router'
    else:
        n = _i(vars.get('rb_asks')) + 1
        vars['rb_asks'] = str(n)
        if n >= 5:
            vars['nego_cmd'] = 'no_answer'
            vars['stage'] = 'negotiation'
            _reset_date_parts()
            nxt = 'negotiation_router'
        else:
            vars['rb_hint'] = 'The answer was not a clear yes or no. Read the promise back again and ask for a clear yes.'
            if CONST.get('rb_again'):
                nxt = 'readback_again'
    vars['rb_next'] = nxt
except Exception as e:
    vars['rb_next'] = 'readback'
    vars['snippet_error'] = 'readback_router: ' + str(e)
