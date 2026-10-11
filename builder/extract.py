"""Extract stage: brief text + tool API → facts (1a) → resolution (code) → spec (1b).

The prompts are generic: they describe the schema vocabulary, never a bank's values.
Every call goes through builder.llm.structured (structured outputs, explicit effort, trace line).

CLI (development):
    python -m builder.extract <brief files...> <tool_api.json> --out out/<slot> [--effort high] [--votes 3] [--no-verify] [--facts out/<slot>.facts.json]
writes <out>.facts.json, <out>.resolution.json, <out>.spec.json and <out>.trace.txt
In code: extract(brief_text, api_summary, trace, effort, votes=, verify_inputs_text=) -> (facts, resolution, spec, issues)
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

from builder import llm
from builder.inputs import api_summary, api_text, load_api, load_text_inputs, split_args
from builder.resolve import Resolution, resolve
from builder.schema import Extraction, Fact, Spec, dump_model
from builder.trace import Trace

# ---------------------------------------------------------------------------
# Stage 1a: facts + conflicts
# ---------------------------------------------------------------------------

FACTS_INSTRUCTIONS = """You are the extraction stage of a program that builds a phone agent for a bank's collections calls.
You read the bank's material (one or several documents, each inside a <document> tag) and the tool API, and you return
atomic facts plus a list of conflicts. Another program resolves conflicts and fills a schema from your facts, so
completeness and faithfulness matter more than brevity.

Rules
1. Read everything. Every checkable statement becomes one fact: every number, limit, date, time, window, code,
   required sentence, allowed or forbidden behaviour, ordering rule, question to ask, outcome, reason, condition and exception.
   Tables become one fact per row (or per cell where a row holds several values). Lists of allowed codes become one
   `code_list_entry` fact per code, with the meaning as `text`.
2. One fact = one atomic statement. Split "do X then Y unless Z" into separate facts that share a `topic`; put the exception in `exceptions`.
3. `source_quote` is verbatim from the document (copy the characters; keep digits, quotes and punctuation). Never paraphrase inside it.
4. `doc_label` names the document (its name attribute or heading). `doc_date` is the date the document was written or
   issued, as YYYY-MM-DD, or "" when none is given. `effective_from` is the date from which a rule applies, when the text
   gives one, else "". Do not guess dates.
5. `kind`: `decision` for a rule that governs; `discussion` for questions, proposals, opinions, "we could", "should we",
   drafts and anything that decides nothing; `definition` for terms (business day, floor, band ...); `code_list_entry`
   for an allowed code or value. When one document changes what another says, both are `decision` facts: list the pair
   under `conflicts` and let the resolver decide. Never pick a side yourself and never drop the older rule.
6. `stage` is the call phase the fact belongs to: opening (greeting, who is on the line, confirming identity of the
   person), third_party (someone else answers, callbacks), identity (security questions), debt_statement (naming the
   product, amount, days late), negotiation (dates, amounts, deadlines, attempts, offers), confirmation (read-back),
   recording (the write that records the promise and what to say after), special (paid, dispute, hardship, human,
   payment plan, does not want to talk ...), closing (outcome table, close rules, goodbye), global (applies throughout:
   language, tone, forbidden words, honesty, variables).
7. `topic` is a short snake_case key shared by facts about the same thing (e.g. callback_window, deadline_band,
   identity_question_1, outcome_table_row). `scope` says what it applies to (a product type, a band, a situation);
   `conditions` when; `exceptions` when not. `operator` carries the comparison when there is one
   ('<=', '>=', '==', 'between', 'before', 'after', 'nth_business_day', 'count'). `value` holds the number, date, time,
   code or phrase the fact fixes, as a plain string (a count like "5", a time like "08:30", a date like "2030-01-15", a format like "YYYY-MM-DD", or a code from the tool API).
   `value_kind`: `parameter` when the slot can hold only one value (a limit, count, time, deadline, window end),
   `set_member` when the fact is one item of a list that may hold several (one holiday, one accepted phrase, one code,
   one product type, one outcome row), `none` when there is no value. One fact per list item.
8. `agent_instruction`: what the phone agent must do, in plain imperative English, written so it can be pasted into the
   agent's instructions as-is. "" for facts that are not agent-facing (definitions, variable tables, document metadata).
   Where the document prescribes exact words, keep them verbatim inside the instruction.
9. The tool API is the only way the agent acts. Facts that mention a tool, a field, a code or an enum value must use the
   exact API names. Do not invent tools, fields or codes that are not in the API or the documents.
10. No outside knowledge. If the documents do not say it, there is no fact for it.
11. `conflicts`: every place where two documents (or two passages) give different values or contradictory rules for the
    same topic, including an amendment that changes a number without saying so explicitly. Give the fact ids and a short note.
    Do not resolve. A discussion thread that decides nothing is not a conflict; just mark those facts `discussion`.

12. `documents`: one entry per <document>, in reading order: its label (exactly the doc_label you use), its date if
    given, its kind (policy = base rules; amendment = a memo, update or later brief that changes another document;
    request = a mail commissioning the agent; code_list; discussion = a thread that decides nothing; other), and
    `amends` = the label of the document it changes or builds on when the text says so ("builds on", "every rule of X
    applies unless a rule below replaces it", "update to", "following the review ... the following applies"), else "".
    The resolver gives a declared amendment precedence over the document it amends.

Ids: F001, F002, ... in reading order. Aim for completeness: a dense specification typically yields 60 to 150 facts."""


def extract_facts(brief: str, api: dict[str, Any], trace: Trace | None, effort: str = "high") -> tuple[Extraction, dict]:
    user = (
        "Extract all facts and conflicts from the documents in the system context. "
        "Return the full structured result."
    )
    stable = f"<tool_api>\n{api_text(api)}\n</tool_api>\n\n<documents>\n{brief}\n</documents>"
    return llm.structured("1a facts+conflicts", Extraction, user, stable_system=stable,
                          instructions=FACTS_INSTRUCTIONS, effort=effort, trace=trace)


# ---------------------------------------------------------------------------
# Stage 1b: spec fill from governing facts
# ---------------------------------------------------------------------------

SPEC_INSTRUCTIONS = """You fill a closed, executable specification (the output schema) for a collections phone agent from a list
of governing facts. Code will generate the agent from your output without reading the original documents, so:

1. Use only the facts given. Every leaf has `fact_ids`: cite the fact id(s) that support the value. Never cite a fact
   that does not support the value. If several facts support it, cite them all.
2. Fill every field. For a value the facts do not fix, apply the STRICTER default (the one that lets the agent do less:
   fewer asks, shorter windows, no extra offers, record nothing it is not told to record), cite the closest fact, and
   add an entry to `unresolved` naming the topic and the default you applied. Use "" for text with no value, [] for empty lists, 0 for unknown counts.
3. Closed vocabulary (use these exact tokens):
   - Close leaves: `outcome` from the tool API's close_call outcome enum; `reason` exactly as in the facts' outcome
     table, or "" when the table lists no reason for that outcome.
   - `third_party.callback.allowed_days`: today, tomorrow, next_business_day, any_business_day, within_n_days:<n>.
   - `identity.questions[].numeric_date_order` and `calendar.numeric_date_order`: day_month_year | month_day_year | year_month_day | "".
   - `calendar.next_weekday`: following_calendar_week | next_occurrence; `calendar.this_weekday`: current_week | next_occurrence.
   - `calendar.deadline_rule.kind`: nth_business_day_after_today | nth_calendar_day_after_today | fixed_date.
   - `calendar.business_weekdays`: lower-case English weekday names. `holidays`: ISO dates. `date_source`: the call variable all date rules use.
   - `bands[]`: one row per days-late band, `days_late_min`/`days_late_max` inclusive, `label` as the facts name it.
   - `amounts.accept_range.min/max`: floor | full | <number>. `floor_field_by_type[]`: one row per product type in the tool API's product type enum, with the account field that holds that type's floor.
   - `negotiation.attempts[]`: `amount` = full | floor | floor_if_full_refused; `date` = today | last_business_day_this_week | next_business_day | deadline | nth_business_day:<n>; `if_today_is_that_day` = last_business_day_next_week | next_business_day | ""; `bands_allowed` = band labels, [] = every band.
   - `negotiation.vague.then`: propose_deadline | propose_next_business_day | ask_again.
   - `special_intents[]`: one per situation the documents handle (paid claims, disputes, hardship, plan requests, requests
     for a human, scam or robot questions, refusals to talk, questions the agent cannot answer, ...). `key` snake_case
     from this list when it fits: already_paid, dispute, hardship, wants_plan, wants_human, not_talk, robot_question,
     scam_question, unknown_question; otherwise a short descriptive key. `action_kind` = none | transfer | note | callback;
     `action_queue` and `action_note_reason` from the tool API enums or the facts' code list. `close_outcome` = "" when
     the call continues; then set `continue_call` true. `ask_once_first` when the agent first asks (can I help? shall I
     connect you?) before acting; `declined_close_*` is the close used if the customer declines that offer ("" = continue).
     `count_before_action` = how many times the customer must say it. `before_identity_close_*` when a different close
     applies before identity is verified ("" = same). `precedence`: lower number wins when several apply at once; give the
     intent the documents say comes first the lowest number. `applies_to` = all | current_product | named_product.
   - `closing.outcome_table[]`: one row per outcome/reason pair in the documents' table (a reason-less outcome has reason "").
   - `closing.aggregation.all_noted_as[]` and `else_rule` (first_non_<reason>_note_reason_in_order | "") describe how
     several per-product results combine into one close; leave `all_noted_as` empty and `else_rule` "" when the documents
     describe no combination.
   - `multi_product.enabled` false when the documents describe one product per customer; then fill the other
     multi_product leaves with false/1/[]/"" and cite the fact that says one product.
   - `identity.swapped`: only when the identity tool's response in the tool API has a hint for swapped date parts;
     otherwise hint_value "", instruction "", counts_as_wrong false.
   - `applies_to` = all, unless the documents describe several products per customer and say an intent concerns one of them.
   - `count_before_action`: the number of times the documents say the customer must repeat it ("says twice" = 2);
     "ask once whether you can help, then act if they insist" is `ask_once_first` true with count 1.
   - `language`: the language name in English (e.g. "English"), not a code.
   - `required_phrases[]`: every sentence or question the documents require verbatim (quoted wording), with the stage.
   - `behaviour_rules[]`: one entry for EVERY governing fact with a non-empty `agent_instruction`, with its stage,
     copying the fact's `agent_instruction` (keep required wording verbatim). Do this even when a closed field also
     captures the rule: the closed fields drive the code, the behaviour rules drive the agent's prompts, and both are
     needed. Merge only facts that say the same thing twice.
   - `date_conditional[]`: one entry per date-conditional pair listed under RESOLUTION, with the spec field path it
     changes, `effective_from`, and the value (JSON-encoded) that applies from that date. The main spec holds the value
     in force BEFORE that date.
4. Tool names, field names, enum values and codes must be exactly as in the tool API. Product types come from the tool
   API's product type enum; identity `api_field`s from the identity tool's field enum; queues from the transfer tool's
   queue enum; note reasons from the note tool's enum if it has one, else from the facts' code list.
5. Text leaves (`ask_text`, `intro_instruction`, `say_text`, `fail_message`, ...) are short imperative instructions for
   the agent, in the documents' language. Keep required wording verbatim.
6. Do not add rules, values, names or numbers that are not in the facts."""


def fill_spec(governing: list[Fact], res: Resolution, api: dict[str, Any], trace: Trace | None,
              effort: str = "high", feedback: str = "") -> tuple[Spec, dict]:
    facts_json = json.dumps([f.model_dump() for f in governing], ensure_ascii=False, indent=0)
    res_lines = []
    for o in res.overrides:
        res_lines.append(f"- {o.loser} is overridden by {o.winner} on '{o.topic}' ({o.rule}); it is not in the list.")
    for d in res.date_conditional:
        res_lines.append(f"- DATE-CONDITIONAL '{d.topic}': {d.before_id} applies before {d.from_date}, {d.after_id} from {d.from_date}. Put {d.before_id}'s value in the spec and {d.after_id}'s value under date_conditional.")
    for u in res.unresolved:
        res_lines.append(f"- UNRESOLVED '{u.topic}' between {u.fact_ids}: the stricter {u.chosen_id} governs ({u.how}). Also list it under `unresolved`.")
    if res.dropped_discussion:
        res_lines.append(f"- discussion facts (not in the list, never apply): {', '.join(res.dropped_discussion)}")
    user = (
        "<tool_api>\n" + api_text(api) + "\n</tool_api>\n\n"
        "<governing_facts>\n" + facts_json + "\n</governing_facts>\n\n"
        "<resolution>\n" + ("\n".join(res_lines) or "- no conflicts") + "\n</resolution>\n\n"
        + (f"<verification_feedback>\nA previous attempt had these problems; fix them:\n{feedback}\n</verification_feedback>\n\n" if feedback else "")
        + "Fill the specification from the governing facts."
    )
    return llm.structured("1b spec fill" + (" (re-extract)" if feedback else ""), Spec, user,
                          instructions=SPEC_INSTRUCTIONS, effort=effort, trace=trace)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _one_extraction(brief: str, api_sum: dict[str, Any], trace: Trace | None, effort: str,
                    out_prefix: str | None = None, facts_from: str | None = None) -> tuple[Extraction, Resolution, Spec]:
    if facts_from:  # resume: reuse saved stage-1a output (saves a model call after a crash or a quota stop)
        with open(facts_from, encoding="utf-8") as f:
            ex = Extraction.model_validate(json.load(f))
        if trace:
            trace.kv("facts", f"reused from {facts_from}: {len(ex.facts)} facts, {len(ex.conflicts)} conflicts")
    else:
        ex, _ = extract_facts(brief, api_sum, trace, effort)
        if trace:
            trace.kv("facts", f"{len(ex.facts)} ({sum(f.kind == 'decision' for f in ex.facts)} decisions, "
                              f"{sum(f.kind == 'discussion' for f in ex.facts)} discussion), conflicts listed: {len(ex.conflicts)}")
    res = resolve(ex)
    if trace:
        for n in res.notes:
            trace.line("RESOLVE " + n)
        trace.kv("governing facts", len(res.governing_ids))
    if out_prefix:  # written before 1b so a failed 1b leaves the facts on disk
        _write(out_prefix + ".facts.json", dump_model(ex))
        _write(out_prefix + ".resolution.json", dump_model(res))
    spec, _ = fill_spec(res.governing(ex.facts), res, api_sum, trace, effort)
    return ex, res, spec


def extract(brief: str, api_sum: dict[str, Any], trace: Trace | None, effort: str = "high",
            out_prefix: str | None = None, votes: int = 1, verify_inputs_text: str = "",
            reextract: bool = True, facts_from: str | None = None) -> tuple[Extraction, Resolution, Spec, list]:
    """Full extract stage. Returns (facts, resolution, spec, verify issues).

    votes > 1: that many independent 1a→resolve→1b runs in parallel, merged by field-wise majority (builder.vote);
    the facts and resolution of the first run are kept as the provenance set (fact ids differ between runs, so the
    merged spec's fact_ids are the union of the winning votes' ids and may reference any run's facts).
    verify_inputs_text: when given, builder.verify runs and errors trigger one re-fill (1b) with feedback (T4.3).
    """
    from builder.verify import errors as _errors, feedback as _feedback, verify as _verify

    if votes <= 1:
        ex, res, spec = _one_extraction(brief, api_sum, trace, effort, out_prefix, facts_from)
        all_facts = list(ex.facts)
    else:
        from concurrent.futures import ThreadPoolExecutor

        from builder.vote import vote

        with ThreadPoolExecutor(max_workers=votes) as pool:
            runs = list(pool.map(lambda _: _one_extraction(brief, api_sum, trace, effort), range(votes)))
        ex, res, _ = runs[0]
        merged, disputes = vote([r[2].model_dump() for r in runs])
        spec = Spec.model_validate(merged)
        all_facts = [f for r in runs for f in r[0].facts]
        if trace:
            trace.kv("votes", f"{votes} runs, {len(disputes)} disputed leaves")
            for d in disputes:
                trace.line(f"VOTE DISPUTE {d.path}: {d.how}; chosen={d.chosen!r} votes={d.votes!r}"[:400])
        # provenance for verify: union of all runs' facts and governing ids
        gov = set(res.governing_ids)
        for r in runs[1:]:
            gov |= set(r[1].governing_ids)
        res = res.model_copy(update={"governing_ids": sorted(gov)})
    if out_prefix:
        _write(out_prefix + ".facts.json", dump_model(Extraction(documents=ex.documents, facts=all_facts, conflicts=ex.conflicts)))
        _write(out_prefix + ".resolution.json", dump_model(res))

    issues: list = []
    if verify_inputs_text:
        issues = _verify(spec, all_facts, res, api_sum, verify_inputs_text)
        errs = _errors(issues)
        if trace:
            trace.kv("verify", f"{len(errs)} error(s), {len(issues) - len(errs)} warning(s)")
            for i in issues:
                trace.line("VERIFY " + str(i))
        if errs and reextract:
            spec2, _ = fill_spec(res.governing(all_facts), res, api_sum, trace, effort, feedback=_feedback(issues))
            issues2 = _verify(spec2, all_facts, res, api_sum, verify_inputs_text)
            if len(_errors(issues2)) <= len(errs):
                spec, issues = spec2, issues2
                if trace:
                    trace.kv("verify after re-extract", f"{len(_errors(issues2))} error(s)")
            elif trace:
                trace.warn("re-extract was worse; keeping the first spec")
    if out_prefix:
        _write(out_prefix + ".spec.json", dump_model(spec))
    return ex, res, spec, issues


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="brief text files and the tool API (.json/.yaml)")
    ap.add_argument("--out", default="out/extract", help="output prefix")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--votes", type=int, default=1)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--facts", help="resume from a saved <prefix>.facts.json (skips stage 1a)")
    a = ap.parse_args(argv)
    texts, api_path = split_args(a.inputs)
    brief = load_text_inputs(texts)
    api_sum = api_summary(load_api(api_path))
    trace = Trace(a.out + ".trace.txt")
    trace.start("python -m builder.extract " + " ".join(a.inputs), a.inputs)
    try:
        extract(brief, api_sum, trace, a.effort, out_prefix=a.out, votes=a.votes,
                verify_inputs_text="" if a.no_verify else brief, facts_from=a.facts)
        trace.end("ok")
        return 0
    except Exception as e:  # noqa: BLE001
        trace.warn(f"extract failed: {type(e).__name__}: {e}")
        trace.end("failed")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
