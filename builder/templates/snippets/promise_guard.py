# promise_guard: validates the agreed values of the next agreed product and bakes them for the write.
try:
    today = _today()
    table = _load('products_json', [])
    nxt = 'wrap_up'
    chosen = -1
    k = 0
    while k < len(table):
        if table[k].get('status') == 'agreed':
            chosen = k
            break
        k += 1
    if chosen >= 0:
        p = table[chosen]
        d = _d(p.get('agreed_date'))
        amount = _f(p.get('agreed_amount'))
        dl = _d(p.get('deadline')) or today
        ok = d is not None and d >= today and _is_bd(d) and d <= dl
        ok = ok and amount >= _f(p.get('floor')) - 0.005 and amount <= _f(p.get('past_due')) + 0.005
        if ok:
            vars['p_product'] = _s(p.get('id'))
            vars['p_amount'] = amount
            vars['p_date'] = d.isoformat()
            vars['pr_status'] = ''
            vars['pr_attempts'] = '0'
            vars['cur_idx'] = str(chosen)
            nxt = 'do_promise'
        else:
            p['status'] = 'open'
            p['pending_amount'] = amount
            table[chosen] = p
            _save('products_json', table)
            vars['cur_idx'] = str(chosen)
            vars['nego_cmd'] = 'proposes'
            vars['d_ref'] = 'none'
            vars['nego_hint'] = ''
            nxt = 'negotiation_router'
    vars['pg_next'] = nxt
except Exception as e:
    vars['pg_next'] = 'wrap_up'
    vars['snippet_error'] = 'promise_guard: ' + str(e)
