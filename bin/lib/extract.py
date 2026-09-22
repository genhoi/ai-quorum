#!/usr/bin/env python3
"""Parse CLI logs, assemble role prompts, build the verdict and the usage digest.

    extract.py report   FORMAT RAW          # final answer text of a job
    extract.py meta     FORMAT RAW          # JSON: session_id, turns, tool_calls, cost_usd, duration_ms, tokens
    extract.py progress FORMAT RAW          # one progress line for `quorum status`
    extract.py error    META_JSON           # first error message from a job's meta.json
    extract.py profile  ROOT [--source]     # project section "## Quorum" / "## Совет" from AGENTS.md or CLAUDE.md
    extract.py letters  RUN                 # assign A/B/C to finished advisors (letters.json), print the mapping
    extract.py judge-prompt RUN ROUND TEMPLATE   # judge prompt: template + question + anonymized answers
    extract.py judge-choice REPORT_MD       # JSON {"choice": "A"|"none", "feedback": {...}}
    extract.py claims   RUN                 # done stage: findings of all advisors → claims.json (deduplicated, refuter assigned)
    extract.py refute-prompt RUN JOB TEMPLATE    # refuter prompt for one refuter job
    extract.py verdict  RUN                 # verdict.md to stdout
    extract.py summary  RUN                 # JSON summary of the run for the usage journal
    extract.py digest   HOME [--since D]    # Markdown digest of usage.jsonl + feedback.jsonl

FORMAT: claude-stream-json | codex-jsonl | grok-messages | kimi-stream-json | text
Standard library only.
"""
import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path

FAMILY = {"codex": "openai", "grok": "xai", "glm": "zhipu", "kimi": "moonshot", "kimi-cli": "moonshot",
          "opus": "anthropic", "fable": "anthropic"}


def family_of(backend):
    name, _, variant = backend.partition(":")
    if name == "fake":
        return f"fake-{variant or 'a'}"
    return FAMILY.get(name, name)


# ---------- raw log parsing ----------

def _lines(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _blocks_text(content):
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            out.append(b.get("text", ""))
    return "".join(out)


def _tool_label(name, inp):
    if not isinstance(inp, dict):
        return name
    for k in ("command", "cmd", "file_path", "path", "pattern", "query", "description"):
        v = inp.get(k)
        if isinstance(v, str) and v:
            return f"{name}({v[:90]})"
    return name


class Parsed:
    def __init__(self):
        self.texts = []
        self.final = None
        self.tools = []
        self.session_id = None
        self.turns = None
        self.cost = None
        self.duration_ms = None
        self.model = None
        self.errors = []
        self.tokens_in = None
        self.tokens_cached = None
        self.tokens_out = None

    def report(self):
        if self.final and self.final.strip():
            return self.final.strip()
        for t in reversed(self.texts):
            if t.strip():
                return t.strip()
        return ""

    def meta(self):
        return {
            "session_id": self.session_id, "turns": self.turns, "tool_calls": len(self.tools),
            "cost_usd": self.cost, "duration_ms": self.duration_ms, "model": self.model,
            "tokens_in": self.tokens_in, "tokens_cached": self.tokens_cached, "tokens_out": self.tokens_out,
            "errors": self.errors[-3:],
        }

    def add_usage(self, usage):
        if not isinstance(usage, dict):
            return
        cached = usage.get("cache_read_input_tokens", usage.get("cached_input_tokens", 0)) or 0
        created = usage.get("cache_creation_input_tokens", usage.get("cache_write_input_tokens", 0)) or 0
        raw_in = usage.get("input_tokens", 0) or 0
        total_in = raw_in + cached + created if "cache_read_input_tokens" in usage else max(raw_in, cached)
        out = (usage.get("output_tokens", 0) or 0)
        self.tokens_in = (self.tokens_in or 0) + total_in
        self.tokens_cached = (self.tokens_cached or 0) + cached
        self.tokens_out = (self.tokens_out or 0) + out


def parse_claude(path):
    p = Parsed()
    for ev in _lines(path):
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            p.session_id = ev.get("session_id") or p.session_id
            p.model = ev.get("model") or p.model
        elif t == "assistant":
            msg = ev.get("message", {})
            p.model = msg.get("model") or p.model
            txt = _blocks_text(msg.get("content"))
            if txt.strip():
                p.texts.append(txt)
            for b in msg.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    p.tools.append(_tool_label(b.get("name", "?"), b.get("input")))
        elif t == "result":
            p.session_id = ev.get("session_id") or p.session_id
            p.turns = ev.get("num_turns")
            p.cost = ev.get("total_cost_usd")
            p.duration_ms = ev.get("duration_ms")
            p.add_usage(ev.get("usage"))
            if ev.get("is_error"):
                p.errors.append(str(ev.get("result") or ev.get("error") or "error")[:300])
            elif isinstance(ev.get("result"), str):
                p.final = ev["result"]
    return p


def parse_codex(path):
    p = Parsed()
    for ev in _lines(path):
        t = ev.get("type", "")
        if t == "thread.started":
            p.session_id = ev.get("thread_id") or p.session_id
        elif t == "item.completed":
            item = ev.get("item", {})
            it = item.get("type")
            if it == "agent_message":
                txt = item.get("text") or _blocks_text(item.get("content"))
                if txt and txt.strip():
                    p.texts.append(txt)
            elif it in ("command_execution", "local_shell_call"):
                p.tools.append(_tool_label("shell", {"command": item.get("command", "")}))
            elif it in ("file_change", "patch"):
                p.tools.append("apply_patch")
            elif it == "mcp_tool_call":
                p.tools.append(_tool_label(item.get("tool", "mcp"), item.get("arguments")))
        elif t == "turn.completed":
            p.turns = (p.turns or 0) + 1
            p.add_usage(ev.get("usage"))
        elif t in ("error", "turn.failed"):
            p.errors.append(json.dumps(ev)[:300])
    last = Path(path).with_name("last_message.md")
    if last.exists() and last.read_text(encoding="utf-8", errors="replace").strip():
        p.final = last.read_text(encoding="utf-8", errors="replace")
    return p


def parse_grok_messages(path):
    p = Parsed()
    cur_text, cur_tool = [], None
    for ev in _lines(path):
        t = ev.get("type")
        if t == "message_start":
            cur_text = []
            m = ev.get("message", {})
            p.model = m.get("model") or p.model
            p.session_id = ev.get("session_id") or m.get("session_id") or p.session_id
        elif t == "content_block_start":
            cb = ev.get("content_block", {})
            if cb.get("type") == "tool_use":
                cur_tool = cb.get("name", "?")
                p.tools.append(_tool_label(cur_tool, cb.get("input")))
            elif cb.get("type") == "text" and cb.get("text"):
                cur_text.append(cb["text"])
        elif t == "content_block_delta":
            d = ev.get("delta", {})
            if d.get("type") == "text_delta":
                cur_text.append(d.get("text", ""))
        elif t == "message_stop":
            txt = "".join(cur_text)
            if txt.strip():
                p.texts.append(txt)
            p.turns = (p.turns or 0) + 1
        elif t == "message":
            m = ev.get("message", ev)
            if m.get("role") == "assistant":
                txt = _blocks_text(m.get("content"))
                if txt.strip():
                    p.texts.append(txt)
                for b in m.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        p.tools.append(_tool_label(b.get("name", "?"), b.get("input")))
        elif t == "error":
            p.errors.append(json.dumps(ev)[:300])
    if cur_text and "".join(cur_text).strip() and ("".join(cur_text) not in p.texts):
        p.texts.append("".join(cur_text))
    return p


def parse_kimi(path):
    p = Parsed()
    for ev in _lines(path):
        t = ev.get("type", "")
        if t == "session.resume_hint":
            p.session_id = ev.get("session_id") or p.session_id
            continue
        if ev.get("role") == "assistant":
            content = ev.get("content")
            txt = content if isinstance(content, str) else _blocks_text(content)
            if txt and txt.strip():
                p.texts.append(txt)
            for tc in ev.get("tool_calls") or []:
                fn = (tc or {}).get("function") or {}
                args = fn.get("arguments")
                try:
                    args = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    args = {"command": str(args)}
                p.tools.append(_tool_label(fn.get("name", "?"), args))
            p.turns = (p.turns or 0) + 1
        elif t == "error" or ev.get("role") == "error":
            p.errors.append(json.dumps(ev, ensure_ascii=False)[:300])
    return p


def parse_text(path):
    p = Parsed()
    p.final = Path(path).read_text(encoding="utf-8", errors="replace")
    return p


PARSERS = {
    "claude-stream-json": parse_claude,
    "codex-jsonl": parse_codex,
    "grok-messages": parse_grok_messages,
    "kimi-stream-json": parse_kimi,
    "text": parse_text,
}


def parse(fmt, path):
    if fmt not in PARSERS:
        sys.exit(f"extract.py: unknown format {fmt}")
    if not os.path.exists(path):
        return Parsed()
    return PARSERS[fmt](path)


# ---------- run helpers ----------

def _read(p, default=""):
    p = Path(p)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else default


def _json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def json_block(text, key=None):
    """Last ```json block of a report (optionally the last one holding KEY) → dict, or {}."""
    blocks = re.findall(r"```json\s*\n(.*?)\n\s*```", text or "", flags=re.S)
    for raw in reversed(blocks):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and (key is None or key in data):
            return data
    return {}


def jobs(run, role=None):
    run = Path(run)
    out = []
    for d in sorted(run.iterdir()):
        if d.is_dir() and (d / "status").exists():
            if role is None or _read(d / "role").strip() == role:
                out.append(d)
    return out


def job_status(d):
    return _read(d / "status").strip()


def job_meta(d):
    return _json(d / "meta.json")


def job_answer(d):
    """Answer of a job: for an advisor, the retry answer replaces the first one when it exists."""
    run = d.parent
    retry = run / f"retry-{d.name}"
    if retry.is_dir() and job_status(retry) == "done":
        return _read(retry / "report.md")
    return _read(d / "report.md")


def run_meta(run):
    return _json(Path(run) / "meta.json")


def section(text, *titles):
    """Body of the first markdown section whose heading contains one of TITLES (case-insensitive)."""
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if not m or not any(t.lower() in m.group(2).lower() for t in titles):
            continue
        level = len(m.group(1))
        body = []
        for l2 in lines[i + 1:]:
            m2 = re.match(r"^(#{1,6})\s", l2)
            if m2 and len(m2.group(1)) <= level:
                break
            body.append(l2)
        return "\n".join(body).strip()
    return ""


# ---------- project profile ----------

PROFILE_SOURCES = ("AGENTS.md", "CLAUDE.md", "agents.md", "claude.md")
PROFILE_HEADING = re.compile(r"^(#{1,6})\s*(quorum|совет моделей|совет|external review|внешнее ревью)\b.*$", re.I | re.M)


def project_profile(root):
    root = Path(root)
    for name in PROFILE_SOURCES:
        f = root / name
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        m = PROFILE_HEADING.search(text)
        if not m:
            continue
        level = len(m.group(1))
        rest = text[m.end():]
        stop = re.search(rf"^#{{1,{level}}}\s", rest, re.M)
        body = rest[: stop.start()] if stop else rest
        if body.strip():
            return f"{name} § {m.group(0).lstrip('#').strip()}", body.strip()
    return None, ""


# ---------- judge ----------

LETTERS = "ABCDEFGH"


def letters(run):
    """A/B/C for finished advisors, shuffled once and stored in letters.json."""
    run = Path(run)
    f = run / "letters.json"
    if f.exists():
        return _json(f)
    done = [d.name for d in jobs(run, "advisor") if job_status(d) == "done"]
    random.shuffle(done)
    mapping = {LETTERS[i]: name for i, name in enumerate(done)}
    f.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    return mapping


def judge_prompt(run, round_no, template):
    run = Path(run)
    mapping = letters(run)
    brief = _read(run / "brief.md")
    parts = [_read(template).strip(), "", "---", "", "# Вопрос и вводная исполнителя", "", brief.strip(), ""]
    if round_no > 1:
        prev = run / f"judge-{round_no - 1}"
        fb = json_block(_read(prev / "report.md"), "choice").get("feedback") or {}
        parts += ["# Твои замечания после первого круга (авторы их получили и ответили ниже)", ""]
        for letter in mapping:
            if fb.get(letter):
                parts += [f"- {letter}: {fb[letter]}"]
        parts.append("")
    parts += ["# Решения", ""]
    for letter, name in mapping.items():
        ans = job_answer(run / name)
        parts += [f"## Решение {letter}", "", ans.strip() or "_(ответа нет)_", ""]
    return "\n".join(parts)


def judge_choice(report_md):
    data = json_block(_read(report_md), "choice")
    choice = str(data.get("choice") or "none").strip().upper()
    if choice not in list(LETTERS) + ["NONE"]:
        choice = "NONE"
    return {"choice": "none" if choice == "NONE" else choice, "feedback": data.get("feedback") or {},
            "must_do": data.get("must_do") or []}


# ---------- claims (done stage) and refuters ----------

SEV_ORDER = {"blocker": 0, "critical": 0, "major": 1, "minor": 2, "info": 3}


def _norm_file(f):
    return (f or "").strip().lstrip("./")


def build_claims(run):
    """Findings of all advisors → claims.json: deduplicated by file and line (±15), each assigned
    to a refuter from a different family than every advisor who raised it."""
    run = Path(run)
    advisors = [d for d in jobs(run, "advisor") if job_status(d) == "done"]
    raw = []
    for d in advisors:
        data = json_block(job_answer(d), "findings")
        for f in data.get("findings") or []:
            if isinstance(f, dict) and (f.get("claim") or f.get("title")):
                raw.append(dict(f, _by=d.name))
    raw.sort(key=lambda x: (SEV_ORDER.get(str(x.get("severity", "")).lower(), 9), _norm_file(x.get("file"))))
    groups = []
    for f in raw:
        for g in groups:
            g0 = g[0]
            same = _norm_file(g0.get("file")) and _norm_file(g0.get("file")) == _norm_file(f.get("file"))
            try:
                close = abs(int(g0.get("line") or 0) - int(f.get("line") or 0)) <= 15
            except (TypeError, ValueError):
                close = False
            if same and close:
                g.append(f)
                break
        else:
            groups.append([f])
    names = [d.name for d in advisors]
    judge = _read(run / "judge").strip()
    claims = []
    for i, g in enumerate(groups, 1):
        by = sorted({x["_by"] for x in g})
        families = {family_of(b) for b in by}
        candidates = [n for n in names if family_of(n) not in families]
        refuter = candidates[(i - 1) % len(candidates)] if candidates else (judge if judge and family_of(judge) not in families else "")
        f = g[0]
        claims.append({"id": i, "severity": str(f.get("severity") or "?"), "file": f.get("file"), "line": f.get("line"),
                       "claim": f.get("claim") or f.get("title"), "by": by, "refuter": refuter,
                       "evidence": [str(x.get("evidence") or "") for x in g]})
    (run / "claims.json").write_text(json.dumps(claims, ensure_ascii=False, indent=1), encoding="utf-8")
    return claims


def refute_prompt(run, job, template):
    """Refuter prompt. done stage: the claims assigned to this refuter (claim only, no advisor
    reasoning). plan stage: the winning solution's factual claims about the code."""
    run = Path(run)
    meta = run_meta(run)
    parts = [_read(template).strip(), "", "---", ""]
    if meta.get("stage") == "done":
        claims = [c for c in _json(run / "claims.json", []) if c.get("refuter") == job.split("refute-", 1)[-1]]
        parts += ["# Утверждения на проверку", ""]
        for c in claims:
            loc = f"{c.get('file') or '?'}:{c.get('line') or '?'}"
            parts += [f"## Утверждение {c['id']} [{c.get('severity')}] `{loc}`", "", str(c.get("claim")).strip(), ""]
        parts += ["Для каждого утверждения — отдельный раздел с вердиктом и уликой, затем итоговый JSON:", "",
                  "```json", json.dumps({"results": [{"id": c["id"], "verdict": "confirmed|refuted|unverified",
                                                       "evidence": "команда и строки вывода или file:line"} for c in claims]},
                                        ensure_ascii=False, indent=1), "```", ""]
    else:
        winner = _read(run / "winner").strip()
        ans = job_answer(run / winner) if winner else ""
        parts += ["# Решение на проверку", "", ans.strip(), "",
                  "Выпиши из решения утверждения о коде, от которых зависит его правильность: что уже есть, чего нет,",
                  "что делает указанная строка, что докажет предложенный тест. Не больше восьми, самые весомые первыми;",
                  "мелкие и повторяющиеся не проверяй. Проверь каждое. Итоговый JSON:", "",
                  "```json", json.dumps({"results": [{"id": 1, "claim": "…", "verdict": "confirmed|refuted|unverified",
                                                       "evidence": "…"}]}, ensure_ascii=False, indent=1), "```", ""]
    return "\n".join(parts)


def refute_results(run):
    """Results of all refuter jobs: list of {id, claim, verdict, evidence, refuter}."""
    run = Path(run)
    assigned = {c["id"]: c.get("refuter") for c in _json(run / "claims.json", [])}
    out = []
    for d in jobs(run, "refuter"):
        backend = _read(d / "backend").strip()
        data = json_block(_read(d / "report.md"), "results")
        for r in data.get("results") or []:
            if not isinstance(r, dict):
                continue
            # done stage: a refuter answers only for the claims assigned to it
            if assigned and assigned.get(r.get("id")) not in (None, backend):
                continue
            out.append(dict(r, refuter=backend, _status=job_status(d)))
    return out


# ---------- verdict ----------

def _dur_ms(m, d):
    """Duration from the CLI's own report, else from the started/finished marks (codex reports none)."""
    dur = m.get("duration_ms")
    if not dur and (d / "started").exists() and (d / "finished").exists():
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        try:
            a = datetime.strptime(_read(d / "started").strip(), fmt)
            b = datetime.strptime(_read(d / "finished").strip(), fmt)
            dur = int((b - a).total_seconds() * 1000)
        except ValueError:
            dur = None
    return dur


def _dur(m, d):
    dur = m.get("duration_ms")
    if not dur and (d / "started").exists() and (d / "finished").exists():
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        try:
            a = datetime.strptime(_read(d / "started").strip(), fmt)
            b = datetime.strptime(_read(d / "finished").strip(), fmt)
            dur = int((b - a).total_seconds() * 1000)
        except ValueError:
            dur = None
    return f"{dur // 60000}m {dur % 60000 // 1000:02d}s" if dur else "—"


def _k(n):
    if n is None:
        return "—"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def jobs_table(run):
    out = ["| Роль | Модель | Статус | Время | Токены in / out | Стоимость |", "|---|---|---|---|---|---|"]
    for d in jobs(run):
        m = job_meta(d)
        st = job_status(d) + (f" ({_read(d / 'partial').strip()})" if (d / "partial").exists() else "")
        cost = f"${m['cost_usd']:.2f}" if isinstance(m.get("cost_usd"), (int, float)) else "—"
        out.append(f"| {_read(d / 'role').strip()} | {_read(d / 'backend').strip()} | {st} | {_dur(m, d)} | {_k(m.get('tokens_in'))} / {_k(m.get('tokens_out'))} | {cost} |")
    return out


def verdict(run):
    run = Path(run)
    meta = run_meta(run)
    stage = meta.get("stage", "plan")
    brief = _read(run / "brief.md")
    question = section(brief, "вопрос", "question") or "_(раздел «Вопрос» в брифе не заполнен)_"
    title = {"plan": "Совет до кода", "stuck": "Совет по сбою", "done": "Приёмка"}.get(stage, "Совет")
    out = [f"# {title} — {meta.get('project')} — {meta.get('started', '')[:16].replace('T', ' ')}", "",
           f"Прогон: `{run}`  ", f"Этап: {stage} · советники: {', '.join(meta.get('advisors') or [])}"
           + (f" · судья: {meta.get('judge')}" if stage != "done" else ""), "",
           "## Вопрос", "", question, ""]
    advisors = jobs(run, "advisor")
    done = [d for d in advisors if job_status(d) == "done"]
    failed = [d for d in advisors if job_status(d) != "done"]
    if stage == "done":
        claims = _json(run / "claims.json", [])
        results = {r.get("id"): r for r in refute_results(run)}
        buckets = {"confirmed": [], "refuted": [], "unverified": []}
        for c in claims:
            r = results.get(c["id"]) or {}
            v = str(r.get("verdict") or "unverified").lower()
            buckets.setdefault(v if v in buckets else "unverified", buckets["unverified"]).append((c, r))
        out += [f"## Подтверждено ({len(buckets['confirmed'])}) — чинить", ""]
        for c, r in buckets["confirmed"]:
            out.append(f"- [{c['severity']}] `{c.get('file') or '?'}:{c.get('line') or '?'}` — {c['claim']}  ")
            out.append(f"  нашёл: {', '.join(c['by'])}; проверил {r.get('refuter')}: {r.get('evidence', '')}")
        if not buckets["confirmed"]:
            out.append("_нет_")
        out += ["", f"## Опровергнуто ({len(buckets['refuted'])}) — не чинить; вернуть можно рукой", ""]
        for c, r in buckets["refuted"]:
            out.append(f"- [{c['severity']}] `{c.get('file') or '?'}:{c.get('line') or '?'}` — {c['claim']}  ")
            out.append(f"  нашёл: {', '.join(c['by'])}; опроверг {r.get('refuter')}: {r.get('evidence', '')}")
        if not buckets["refuted"]:
            out.append("_нет_")
        out += ["", f"## Не проверено ({len(buckets['unverified'])}) — решает исполнитель", ""]
        for c, r in buckets["unverified"]:
            out.append(f"- [{c['severity']}] `{c.get('file') or '?'}:{c.get('line') or '?'}` — {c['claim']}  ")
            out.append(f"  нашёл: {', '.join(c['by'])}; {('опровергатель ' + r['refuter'] + ': ' + str(r.get('evidence', ''))) if r else 'опровергатель не отвечал'}")
        if not buckets["unverified"]:
            out.append("_нет_")
        out += ["", "## Вердикты советников", ""]
        for d in done:
            data = json_block(job_answer(d), "findings")
            out.append(f"- {d.name}: {data.get('verdict') or section(job_answer(d), 'вердикт', 'резюме')[:200] or '—'}")
    else:
        mapping = _json(run / "letters.json")
        rounds = [d for d in jobs(run, "judge") if job_status(d) == "done"]
        last = rounds[-1] if rounds else None
        choice = judge_choice(last / "report.md") if last else {"choice": "none"}
        winner = mapping.get(choice["choice"]) if choice["choice"] != "none" else None
        out += ["## Кто есть кто", "", ", ".join(f"{k} = {v}" for k, v in mapping.items()) or "_советники не ответили_", ""]
        if winner:
            out += [f"## Выбор судьи: {choice['choice']} = {winner}", ""]
        elif last:
            out += ["## Судья: приемлемого решения нет", ""]
        else:
            out += ["## Судья не отвечал", ""]
        if last:
            out += [f"_Судья {_read(last / 'backend').strip()}, круг {len(rounds)}._", "", _read(last / "report.md").strip(), ""]
        refs = jobs(run, "refuter")
        if refs:
            out += ["## Проверка решения опровергателем", ""]
            for d in refs:
                out += [f"_{_read(d / 'backend').strip()}, статус {job_status(d)}._", "", _read(d / "report.md").strip() or "_ответа нет_", ""]
        out += ["## Ответы советников", ""]
        for d in done:
            letter = next((k for k, v in mapping.items() if v == d.name), "?")
            out += [f"### {letter} = {d.name}", "", job_answer(d).strip(), ""]
    if failed:
        out += ["## Не ответили", ""]
        for d in failed:
            out.append(f"- {d.name}: {job_status(d)}" + (f" ({_read(d / 'partial').strip()})" if (d / "partial").exists() else ""))
        out.append("")
    out += ["## Служебное", ""] + jobs_table(run)
    return "\n".join(out) + "\n"


# ---------- usage summary and digest ----------

def first_error(meta_path):
    try:
        errs = json.loads(Path(meta_path).read_text(encoding="utf-8")).get("errors") or []
    except Exception:
        return ""
    for e in errs:
        msg = ""
        try:
            o = json.loads(e) if isinstance(e, str) else e
            if isinstance(o, dict):
                msg = o.get("message") or (o.get("error") or {}).get("message") or ""
        except Exception:
            msg = e if isinstance(e, str) else ""
        msg = " ".join(str(msg).split())
        if len(msg) > 8:
            return msg[:100]
    return ""


def run_summary(run):
    run = Path(run)
    meta = run_meta(run)
    out = {"stage": meta.get("stage"), "jobs": {}}
    for d in jobs(run):
        m = job_meta(d)
        out["jobs"][d.name] = {"role": _read(d / "role").strip(), "backend": _read(d / "backend").strip(),
                               "status": job_status(d), "partial": _read(d / "partial").strip() or None,
                               "duration_ms": _dur_ms(m, d), "tool_calls": m.get("tool_calls"),
                               "tokens_in": m.get("tokens_in"), "tokens_out": m.get("tokens_out"), "cost_usd": m.get("cost_usd")}
    if meta.get("stage") == "done":
        claims = _json(run / "claims.json", [])
        res = refute_results(run)
        out["claims"] = len(claims)
        out["confirmed"] = sum(1 for r in res if str(r.get("verdict")).lower() == "confirmed")
        out["refuted"] = sum(1 for r in res if str(r.get("verdict")).lower() == "refuted")
        out["unverified"] = len(claims) - out["confirmed"] - out["refuted"]
    else:
        mapping = _json(run / "letters.json")
        rounds = [d for d in jobs(run, "judge") if job_status(d) == "done"]
        ch = judge_choice(rounds[-1] / "report.md") if rounds else {"choice": "none"}
        out["rounds"] = len(rounds)
        out["winner"] = mapping.get(ch["choice"]) if ch["choice"] != "none" else None
        out["must_do"] = len(ch.get("must_do") or [])
        concepts = {}
        for d in jobs(run, "advisor"):
            data = json_block(job_answer(d), "new_concepts")
            if data:
                concepts[d.name] = {"new_concepts": len(data.get("new_concepts") or []), "files": data.get("files_changed"),
                                    "nothing_needed": bool(data.get("nothing_needed"))}
        out["proposals"] = concepts
        res = refute_results(run)
        if res:
            out["winner_claims"] = {"total": len(res),
                                    "refuted": sum(1 for r in res if str(r.get("verdict")).lower() == "refuted")}
    out["cost_usd"] = round(sum((j.get("cost_usd") or 0) for j in out["jobs"].values()), 2)
    return out


def digest(home, since=None):
    home = Path(home)

    def load(name):
        p = home / name
        if not p.exists():
            return []
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [r for r in rows if not since or r.get("ts", "") >= since]

    usage, notes = load("usage.jsonl"), load("feedback.jsonl")
    # a verdict event carries the run summary nested under "summary": flatten it for the counters below
    usage = [dict(r, **(r.get("summary") or {})) if r.get("event") in ("verdict", "judge_done") else r for r in usage]
    # one record per run for the outcome counters: the verdict, or the last judge round when the run
    # was cleaned before the verdict was written
    outcome = {}
    for r in usage:
        if r.get("event") == "judge_done" and r.get("run") not in outcome:
            outcome[r["run"]] = r
        if r.get("event") == "verdict":
            outcome[r["run"]] = r
    verdict_like = list(outcome.values())
    out = [f"# quorum — журнал ({os.uname().nodename}{', с ' + since if since else ''})", ""]
    consults = [r for r in usage if r.get("event") == "consult"]
    verdicts = [r for r in usage if r.get("event") == "verdict"]
    out.append(f"- советов запущено: {len(consults)} · завершено вердиктом: {len(verdicts)} · убрано до вердикта после суда: {len(verdict_like) - len(verdicts)} · заметок: {len(notes)}")
    if consults:
        stages, harness, projects = {}, {}, set()
        for r in consults:
            stages[r.get("stage")] = stages.get(r.get("stage"), 0) + 1
            harness[r.get("harness")] = harness.get(r.get("harness"), 0) + 1
            projects.add(r.get("project"))
        out.append("- этапы: " + ", ".join(f"{k} ×{v}" for k, v in sorted(stages.items(), key=lambda x: -x[1])))
        out.append("- исполнители: " + ", ".join(f"{k} ×{v}" for k, v in sorted(harness.items(), key=lambda x: -x[1])))
        out.append(f"- проекты: {', '.join(sorted(p for p in projects if p))}")
    plan = [r for r in verdict_like if r.get("stage") in ("plan", "stuck")]
    if plan:
        winners, rounds2, none, nothing = {}, 0, 0, 0
        for r in plan:
            w = r.get("winner")
            if w:
                winners[w] = winners.get(w, 0) + 1
            else:
                none += 1
            if (r.get("rounds") or 0) > 1:
                rounds2 += 1
            nothing += sum(1 for p in (r.get("proposals") or {}).values() if p.get("nothing_needed"))
        out += ["", "## Советы (plan, stuck)", "",
                f"- побеждали: {', '.join(f'{k} ×{v}' for k, v in sorted(winners.items(), key=lambda x: -x[1])) or '—'}",
                f"- без приемлемого решения: {none} · понадобился второй круг: {rounds2}",
                f"- ответов «делать ничего не нужно»: {nothing}",
                f"- средняя стоимость совета: ${sum(r.get('cost_usd') or 0 for r in plan) / len(plan):.2f}"]
    done = [r for r in verdict_like if r.get("stage") == "done"]
    if done:
        c = sum(r.get("claims") or 0 for r in done)
        conf = sum(r.get("confirmed") or 0 for r in done)
        ref = sum(r.get("refuted") or 0 for r in done)
        out += ["", "## Приёмки (done)", "",
                f"- находок всего: {c} · подтверждено: {conf} · опровергнуто: {ref} · не проверено: {c - conf - ref}",
                f"- средняя стоимость приёмки: ${sum(r.get('cost_usd') or 0 for r in done) / len(done):.2f}"]
    stats = {}
    for v in verdict_like:
        for name, j in (v.get("jobs") or {}).items():
            key = f"{j.get('backend')} ({j.get('role')})"
            st = stats.setdefault(key, {"n": 0, "done": 0, "dur": [], "cost": []})
            st["n"] += 1
            st["done"] += 1 if j.get("status") == "done" else 0
            if isinstance(j.get("duration_ms"), (int, float)):
                st["dur"].append(j["duration_ms"])
            if isinstance(j.get("cost_usd"), (int, float)):
                st["cost"].append(j["cost_usd"])
    if stats:
        out += ["", "## Модели по ролям", "", "| Модель (роль) | Запусков | Ответили | Среднее время | Средняя стоимость |", "|---|---|---|---|---|"]
        for key, st in sorted(stats.items()):
            d = sum(st["dur"]) / len(st["dur"]) if st["dur"] else None
            dur = f"{int(d // 60000)}m {int(d % 60000 // 1000):02d}s" if d else "—"
            cost = f"${sum(st['cost']) / len(st['cost']):.2f}" if st["cost"] else "—"
            out.append(f"| {key} | {st['n']} | {st['done']} | {dur} | {cost} |")
    if notes:
        out += ["", "## Заметки исполнителей", ""]
        for n in notes:
            out += [f"### {n.get('ts', '')[:10]} · {n.get('project')} · {n.get('harness')} · {n.get('run')}", "", n.get("note", "").strip(), ""]
    else:
        out += ["", "_Заметок пока нет: после совета исполнитель пишет `quorum feedback RUN \"что помогло, что приняли, что отклонили\"`._"]
    return "\n".join(out) + "\n"


# ---------- CLI ----------

def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "report":
        print(parse(rest[0], rest[1]).report())
    elif cmd == "meta":
        print(json.dumps(parse(rest[0], rest[1]).meta(), ensure_ascii=False))
    elif cmd == "progress":
        p = parse(rest[0], rest[1])
        last = p.tools[-1] if p.tools else "—"
        snippet = (p.texts[-1].strip().splitlines() or [""])[-1][:70] if p.texts else ""
        err = f" ERR: {p.errors[-1][:80]}" if p.errors else ""
        m = p.meta()
        cost = f" ${m['cost_usd']:.2f}" if isinstance(m.get("cost_usd"), (int, float)) else ""
        print(f"{len(p.tools)} tool calls; last: {last}; text: {snippet}{err}{cost}")
    elif cmd == "error":
        print(first_error(rest[0]))
    elif cmd == "profile":
        src, text = project_profile(rest[0])
        if not src:
            sys.exit(1)
        print(src if len(rest) > 1 and rest[1] == "--source" else text)
    elif cmd == "letters":
        print(json.dumps(letters(rest[0]), ensure_ascii=False))
    elif cmd == "judge-prompt":
        print(judge_prompt(rest[0], int(rest[1]), rest[2]))
    elif cmd == "judge-choice":
        print(json.dumps(judge_choice(rest[0]), ensure_ascii=False))
    elif cmd == "claims":
        print(json.dumps(build_claims(rest[0]), ensure_ascii=False))
    elif cmd == "refute-prompt":
        print(refute_prompt(rest[0], rest[1], rest[2]))
    elif cmd == "verdict":
        print(verdict(rest[0]), end="")
    elif cmd == "summary":
        print(json.dumps(run_summary(rest[0]), ensure_ascii=False))
    elif cmd == "digest":
        since = rest[rest.index("--since") + 1] if "--since" in rest else None
        print(digest(rest[0], since), end="")
    elif cmd == "json":
        print(json.dumps(json_block(Path(rest[0]).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
    else:
        sys.exit(f"extract.py: unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
