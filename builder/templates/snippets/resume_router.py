# resume_router: returns to the stage node named in resume_node, carrying resume_hint into that node's hint.
try:
    node = _s(vars.get('resume_node')) or 'negotiate'
    hint = _s(vars.get('resume_hint'))
    if node == 'opening':
        vars['opening_hint'] = hint
    elif node.startswith('identity_q'):
        vars['id_hint'] = hint
    elif node == 'third_party':
        vars['tp_hint'] = hint
    elif node == 'readback':
        vars['rb_hint'] = hint
    elif node == 'offer':
        vars['offer_hint'] = hint
    else:
        vars['nego_hint'] = hint
        node = 'negotiate'
    vars['resume_hint'] = ''
    vars['resume_next'] = node
except Exception as e:
    vars['resume_next'] = 'negotiate'
    vars['snippet_error'] = 'resume_router: ' + str(e)
