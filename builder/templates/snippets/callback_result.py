# callback_result: after the schedule_callback api node.
try:
    tp = CONST.get('third_party') or dict()
    if _s(vars.get('cb_status')) == 'ok':
        _set_close(tp.get('callback_outcome'), tp.get('callback_reason'), 'Say that a callback is arranged for ' + _s(vars.get('cb_text')) + '.')
    else:
        _set_close(tp.get('no_callback_outcome'), tp.get('no_callback_reason'), 'Say that the callback could not be scheduled because of a technical problem.')
except Exception as e:
    vars['snippet_error'] = 'callback_result: ' + str(e)
