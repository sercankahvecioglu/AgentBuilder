# Shared helpers for every code node (runs in Freya's sandbox). `CONST` and `vars` exist before this text.
# Rules: only json/re/datetime; never raise; no double braces anywhere in this file.
import json, re, datetime

WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
CAL = CONST.get('cal') or dict()
BW = set(CAL.get('business_weekdays') or [0, 1, 2, 3, 4])
HOL = set(CAL.get('holidays') or [])


def _s(v):
    return '' if v is None else str(v)


def _d(s):
    try:
        return datetime.date.fromisoformat(_s(s)[:10])
    except Exception:
        return None


def _today():
    d = _d(vars.get(CONST.get('now_var') or 'now'))
    if d is None:
        d = datetime.date.today()
    return d


def _now_hhmm():
    m = re.search(r'[T ](\d\d):(\d\d)', _s(vars.get(CONST.get('now_var') or 'now')))
    if m:
        return m.group(1) + ':' + m.group(2)
    return '00:00'


def _is_bd(d):
    return d.weekday() in BW and d.isoformat() not in HOL


def _next_bd(d):
    n = 0
    while not _is_bd(d) and n < 60:
        d = d + datetime.timedelta(days=1)
        n += 1
    return d


def _add_bd(d, n):
    k = 0
    while k < n:
        d = d + datetime.timedelta(days=1)
        if _is_bd(d):
            k += 1
    return d


def _week_start(d):
    return d - datetime.timedelta(days=d.weekday())


def _last_bd_of_week(d):
    e = _week_start(d) + datetime.timedelta(days=6)
    n = 0
    while not _is_bd(e) and n < 7:
        e = e - datetime.timedelta(days=1)
        n += 1
    return e


def _fmt(d):
    if d is None:
        return ''
    return WEEKDAYS[d.weekday()].capitalize() + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1].capitalize() + ' ' + str(d.year)


def _amt(x):
    try:
        return ('%.2f' % float(x))
    except Exception:
        return _s(x)


def _f(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _i(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default


def _load(name, default):
    v = vars.get(name)
    if isinstance(v, (list, dict)):
        return v
    try:
        if isinstance(v, str) and v.strip():
            return json.loads(v)
    except Exception:
        pass
    return default


def _save(name, obj):
    vars[name] = json.dumps(obj)


def _reset_date_parts():
    vars['d_week_said'] = _s(vars.get('d_week')).lower() if _s(vars.get('d_week')).lower() in ('this', 'next', 'week_after_next') else ''
    vars['d_ref'] = 'none'
    vars['d_weekday'] = 'none'
    vars['d_week'] = 'none'
    vars['d_dom'] = 0
    vars['d_month'] = 'none'
    vars['d_year'] = 0
    vars['amount_said'] = 0


def _resolve_date(today):
    """Date parts written by extraction -> ('date', date) | ('vague', None) | ('none', None)."""
    ref = _s(vars.get('d_ref')).lower()
    wd = _s(vars.get('d_weekday')).lower()
    wk = _s(vars.get('d_week')).lower()
    dom = _i(vars.get('d_dom'))
    mon = _s(vars.get('d_month')).lower()
    yr = _i(vars.get('d_year'))
    if ref == 'today':
        return ('date', today)
    if ref == 'tomorrow':
        return ('date', today + datetime.timedelta(days=1))
    if ref == 'day_after_tomorrow':
        return ('date', today + datetime.timedelta(days=2))
    if ref == 'vague':
        return ('vague', None)
    if ref == 'weekday' or (ref in ('', 'none') and wd in WEEKDAYS):
        if wd not in WEEKDAYS:
            return ('vague', None)
        idx = WEEKDAYS.index(wd)
        ws = _week_start(today)
        if wk in ('', 'none') and _s(vars.get('week_ctx')) in ('this', 'next', 'week_after_next'):
            wk = _s(vars.get('week_ctx'))
        vars['week_ctx'] = ''
        if wk == 'week_after_next':
            return ('date', ws + datetime.timedelta(days=14 + idx))
        if wk == 'next':
            if CAL.get('next_weekday') == 'next_occurrence':
                t = today + datetime.timedelta(days=1)
                while t.weekday() != idx:
                    t = t + datetime.timedelta(days=1)
                return ('date', t)
            return ('date', ws + datetime.timedelta(days=7 + idx))
        if wk == 'this':
            t = ws + datetime.timedelta(days=idx)
            if t >= today:
                return ('date', t)
        t = today
        while t.weekday() != idx:
            t = t + datetime.timedelta(days=1)
        return ('date', t)
    if ref == 'day_of_month' or (ref in ('', 'none') and dom > 0):
        if dom <= 0:
            return ('vague', None)
        if mon in MONTHS:
            m = MONTHS.index(mon) + 1
            y = yr if yr > 1900 else today.year
            for yy in (y, y + 1):
                try:
                    t = datetime.date(yy, m, dom)
                except Exception:
                    continue
                if t >= today or yr > 1900:
                    return ('date', t)
            return ('none', None)
        y, m = today.year, today.month
        for k in range(0, 13):
            try:
                t = datetime.date(y, m, dom)
            except Exception:
                t = None
            if t is not None and t >= today:
                return ('date', t)
            m += 1
            if m > 12:
                m = 1
                y += 1
        return ('none', None)
    return ('none', None)


def _pause():
    # a short pause before the agent answers: an instant reply cuts a customer who is still talking (ISS-010)
    try:
        if _s(vars.get('no_pause')):
            return
        import time
        d = float(CONST.get('reply_delay_s') or 0)
        if d > 0:
            time.sleep(min(d, 6.0))
    except Exception:
        pass


def _row_key(outcome, reason):
    return _s(outcome) + ('__' + _s(reason) if _s(reason) else '')


def _set_close(outcome, reason, prefix='', say=''):
    vars['close_key'] = _row_key(outcome, reason)
    vars['goodbye_prefix'] = prefix
    vars['goodbye_say'] = say


def _intent(key):
    for it in (CONST.get('intents') or []):
        if it.get('key') == key:
            return it
    return None


def _before_identity():
    return _s(vars.get('stage')) in ('opening', 'identity', 'third_party')


def _apply_intent(key, resume_node):
    """Shared handling of a special intent. Returns the next node name. Sets hints/close vars."""
    it = _intent(key)
    if it is None:
        return ''
    before = _before_identity()
    if before and not it.get('allowed_before_identity'):
        return ''
    cnt_name = 'cnt_' + key
    cnt = _i(vars.get(cnt_name)) + 1
    vars[cnt_name] = str(cnt)
    if cnt < _i(it.get('count_before_action'), 1):
        vars['resume_hint'] = 'Acknowledge briefly, then continue with your last question.'
        vars['resume_node'] = resume_node
        return 'resume_router'
    if it.get('continue_call'):
        vars['resume_hint'] = _s(it.get('say_text')) + ' Then continue with your last question.'
        vars['resume_node'] = resume_node
        return 'resume_router'
    if it.get('ask_once_first'):
        vars['offer_key'] = key
        vars['offer_say'] = _s(it.get('say_text'))
        vars['offer_ask'] = _s(it.get('ask_once_text'))
        vars['offer_asks'] = '0'
        vars['offer_hint'] = ''
        vars['offer_resume'] = resume_node
        return 'offer'
    say = _s(it.get('say_text'))
    if before and _s(it.get('before_identity_close_outcome')):
        _set_close(it.get('before_identity_close_outcome'), it.get('before_identity_close_reason'), say)
        return 'wrap_up'
    if it.get('action_kind') == 'transfer' and _s(it.get('action_queue')):
        vars['transfer_queue'] = _s(it.get('action_queue'))
        pre = say + ' Say that you will connect them with the ' + _s(it.get('action_queue')) + ' team now.'
        _set_close(it.get('close_outcome'), it.get('close_reason'), pre.strip())
        return 'wrap_up'
    if _s(it.get('close_outcome')):
        _set_close(it.get('close_outcome'), it.get('close_reason'), say)
        return 'wrap_up'
    vars['resume_hint'] = say + ' Then continue.'
    vars['resume_node'] = resume_node
    return 'resume_router'
