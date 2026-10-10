# product_done: the current product ended without agreement (attempts exhausted). Next product or wrap up.
try:
    NEG = CONST.get('negotiation') or dict()
    table = _load('products_json', [])
    idx = _i(vars.get('cur_idx'))
    nxt = 'wrap_up'
    k = idx + 1
    while k < len(table):
        if table[k].get('status') == 'open':
            vars['cur_idx'] = str(k)
            vars['cur_label'] = _s(table[k].get('label'))
            vars['nego_hint'] = 'Move on to the next product: ' + _s(table[k].get('label')) + ". Propose exactly: 'Could you pay " + _amt(table[k].get('past_due')) + ' on ' + _fmt(_next_bd(_today())) + "?'"
            nxt = 'negotiate'
            break
        k += 1
    if nxt == 'wrap_up':
        agreed = [r for r in table if r.get('status') == 'agreed']
        if agreed:
            rb = []
            for row in agreed:
                rb.append(_s(row.get('label')) + ': ' + _amt(row.get('agreed_amount')) + ' on ' + _fmt(_d(row.get('agreed_date'))))
            vars['readback_text'] = '; '.join(rb)
            vars['rb_hint'] = ''
            vars['rb'] = 'none'
            vars['stage'] = 'readback'
            nxt = 'readback'
        else:
            _set_close(NEG.get('exhausted_outcome'), NEG.get('exhausted_reason'), 'Say that you will leave it there for today.')
    vars['pd_next'] = nxt
except Exception as e:
    vars['pd_next'] = 'wrap_up'
    vars['snippet_error'] = 'product_done: ' + str(e)
