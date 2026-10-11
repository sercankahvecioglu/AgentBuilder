# account_facts: after get_account. Builds the product table, deadlines, texts.
try:
    today = _today()
    prods = _load('ga_products_json', None)
    if not isinstance(prods, list):
        prods = []
        k = 0
        while k < 10:
            pid = vars.get(_s(CONST.get('ga_node')) + '_response.data.' + _s(CONST.get('products_field')) + '.' + str(k) + '.product_id')
            if pid is None:
                break
            row = dict()
            for fn in (CONST.get('product_fields') or []):
                v = vars.get(_s(CONST.get('ga_node')) + '_response.data.' + _s(CONST.get('products_field')) + '.' + str(k) + '.' + fn)
                if v is not None:
                    row[fn] = v
            prods.append(row)
            k += 1
    table = []
    labels = CONST.get('product_labels') or dict()
    floors = CONST.get('floor_fields') or dict()
    bands = CONST.get('bands') or []
    maxdl = today
    for p in prods:
        if not isinstance(p, dict):
            continue
        ptype = _s(p.get('type'))
        tmpl = _s(labels.get(ptype)) or ptype.replace('_', ' ')
        label = tmpl
        for kk in p:
            label = label.replace('{' + kk + '}', _s(p.get(kk)))
        floor_field = _s(floors.get(ptype))
        floor = _f(p.get(floor_field), 0.0) if floor_field else 0.0
        past_due = _f(p.get('past_due'), 0.0)
        days_late = _i(p.get('days_late'))
        band = None
        for b in bands:
            if _i(b.get('days_late_min')) <= days_late <= _i(b.get('days_late_max')):
                band = b
                break
        if band is None and bands:
            band = bands[-1]
            for b in bands:
                if days_late < _i(b.get('days_late_min')):
                    band = b
                    break
        n_bd = _i((band or dict()).get('deadline_business_days'), 1)
        deadline = _add_bd(today, n_bd)
        if deadline > maxdl:
            maxdl = deadline
        row = dict()
        row['id'] = _s(p.get('product_id'))
        row['type'] = ptype
        row['label'] = label
        row['past_due'] = past_due
        row['floor'] = floor if floor > 0 else past_due
        row['days_late'] = days_late
        row['band'] = _s((band or dict()).get('label'))
        row['deadline'] = deadline.isoformat()
        row['attempts_max'] = _i((band or dict()).get('persuasion_attempts'), 1)
        row['attempts_used'] = 0
        row['too_much'] = 0
        row['floor_offered'] = 0
        row['vague_asked'] = 0
        row['deadline_offered'] = 0
        row['status'] = 'open'
        row['agreed_amount'] = 0.0
        row['agreed_date'] = ''
        row['note_reason'] = ''
        row['refused'] = []
        row['pending_amount'] = 0.0
        row['prop_amount'] = 0.0
        row['prop_date'] = ''
        row['none_count'] = 0
        table.append(row)
    _save('products_json', table)
    vars['product_count'] = str(len(table))
    vars['cur_idx'] = '0'
    vars['stage'] = 'negotiation'
    lines = []
    inc = CONST.get('debt_include') or ['past_due', 'days_late']
    for row in table:
        parts = []
        if 'past_due' in inc:
            parts.append(_ph('debt_past_due', amount=_amt(row['past_due'])))
        if 'days_late' in inc:
            parts.append(_ph('debt_days_late', n=str(row['days_late'])))
        if 'floor' in inc:
            parts.append(_ph('debt_floor', amount=_amt(row['floor'])))
        if 'deadline' in inc:
            parts.append(_ph('debt_deadline', date=_fmt(_d(row['deadline']))))
        lines.append(_ph('debt_line', label=row['label'], parts=_ph('debt_and').join(parts)))
    vars['debt_text'] = ' '.join(lines) if lines else _ph('no_products')
    facts = ['Today is ' + _fmt(today) + '.']
    for row in table:
        facts.append(row['label'] + ': full past-due amount ' + _amt(row['past_due']) + ', minimum ' + _amt(row['floor']) + ', latest possible promise date ' + _fmt(_d(row['deadline'])) + '.')
    vars['date_facts'] = '\n'.join(facts)
    if table:
        vars['cur_label'] = table[0]['label']
    else:
        vars['cur_label'] = ''
    vars['nego_hint'] = ''
    vars['ga_count'] = str(len(table))
    _reset_date_parts()
    vars['pay'] = 'none'
except Exception as e:
    vars['snippet_error'] = 'account_facts: ' + str(e)
    vars['products_json'] = '[]'
    vars['product_count'] = '0'
    vars['cur_idx'] = '0'
    vars['debt_text'] = ''
    vars['date_facts'] = ''
    vars['nego_hint'] = ''
    vars['stage'] = 'negotiation'
