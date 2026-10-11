# pre_close: after the goodbye. Decides whether a transfer runs before the close.
try:
    q = _s(vars.get('transfer_queue'))
    if q and _s(vars.get('transfer_done')) != 'yes':
        vars['transfer_done'] = 'yes'
        vars['tr_status'] = ''
        vars['pc_next'] = 'do_transfer'
    else:
        vars['pc_next'] = 'close_router'
except Exception as e:
    vars['pc_next'] = 'close_router'
    vars['snippet_error'] = 'pre_close: ' + str(e)
