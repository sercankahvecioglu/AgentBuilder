# product_done: the current product ended without agreement (attempts exhausted). Next product, read-back or wrap up.
try:
    NEG = CONST.get('negotiation') or dict()
    table = _load('products_json', [])
    nxt = 'wrap_up'
    k = 0
    opens = []
    while k < len(table):
        if table[k].get('status') == 'open':
            opens.append(k)
        k += 1
    if opens:
        vars['cur_idx'] = str(opens[0])
        vars['cur_label'] = _s(table[opens[0]].get('label'))
        vars['nego_cmd'] = 'start_product'
        vars['nego_instruction'] = ''
        nxt = 'negotiation_router'
    else:
        agreed = [r for r in table if r.get('status') == 'agreed']
        if agreed:
            rb = []
            for row in agreed:
                line = _s(row.get('label')) + ': ' + _amt(row.get('agreed_amount')) + ' on ' + _fmt(_d(row.get('agreed_date')))
                if _s(row.get('deadline_note')):
                    line = line + ' (' + _s(row.get('deadline_note')) + ')'
                rb.append(line)
            vars['readback_text'] = '; '.join(rb)
            vars['rb_hint'] = 'Say you understand.'
            vars['rb'] = 'none'
            vars['rb_asks'] = '0'
            vars['stage'] = 'readback'
            nxt = 'readback'
        else:
            _set_close(NEG.get('exhausted_outcome'), NEG.get('exhausted_reason'), '', 'I will leave it there for today.')
    vars['pd_next'] = nxt
except Exception as e:
    vars['pd_next'] = 'wrap_up'
    vars['snippet_error'] = 'product_done: ' + str(e)
