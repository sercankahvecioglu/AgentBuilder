# promise_result: after the create_promise api node. One retry, then the failure policy.
try:
    REC = CONST.get('recording') or dict()
    table = _load('products_json', [])
    idx = _i(vars.get('cur_idx'))
    p = table[idx] if idx < len(table) else None
    st = _s(vars.get('pr_status'))
    nxt = 'wrap_up'
    if st == 'ok':
        if p is not None:
            p['status'] = 'promised'
            table[idx] = p
            _save('products_json', table)
            promised = _load('promised_json', [])
            promised.append(dict(id=_s(p.get('id')), amount=_f(p.get('agreed_amount')), date=_s(p.get('agreed_date'))))
            _save('promised_json', promised)
        nxt = 'promise_guard'
        more = False
        for row in table:
            if row.get('status') == 'agreed':
                more = True
        if not more:
            nxt = 'say_recorded'
    else:
        n = _i(vars.get('pr_attempts')) + 1
        vars['pr_attempts'] = str(n)
        if n < _i(REC.get('max_attempts'), 2):
            vars['pr_status'] = ''
            nxt = 'do_promise'
        else:
            if p is not None:
                p['status'] = 'failed'
                p['note_reason'] = _s(REC.get('failure_note_reason'))
                table[idx] = p
                _save('products_json', table)
            vars['write_failed'] = 'yes'
            if not CONST.get('multi'):
                _set_close(REC.get('failure_outcome'), REC.get('failure_reason'), _s(REC.get('failure_say')))
            nxt = 'promise_guard'
            more = False
            for row in table:
                if row.get('status') == 'agreed':
                    more = True
            if not more:
                nxt = 'wrap_up'
    vars['prs_next'] = nxt
except Exception as e:
    vars['prs_next'] = 'wrap_up'
    vars['snippet_error'] = 'promise_result: ' + str(e)
