# callback_check: after each reply of the third party.
try:
    tp = CONST.get('third_party') or dict()
    today = _today()
    _pause()
    intent = _s(vars.get('tp_intent')).lower()
    vars['tp_intent'] = 'none'
    nxt = 'third_party'
    ok = False
    if intent == 'wrong_number':
        _set_close(tp.get('wrong_number_outcome'), tp.get('wrong_number_reason'), '', _ph('apologise'))
        nxt = 'wrap_up'
    elif intent == 'deceased':
        sent = _s(tp.get('deceased_sentence'))
        low = sent.lower().strip()
        instr = low.startswith(('say ', 'tell ', 'express ', 'state ', 'offer '))
        if sent and not instr:
            _set_close(tp.get('deceased_outcome'), tp.get('deceased_reason'), '', sent)
        else:
            _set_close(tp.get('deceased_outcome'), tp.get('deceased_reason'), (sent if instr else 'Express condolences in one sentence.') + ' Ask nothing else.')
        nxt = 'wrap_up'
    elif _intent(intent) is not None:
        nxt = _apply_intent(intent, 'third_party') or 'third_party'
    else:
        kind, d = _resolve_date(today)
        t = _s(vars.get('cb_time')).strip()
        vars['cb_time_said'] = t
        m = re.match(r'^(\d{1,2}):(\d{2})$', t)
        hhmm = ''
        if m:
            hhmm = ('%02d:%s' % (int(m.group(1)), m.group(2)))
        frag = _s(vars.get('fragment')).lower() == 'yes'
        vars['fragment'] = 'no'
        if frag and _i(vars.get('cb_noinfo')) < 4:
            # a cut-off turn: whatever day or time it carries is probably incomplete; hear it whole first
            kind, d, hhmm = 'none', None, ''
        pend = _d(vars.get('cb_pending_day'))
        if kind != 'date' and hhmm and pend is not None and pend >= today:
            # the day came in an earlier turn, the time in this one
            d = pend
            kind = 'date'
        if kind == 'date' and not hhmm and d is not None and d >= today:
            vars['cb_pending_day'] = d.isoformat()
            vars['cb_pending_text'] = _fmt(d)
        allowed = []
        for k in (tp.get('allowed_days') or []):
            if k == 'today':
                allowed.append(today)
            elif k == 'next_business_day':
                allowed.append(_next_bd(today + datetime.timedelta(days=1)))
            elif k == 'any_business_day':
                allowed = None
                break
        if kind != 'date' and hhmm:
            d = today if hhmm > _now_hhmm() else _next_bd(today + datetime.timedelta(days=1))
            kind = 'date'
        ok = False
        reason = ''
        if kind == 'date' and hhmm:
            inside = (allowed is None and _is_bd(d)) or (allowed is not None and d in allowed)
            fr = _s(tp.get('from_time')) or '00:00'
            to = _s(tp.get('to_time')) or '23:59'
            if tp.get('inclusive', True):
                tin = fr <= hhmm <= to
            else:
                tin = fr < hhmm < to
            if d == today and tp.get('after_now', True) and hhmm <= _now_hhmm():
                tin = False
            ok = inside and tin
            if not ok:
                reason = 'The time offered is outside the window.'
        else:
            reason = 'No day or no time was given.'
        _reset_date_parts()
        vars['cb_time'] = ''
        if not ok and (kind != 'date' or not hhmm):
            # incomplete information (no day, no time, or a cut-off turn) is not an offer outside the window:
            # ask for the missing part, up to twice, before the window rule applies
            n = _i(vars.get('cb_noinfo')) + 1
            vars['cb_noinfo'] = str(n)
            if n <= 4:
                if kind == 'date' and d is not None:
                    vars['tp_hint'] = 'The person named ' + _fmt(d) + ' but no time. Ask at what time on that day the customer can be reached.'
                elif hhmm:
                    vars['tp_hint'] = 'The person named a time but no day. Ask on which day the customer can be reached at that time.'
                else:
                    vars['tp_hint'] = 'The person has not yet said when the customer can be reached. Ask again for a day and a time.'
                vars['tp_next'] = 'third_party'
                ok = None
        if ok is None:
            pass
        elif ok:
            vars['cb_date'] = d.isoformat()
            vars['cb_time'] = hhmm
            vars['cb_text'] = _ph('at_time', date=_fmt(d), time=hhmm)
            vars['cb_status'] = ''
            nxt = 'do_callback'
        else:
            asks = _i(vars.get('cb_asks'))
            if asks < _i(tp.get('ask_again_times'), 1):
                vars['cb_asks'] = str(asks + 1)
                days_txt = ' or '.join([_fmt(x) for x in allowed]) if allowed else 'a business day'
                vars['tp_hint'] = reason + ' Say that a callback is possible ' + days_txt + ' between ' + _s(tp.get('from_time')) + ' and ' + _s(tp.get('to_time')) + ', later than now, and ask once for another day and time.'
                nxt = 'third_party'
            else:
                _set_close(tp.get('no_callback_outcome'), tp.get('no_callback_reason'), '', _ph('no_callback'))
                nxt = 'wrap_up'
    if ok is not None or intent in ('wrong_number', 'deceased') or _intent(intent) is not None:
        vars['tp_next'] = nxt
except Exception as e:
    vars['tp_next'] = 'third_party'
    vars['tp_hint'] = 'Ask when the customer can be reached.'
    vars['snippet_error'] = 'callback_check: ' + str(e)
