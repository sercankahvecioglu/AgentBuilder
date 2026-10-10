# callback_check: after each reply of the third party.
try:
    tp = CONST.get('third_party') or dict()
    today = _today()
    intent = _s(vars.get('tp_intent')).lower()
    vars['tp_intent'] = 'none'
    nxt = 'third_party'
    if intent == 'wrong_number':
        _set_close(tp.get('wrong_number_outcome'), tp.get('wrong_number_reason'), 'Apologise for the disturbance.')
        nxt = 'wrap_up'
    elif intent == 'deceased':
        sent = _s(tp.get('deceased_sentence'))
        pre = ("Say exactly: '" + sent + "'" if sent else 'Express condolences in one sentence.') + ' Ask nothing else.'
        _set_close(tp.get('deceased_outcome'), tp.get('deceased_reason'), pre)
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
        if ok:
            vars['cb_date'] = d.isoformat()
            vars['cb_time'] = hhmm
            vars['cb_text'] = _fmt(d) + ' at ' + hhmm
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
                _set_close(tp.get('no_callback_outcome'), tp.get('no_callback_reason'), 'Say that no callback could be arranged.')
                nxt = 'wrap_up'
    vars['tp_next'] = nxt
except Exception as e:
    vars['tp_next'] = 'third_party'
    vars['tp_hint'] = 'Ask when the customer can be reached.'
    vars['snippet_error'] = 'callback_check: ' + str(e)
