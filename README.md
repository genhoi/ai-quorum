<p align="center">
  <img src="docs/assets/hero.png" alt="Three advisors hold plans of different sizes, a judge at a lectern points at the smallest one, a refuter examines it through a magnifying glass, discarded scraps lie on the floor" width="100%">
</p>

# quorum — a council of models for the implementing agent

A skill for coding agents (Claude Code, Codex, Kimi, Grok). At three points of a task the
implementer asks several models from different families for advice. The models answer
independently in disposable snapshots of the repository, where they can read the code and run
the tests. A judge from yet another family picks the simplest correct answer by explicit criteria.
A refuter must disprove every claim with evidence from the code or a test; only what survives
reaches the implementer.

The models never debate each other. Debate in rounds makes answers worse; independence plus a
judge makes them better (`references/method.md`, in Russian, with the papers).

Русская версия: [README.ru.md](README.ru.md). Prompts and reports are in Russian for now.

## How it is used

The user tells the implementer: "implement SMSGATE-1121 and consult codex, grok, glm".
The implementer consults at three points and no more often:

1. **Before code**: a half-page plan and the one place where there is a choice. The judge picks
   a variant; the implementer takes it whole together with the "must do" list.
2. **Mid-way, at most once**: a test fails and the cause is not understood after two attempts.
3. **Before saying "done"**: the advisors run the tests, linters and e2e from the brief
   themselves and name only what blocks; the refuter drops what is not proven; the implementer
   fixes what is confirmed.

A single consultation without implementation: "ask codex, grok, glm: store the status in a
column or in a separate table". The judge: "judge opus" or `quorum config set QUORUM_JUDGE opus`.

```bash
quorum brief --out /tmp/q.md            # brief template; fill it in
quorum consult --brief /tmp/q.md        # --stage plan|stuck|done, --advisors, --judge, --plan FILE
quorum wait RUN --max 110               # first line: STATE: ready | STATE: running (call again)
cat RUN/verdict.md
quorum feedback RUN "what helped, what was accepted, what was rejected"
quorum clean RUN
```

## What the verdict holds

Before code and when stuck: who is who (the judge's letters and the models), the judge's choice
with a table by criteria, "must do", "do not take", the refuter's check of the chosen solution,
the advisors' answers. At acceptance: confirmed (fix), refuted (do not fix, can be brought back
by hand), unverified (the implementer decides), the advisors' verdicts.

## Cost

Codex, Grok, GLM and Kimi run on subscriptions. The judge (Claude Fable) reads three short
answers: about a dollar per call. A consultation before code: 15–40 minutes, three subscription
runs and one judge call.

## Setup

`references/setup.md` (Russian). Check: `quorum doctor`. Offline suite: `tests/ci.sh`.

```bash
git clone https://github.com/genhoi/ai-quorum ~/projects/genhoi/ai-quorum
ln -sfn ~/projects/genhoi/ai-quorum ~/.claude/skills/quorum     # Claude Code
ln -sfn ~/projects/genhoi/ai-quorum ~/.agents/skills/quorum     # kimi, gemini, copilot
ln -sfn ~/projects/genhoi/ai-quorum ~/.codex/skills/quorum      # codex
ln -sfn ~/projects/genhoi/ai-quorum ~/.grok/skills/quorum       # grok
ln -sfn ~/projects/genhoi/ai-quorum/bin/quorum ~/.local/bin/quorum
```

## Journal

`~/.local/state/quorum/usage.jsonl` holds run events without answer texts: stages, who won, how
many findings were confirmed and refuted, time and cost per role. `feedback.jsonl` holds the
implementers' notes. `quorum digest --since 2026-09-22` renders everything as Markdown for a
retrospective.

MIT license.
