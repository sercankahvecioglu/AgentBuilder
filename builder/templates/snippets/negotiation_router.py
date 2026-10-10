# negotiation_router: the policy engine. Consumes `pay`, date parts and amount_said; sets nego_next and nego_hint.
try:
    NEG = CONST.get('negotiation') or dict()
    AMT = CONST.get('amounts') or dict()
    today = _today()
    table = _load('products_json', [])
    idx = _i(vars.get('cur_idx'))
    if idx >= len(table):
        idx = max(0, len(table) - 1)
    p = table[idx] if table else None
    pay = _s(vars.get('pay')).lower()
    vars['pay'] = 'none'
    kind, dsaid = _resolve_date(today)
    amt_said = _f(vars.get('amount_said'), 0.0)
    _reset_date_parts()
    nxt = 'negotiate'
    hint = ''

    def _deadline():
        return _d(p.get('deadline')) or today

    def _default_amount():
        if _f(p.get('pending_amount')) > 0:
            return _f(p.get('pending_amount'))
        if p.get('too_much') and p.get('floor_offered'):
            return _f(p.get('floor'))
        return _f(p.get('past_due'))

    def _propose(amount, d, why=''):
        p['prop_amount'] = float(amount)
        p['prop_date'] = d.isoformat()
        return (why + ' ' if why else '') + "Propose exactly this and wait for the answer: 'Could you pay " + _amt(amount) + ' on ' + _fmt(d) + "?'"

    def _agree(amount, d):
        p['status'] = 'agreed'
        p['agreed_amount'] = float(amount)
        p['agreed_date'] = d.isoformat()
        p['prop_amount'] = float(amount)
        p['prop_date'] = d.isoformat()

    def _attempt_date(att):
        rule = _s(att.get('date'))
        dl = _deadline()
        if rule == 'last_business_day_this_week':
            d = _last_bd_of_week(today)
            if d <= today:
                d = _last_bd_of_week(today + datetime.timedelta(days=7))
            if d > dl:
                d = dl
            return d
        if rule == 'next_business_day':
            return _next_bd(today + datetime.timedelta(days=1))
        if rule == 'today':
            return _next_bd(today)
        return dl

    def _attempt_amount(att):
        rule = _s(att.get('amount'))
        if rule == 'floor':
            return _f(p.get('floor'))
        if rule == 'floor_if_full_refused':
            return _f(p.get('floor')) if p.get('too_much') else _f(p.get('past_due'))
        return _f(p.get('past_due'))

    def _refusal(why=''):
        # a flat refusal or non-answer uses one persuasion attempt
        if _f(p.get('prop_amount')) > 0 and _s(p.get('prop_date')):
            p['refused'] = list(p.get('refused') or []) + [_amt(p.get('prop_amount')) + '|' + _s(p.get('prop_date'))]
        n = _i(p.get('attempts_used')) + 1
        tries = 0
        while tries < 5:
            tries += 1
            if n > _i(p.get('attempts_max'), 1):
                break
            att = None
            for a in (NEG.get('attempts') or []):
                ba = a.get('bands_allowed') or []
                if _i(a.get('n')) == n and (not ba or _s(p.get('band')) in ba):
                    att = a
                    break
            if att is None:
                break
            amount = _attempt_amount(att)
            d = _attempt_date(att)
            key = _amt(amount) + '|' + d.isoformat()
            if NEG.get('no_repeat_refused_offer', True) and key in (p.get('refused') or []):
                n += 1
                continue
            p['attempts_used'] = n
            extra = ''
            if _s(att.get('amount')) == 'floor' and AMT.get('too_much_say_rest_overdue'):
                extra = ' Say that the rest stays overdue.'
            return ('negotiate', _propose(amount, d, why) + extra)
        p['attempts_used'] = n
        p['status'] = 'noted'
        p['note_reason'] = _s(NEG.get('exhausted_note_reason'))
        return ('product_done', '')

    def _offer_floor(why):
        p['floor_offered'] = 1
        p['pending_amount'] = _f(p.get('floor'))
        d = _next_bd(today)
        extra = ' Say that the rest stays overdue.' if AMT.get('too_much_say_rest_overdue') else ''
        return ('negotiate', _propose(_f(p.get('floor')), d, why) + extra)

    def _with_date(d, amount):
        dl = _deadline()
        if d < today:
            return ('negotiate', _propose(amount, _next_bd(today), 'That day has already passed.'))
        if not _is_bd(d):
            if d <= dl:
                return ('negotiate', _propose(amount, _next_bd(d), 'Say that ' + _fmt(d) + ' is not a business day and offer the next business day.'))
            p['deadline_offered'] = 1
            return ('negotiate', _propose(amount, dl, 'Say that the latest date you can record is ' + _fmt(dl) + '.'))
        if d > dl:
            if p.get('deadline_offered') and NEG.get('refusing_deadline_is_flat_refusal', True):
                return _refusal('The customer insisted on a date after the deadline.')
            p['deadline_offered'] = 1
            return ('negotiate', _propose(amount, dl, 'Say that the latest date you can record is ' + _fmt(dl) + '.'))
        _agree(amount, d)
        return ('readback', '')

    if p is None:
        nxt, hint = 'wrap_up', ''
    elif pay == 'asks_question' or _intent(pay) is not None:
        if pay == 'asks_question':
            vars['resume_hint'] = 'Answer the question briefly from the rules you have, then repeat your last question or proposal.'
            vars['resume_node'] = 'negotiate'
            nxt = 'resume_router'
        else:
            nxt = _apply_intent(pay, 'negotiate') or 'negotiate'
            if nxt == 'negotiate':
                hint = 'Repeat your last question or proposal.'
    elif pay == 'yes_today':
        amount = _default_amount()
        if kind == 'date' and dsaid is not None:
            nxt, hint = _with_date(dsaid, amount)
        else:
            nxt, hint = _with_date(today, amount)
    elif pay == 'accepts_offer':
        if _f(p.get('prop_amount')) > 0 and _d(p.get('prop_date')) is not None:
            _agree(_f(p.get('prop_amount')), _d(p.get('prop_date')))
            nxt = 'readback'
        else:
            nxt, hint = _with_date(today, _default_amount())
    elif pay == 'too_much':
        p['too_much'] = 1
        if AMT.get('too_much_offer_floor_once', True) and not p.get('floor_offered') and _f(p.get('floor')) < _f(p.get('past_due')):
            nxt, hint = _offer_floor('Say you understand.')
        else:
            nxt, hint = _refusal()
    elif pay in ('proposes', 'vague'):
        amount = _default_amount()
        if amt_said > 0:
            fl = _f(p.get('floor'))
            full = _f(p.get('past_due'))
            if amt_said < fl - 0.005:
                if AMT.get('below_floor_offer_floor_once', True) and not p.get('floor_offered'):
                    nxt, hint = _offer_floor('Say that an amount below the minimum of ' + _amt(fl) + ' cannot be recorded.')
                    kind = 'handled'
                else:
                    nxt, hint = _refusal('The customer insisted on an amount below the minimum.')
                    kind = 'handled'
            else:
                amount = min(amt_said, full)
                p['pending_amount'] = amount
        if kind == 'handled':
            pass
        elif kind == 'date' and dsaid is not None:
            nxt, hint = _with_date(dsaid, amount)
        elif kind == 'vague' or pay == 'vague':
            if NEG.get('vague_ask_once', True) and not p.get('vague_asked'):
                p['vague_asked'] = 1
                hint = 'The customer gave a vague period. Ask once for the exact day.'
            else:
                dl = _deadline()
                p['deadline_offered'] = 1
                hint = _propose(amount, dl, 'Say that the latest date you can record is ' + _fmt(dl) + '.')
        else:
            if amt_said > 0:
                hint = _propose(amount, _next_bd(today), 'Accept the amount.')
            else:
                nc = _i(p.get('none_count')) + 1
                p['none_count'] = nc
                if nc >= 2 and NEG.get('no_answer_is_refusal', True):
                    nxt, hint = _refusal()
                else:
                    hint = 'Repeat your last question or proposal.'
    elif pay in ('refuses', 'no_answer'):
        nxt, hint = _refusal()
    else:
        nc = _i(p.get('none_count')) + 1
        p['none_count'] = nc
        if nc >= 3 and NEG.get('no_answer_is_refusal', True):
            nxt, hint = _refusal()
        else:
            hint = 'Repeat your last question or proposal in one short sentence.'
    if p is not None:
        table[idx] = p
        _save('products_json', table)
        vars['cur_label'] = _s(p.get('label'))
    if nxt == 'product_done':
        nxt = 'product_done'
    if nxt == 'readback':
        rb = []
        for row in table:
            if row.get('status') == 'agreed':
                rb.append(_s(row.get('label')) + ': ' + _amt(row.get('agreed_amount')) + ' on ' + _fmt(_d(row.get('agreed_date'))))
        vars['readback_text'] = '; '.join(rb)
        vars['rb_hint'] = ''
        vars['rb'] = 'none'
        vars['stage'] = 'readback'
    vars['nego_hint'] = hint
    vars['nego_next'] = nxt
except Exception as e:
    vars['nego_next'] = 'negotiate'
    vars['nego_hint'] = 'Repeat your last question in one short sentence.'
    vars['snippet_error'] = 'negotiation_router: ' + str(e)
