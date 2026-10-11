# negotiation_router: the policy engine. Consumes `pay`, `applies_to`, `product_hint`, date parts and amount_said;
# sets nego_next and nego_hint. Works per product (cur_idx) and across products (multi-product mode).
try:
    NEG = CONST.get('negotiation') or dict()
    _pause()
    AMT = CONST.get('amounts') or dict()
    MULTI = bool(CONST.get('multi'))
    today = _today()
    table = _load('products_json', [])
    idx = _i(vars.get('cur_idx'))
    if idx >= len(table):
        idx = max(0, len(table) - 1)
    pay = _s(vars.get('pay')).lower()
    vars['pay'] = 'none'
    cmd = _s(vars.get('nego_cmd')).lower()
    vars['nego_cmd'] = ''
    if cmd:
        pay = cmd
    scope = _s(vars.get('applies_to')).lower()
    vars['applies_to'] = 'none'
    phint = _s(vars.get('product_hint')).lower()
    vars['product_hint'] = ''
    frag = _s(vars.get('fragment')).lower() == 'yes'
    vars['fragment'] = 'no'
    kind, dsaid = _resolve_date(today)
    amt_said = _f(vars.get('amount_said'), 0.0)
    dom_said = _i(vars.get('d_dom'))
    if amt_said > 0 and dom_said > 0 and abs(amt_said - dom_said) < 0.5:
        amt_said = 0.0
    if amt_said > 0 and amt_said < 32 and _s(vars.get('d_ref')).lower() in ('day_of_month', 'weekday'):
        amt_said = 0.0
    _reset_date_parts()
    nxt = 'negotiate'
    hint = ''

    def _open_idx():
        out = []
        k = 0
        while k < len(table):
            if table[k].get('status') == 'open':
                out.append(k)
            k += 1
        return out

    def _named_idx():
        # the product the customer refers to by words, else the current one
        if phint:
            k = 0
            while k < len(table):
                lab = _s(table[k].get('label')).lower()
                typ = _s(table[k].get('type')).lower().replace('_', ' ')
                words = [w for w in re.split(r'[^a-z0-9]+', phint) if len(w) > 2]
                if any(w in lab or w in typ for w in words):
                    return k
                k += 1
        return idx

    # switch the current product if the customer names another open one
    if MULTI and phint:
        j = _named_idx()
        if j != idx and table[j].get('status') == 'open':
            idx = j
            vars['cur_idx'] = str(idx)
    p = table[idx] if table else None

    def _deadline(q):
        return _d(q.get('deadline')) or today

    def _default_amount(q):
        if _f(q.get('pending_amount')) > 0:
            return _f(q.get('pending_amount'))
        if q.get('too_much') and q.get('floor_offered'):
            return _f(q.get('floor'))
        return _f(q.get('past_due'))

    def _propose(q, amount, d, why=''):
        if _s(vars.get('prop_all')) == '1' and why.find('for all products') < 0:
            vars['prop_all'] = ''
        q['prop_amount'] = float(amount)
        q['prop_date'] = d.isoformat()
        lab = (' for the ' + _s(q.get('label'))) if MULTI else ''
        return (why + ' ' if why else '') + 'Could you pay ' + _amt(amount) + lab + ' on ' + _fmt(d) + '?'

    def _agree(q, amount, d, note=''):
        q['status'] = 'agreed'
        q['agreed_amount'] = float(amount)
        q['agreed_date'] = d.isoformat()
        q['prop_amount'] = float(amount)
        q['prop_date'] = d.isoformat()
        q['deadline_note'] = note

    def _attempt_date(q, att):
        rule = _s(att.get('date'))
        dl = _deadline(q)
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

    def _attempt_amount(q, att):
        rule = _s(att.get('amount'))
        if rule == 'floor':
            return _f(q.get('floor'))
        if rule == 'floor_if_full_refused':
            return _f(q.get('floor')) if q.get('too_much') else _f(q.get('past_due'))
        return _f(q.get('past_due'))

    def _next_attempt(q, why='', count_refusal=True):
        # a flat refusal or non-answer uses one persuasion attempt; returns (next, hint)
        if count_refusal and _f(q.get('prop_amount')) > 0 and _s(q.get('prop_date')):
            q['refused'] = list(q.get('refused') or []) + [_amt(q.get('prop_amount')) + '|' + _s(q.get('prop_date'))]
        n = _i(q.get('attempts_used')) + 1
        tries = 0
        while tries < 5:
            tries += 1
            if n > _i(q.get('attempts_max'), 1):
                break
            att = None
            for a in (NEG.get('attempts') or []):
                ba = a.get('bands_allowed') or []
                if _i(a.get('n')) == n and (not ba or _s(q.get('band')) in ba):
                    att = a
                    break
            if att is None:
                break
            amount = _attempt_amount(q, att)
            d = _attempt_date(q, att)
            key = _amt(amount) + '|' + d.isoformat()
            if NEG.get('no_repeat_refused_offer', True) and key in (q.get('refused') or []):
                n += 1
                continue
            q['attempts_used'] = n
            extra = ''
            if _s(att.get('amount')) == 'floor' and AMT.get('too_much_say_rest_overdue'):
                extra = ' The rest stays overdue.'
            return ('negotiate', _propose(q, amount, d, why) + extra)
        q['attempts_used'] = n
        q['status'] = 'noted'
        q['note_reason'] = _s(NEG.get('exhausted_note_reason'))
        return ('product_done', '')

    def _offer_floor(q, why):
        # the floor is offered once, without naming a day: an accepted amount with no day means today
        q['floor_offered'] = 1
        q['pending_amount'] = _f(q.get('floor'))
        d = _next_bd(today)
        q['prop_amount'] = _f(q.get('floor'))
        q['prop_date'] = d.isoformat()
        extra = ' The rest stays overdue.' if AMT.get('too_much_say_rest_overdue') else ''
        return ('negotiate', (why + ' ' if why else '') + 'Could you pay the minimum of ' + _amt(q.get('floor')) + ' instead?' + extra)

    def _with_date(q, d, amount):
        dl = _deadline(q)
        if d < today:
            return ('negotiate', _propose(q, amount, _next_bd(today), 'That day has already passed.'))
        if not _is_bd(d):
            if d <= dl:
                return ('negotiate', _propose(q, amount, _next_bd(d), _fmt(d) + ' is not a business day.'))
            q['deadline_offered'] = 1
            return ('negotiate', _propose(q, amount, dl, 'The latest date I can record is ' + _fmt(dl) + '.'))
        if d > dl:
            if q.get('deadline_offered') and NEG.get('refusing_deadline_is_flat_refusal', True):
                return _next_attempt(q, 'I understand.')
            q['deadline_offered'] = 1
            return ('negotiate', _propose(q, amount, dl, 'The latest date I can record is ' + _fmt(dl) + '.'))
        _agree(q, amount, d)
        return ('agreed', '')

    def _agree_all(d, amount_rule='full'):
        # one date for every open product; a product whose deadline is earlier gets its own deadline (and says so)
        if not _is_bd(d):
            vars['prop_all'] = '1'
            return ('negotiate', _propose(p, _f(p.get('past_due')), _next_bd(d), _fmt(d) + ' is not a business day, so for all products:'))
        vars['prop_all'] = ''
        for k in _open_idx():
            q = table[k]
            dd = d
            note = ''
            if not _is_bd(dd):
                dd = _next_bd(dd)
            dl = _deadline(q)
            if dd > dl:
                if CONST.get('date_over_deadline_use_product_deadline', True):
                    dd = dl
                    note = 'on its own latest date, ' + _fmt(dl) + ', because the day you named is after it'
                else:
                    continue
            amount = _f(q.get('past_due')) if amount_rule == 'full' else _default_amount(q)
            _agree(q, amount, dd, note)
        return None

    def _after_agree():
        # single product → read back; multi → next open product or read back
        opens = _open_idx()
        if MULTI and opens:
            vars['cur_idx'] = str(opens[0])
            return _start_product(table[opens[0]], 'Noted, I will read everything back at the end.')
        return ('readback', '')

    def _start_product(q, lead=''):
        # next product begins at attempt 1 without asking about today again
        return _next_attempt(q, (lead + ' ' if lead else '') + 'Now the ' + _s(q.get('label')) + '.', False)

    if p is not None and pay in ('yes_today', 'accepts_offer', 'proposes', 'too_much', 'vague'):
        p['none_count'] = 0
    # a cut-off turn that carries a number or a day ("I can pay the full 45", "the 11th, sorry, I mean"): the value is
    # probably incomplete, so ask once or twice to hear it whole instead of acting on it (never counts as an attempt)
    cut_value = frag and (amt_said > 0 or kind in ('date', 'vague')) and pay in ('yes_today', 'accepts_offer', 'proposes', 'too_much', 'vague')
    if p is not None and cut_value and _i(p.get('frag_count')) < 2:
        p['frag_count'] = _i(p.get('frag_count')) + 1
        pay = '__cut__'
    if p is None:
        nxt, hint = 'wrap_up', ''
    elif pay == '__cut__':
        hint = 'Sorry, I did not catch all of that. Could you say it again?'
    elif pay == 'start_product':
        nxt, hint = _start_product(p)
    elif pay == 'asks_question' or _intent(pay) is not None:
        it = _intent(pay)
        if pay == 'asks_question':
            if _f(p.get('prop_amount')) > 0 and _s(p.get('prop_date')):
                vars['resume_hint'] = 'Answer the question briefly from the facts you have, then wait for the answer to your last proposal. Do not state the proposal again and do not make any new offer.'
            else:
                vars['resume_hint'] = 'Answer the question briefly from the facts you have, then repeat your last question.'
            vars['resume_node'] = 'negotiate'
            nxt = 'resume_router'
        elif MULTI and it is not None and it.get('continue_other_products') and _s(it.get('action_note_reason')) and it.get('ask_once_first') and _s(vars.get('offered_' + pay)) != '1':
            # the one-time offer (a transfer, help) comes first; a decline returns here through offer_router
            vars['offered_' + pay] = '1'
            nxt = _apply_intent(pay, 'negotiate') or 'negotiate'
            if nxt == 'negotiate':
                hint = _s(vars.get('last_say'))
        elif MULTI and it is not None and it.get('continue_other_products') and _s(it.get('action_note_reason')):
            # note this product and carry on with the others
            j = _named_idx() if phint else idx
            q = table[j]
            if scope == 'all':
                for k in _open_idx():
                    table[k]['status'] = 'noted'
                    table[k]['note_reason'] = _s(it.get('action_note_reason'))
            else:
                q['status'] = 'noted'
                q['note_reason'] = _s(it.get('action_note_reason'))
            vars['cnt_' + pay] = str(_i(vars.get('cnt_' + pay)) + 1)
            say = _s(it.get('say_text')) if _s(vars.get('offered_' + pay)) != '1' else ''
            vars['nego_instruction'] = say
            opens = _open_idx()
            if opens:
                vars['cur_idx'] = str(opens[0])
                nxt, hint = _start_product(table[opens[0]])
            else:
                agreed = [r for r in table if r.get('status') == 'agreed']
                if agreed:
                    nxt = 'readback'
                    vars['rb_hint'] = say
                else:
                    vars['goodbye_prefix'] = say
                    nxt = 'wrap_up'
        else:
            nxt = _apply_intent(pay, 'negotiate') or 'negotiate'
            if nxt == 'negotiate':
                hint = _s(vars.get('last_say'))
    elif pay == 'yes_today':
        if MULTI and (scope == 'all' or (scope != 'current' and len(_open_idx()) > 1 and _i(vars.get('asked_all')) == 0)):
            res = _agree_all(today)
            vars['asked_all'] = '1'
            nxt, hint = res if res else _after_agree()
        else:
            amount = _default_amount(p)
            d = dsaid if (kind == 'date' and dsaid is not None) else today
            nxt, hint = _with_date(p, d, amount)
            if nxt == 'agreed':
                nxt, hint = _after_agree()
    elif pay == 'accepts_offer' and ((kind == 'date' and dsaid is not None and dsaid.isoformat() != _s(p.get('prop_date'))) or (amt_said > 0 and abs(amt_said - _f(p.get('prop_amount'))) > 0.005)):
        # the customer named a day or an amount that differs from the proposal: treat it as their own proposal
        amount = _default_amount(p)
        if amt_said > 0 and amt_said >= _f(p.get('floor')) - 0.005:
            amount = min(amt_said, _f(p.get('past_due')))
            p['pending_amount'] = amount
        elif amt_said > 0:
            nxt, hint = (_offer_floor(p, 'An amount below the minimum of ' + _amt(p.get('floor')) + ' cannot be recorded.') if not p.get('floor_offered') else _next_attempt(p, 'I understand.'))
            kind = 'handled'
        if kind == 'date' and dsaid is not None:
            if MULTI and scope == 'all' and len(_open_idx()) > 1:
                res = _agree_all(dsaid)
                nxt, hint = res if res else _after_agree()
            else:
                nxt, hint = _with_date(p, dsaid, amount)
                if nxt == 'agreed':
                    nxt, hint = _after_agree()
        elif kind != 'handled':
            _agree(p, amount, _d(p.get('prop_date')) or _next_bd(today))
            nxt, hint = _after_agree()
    elif pay == 'accepts_offer':
        if MULTI and _s(vars.get('prop_all')) == '1' and _d(p.get('prop_date')) is not None:
            res = _agree_all(_d(p.get('prop_date')))
            nxt, hint = res if res else _after_agree()
        elif _f(p.get('prop_amount')) > 0 and _d(p.get('prop_date')) is not None:
            _agree(p, _f(p.get('prop_amount')), _d(p.get('prop_date')))
            nxt, hint = _after_agree()
        else:
            nxt, hint = _with_date(p, today, _default_amount(p))
            if nxt == 'agreed':
                nxt, hint = _after_agree()
    elif pay == 'too_much':
        p['too_much'] = 1
        if AMT.get('too_much_offer_floor_once', True) and not p.get('floor_offered') and _f(p.get('floor')) < _f(p.get('past_due')):
            nxt, hint = _offer_floor(p, 'I understand.')
        else:
            nxt, hint = _next_attempt(p)
    elif pay in ('proposes', 'vague'):
        amount = _default_amount(p)
        handled = False
        if amt_said > 0:
            fl = _f(p.get('floor'))
            full = _f(p.get('past_due'))
            if amt_said < fl - 0.005:
                if AMT.get('below_floor_offer_floor_once', True) and not p.get('floor_offered'):
                    nxt, hint = _offer_floor(p, 'An amount below the minimum of ' + _amt(fl) + ' cannot be recorded.')
                else:
                    nxt, hint = _next_attempt(p, 'I understand.')
                handled = True
            else:
                amount = min(amt_said, full)
                p['pending_amount'] = amount
        if handled:
            pass
        elif kind == 'date' and dsaid is not None:
            if MULTI and scope == 'all' and len(_open_idx()) > 1:
                if dsaid < today:
                    hint = _propose(p, amount, _next_bd(today), 'That day has already passed.')
                else:
                    res = _agree_all(dsaid)
                    vars['asked_all'] = '1'
                    nxt, hint = res if res else _after_agree()
            else:
                nxt, hint = _with_date(p, dsaid, amount)
                if nxt == 'agreed':
                    nxt, hint = _after_agree()
        elif kind == 'vague' or pay == 'vague':
            vars['week_ctx'] = _s(vars.get('d_week_said'))
            if NEG.get('vague_ask_once', True) and not p.get('vague_asked'):
                p['vague_asked'] = 1
                hint = 'Which exact day would that be?'
            else:
                dl = _deadline(p)
                p['deadline_offered'] = 1
                hint = _propose(p, amount, dl, 'The latest date I can record is ' + _fmt(dl) + '.')
        else:
            if amt_said > 0:
                hint = _propose(p, amount, _next_bd(today), '')
            else:
                nc = _i(p.get('none_count')) + 1
                p['none_count'] = nc
                if nc >= 2 and NEG.get('no_answer_is_refusal', True):
                    nxt, hint = _next_attempt(p)
                else:
                    hint = 'Sorry, I did not catch that. Could you say that again?'
    elif pay == 'no_answer' or (pay == 'refuses' and frag):
        # a non-answer: ask once for the answer before it counts as a persuasion attempt (cut-off or off-topic turns)
        nc = _i(p.get('none_count')) + 1
        p['none_count'] = nc
        if nc >= 2 and NEG.get('no_answer_is_refusal', True):
            if MULTI and _i(vars.get('asked_all')) == 0:
                vars['asked_all'] = '1'
            nxt, hint = _next_attempt(p)
        else:
            hint = 'Sorry, I did not catch your answer. Does that work for you?'
    elif pay == 'refuses':
        if MULTI and _i(vars.get('asked_all')) == 0:
            vars['asked_all'] = '1'
        nxt, hint = _next_attempt(p)
    else:
        nc = _i(p.get('none_count')) + 1
        p['none_count'] = nc
        if nc >= 3 and NEG.get('no_answer_is_refusal', True):
            nxt, hint = _next_attempt(p)
        else:
            hint = 'Sorry, I did not catch that. Could you say that again?'
    _save('products_json', table)
    cur = table[_i(vars.get('cur_idx'))] if table and _i(vars.get('cur_idx')) < len(table) else p
    if cur is not None:
        vars['cur_label'] = _s(cur.get('label'))
    if nxt == 'readback':
        rb = []
        for row in table:
            if row.get('status') == 'agreed':
                line = _s(row.get('label')) + ': ' + _amt(row.get('agreed_amount')) + ' on ' + _fmt(_d(row.get('agreed_date')))
                if _s(row.get('deadline_note')):
                    line = line + ' (' + _s(row.get('deadline_note')) + ')'
                rb.append(line)
        vars['readback_text'] = '; '.join(rb)
        vars['rb_hint'] = _s(vars.get('rb_hint')) if _s(vars.get('rb_hint')) else ''
        vars['rb'] = 'none'
        vars['rb_asks'] = '0'
        vars['stage'] = 'readback'
    instr = _s(vars.get('nego_instruction'))
    vars['nego_instruction'] = ''
    asked = _s(vars.get('asks')).lower()
    vars['asks'] = 'none'
    if asked and asked != 'none' and nxt == 'readback':
        ait = _intent(asked)
        vars['rb_hint'] = 'The customer also asked a question. ' + (_s(ait.get('say_text')) if ait is not None and _s(ait.get('say_text')) else 'Answer it briefly from the facts you have; if you do not have the information, say so.')
        nxt = 'readback_llm'
    if asked and asked != 'none' and nxt == 'negotiate' and not instr:
        ait = _intent(asked)
        if ait is not None and _s(ait.get('say_text')):
            instr = 'The customer also asked a question. ' + _s(ait.get('say_text'))
        else:
            instr = 'The customer also asked a question. Answer it briefly from the facts you have; if you do not have the information, say so.'
    if nxt == 'negotiate':
        if instr:
            vars['nego_hint'] = instr + (" Then say exactly: '" + hint + "'" if hint else '')
            vars['nego_say'] = ''
            nxt = 'negotiate_llm'
        else:
            vars['nego_say'] = hint
            vars['nego_hint'] = ''
            vars['last_say'] = hint
    else:
        vars['nego_hint'] = hint
        vars['nego_say'] = ''
    vars['nego_next'] = nxt
except Exception as e:
    vars['nego_next'] = 'negotiate_llm'
    vars['nego_say'] = ''
    vars['nego_hint'] = 'Repeat your last question in one short sentence.'
    vars['snippet_error'] = 'negotiation_router: ' + str(e)
