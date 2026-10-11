# id_locked: too many wrong answers.
try:
    idc = CONST.get('identity') or dict()
    _set_close(idc.get('fail_outcome'), idc.get('fail_reason'), _s(idc.get('fail_message')) + ' Do not state any account details.')
except Exception as e:
    vars['snippet_error'] = 'id_locked: ' + str(e)
