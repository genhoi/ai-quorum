#!/usr/bin/env bash
# Offline test suite: no API keys, no network. Run from anywhere: tests/ci.sh
set -euo pipefail
SK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
Q="$SK/bin/quorum"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export QUORUM_HOME="$TMP/state" QUORUM_CONFIG="$TMP/none.env" QUORUM_FAKE=1 FAKE_DELAY=0 QUORUM_WAIT_MAX=60
unset CODEX_THREAD_ID CODEX_MODEL CODEX_EFFORT QR_CODEX_PARENT_ERROR
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*" >&2; exit 1; }

echo "== syntax"
for f in "$Q" "$SK"/bin/lib/*.sh "$SK"/bin/backends/*.sh "$SK"/tests/*.sh; do bash -n "$f"; done; pass "bash -n"
python3 -m py_compile "$SK"/bin/lib/extract.py "$SK"/bin/lib/codex_context.py "$SK"/tests/unit_extract.py; pass "py_compile"
if command -v shellcheck >/dev/null; then
  shellcheck -S warning -e SC1091,SC2086,SC2046,SC2155 "$Q" "$SK"/bin/lib/*.sh "$SK"/bin/backends/*.sh "$SK"/tests/*.sh; pass "shellcheck"
else echo "  - shellcheck not installed, skipped"; fi

echo "== unit tests (extract.py)"
python3 -m unittest -q "$SK/tests/unit_extract.py" 2>&1 | tail -1

echo "== fixture repository"
FX="$TMP/fixture"; mkdir -p "$FX"; cd "$FX"
git init -q -b main; git config user.email ci@example.com; git config user.name ci
mkdir -p billing; printf 'def refund(p, amount):\n    return p.amount - amount\n' > billing/refunds.py
printf 'from billing.refunds import refund\n\ndef post_refund(payment, body):\n    amount = body["amount"]\n    if amount <= 0 or amount > payment.amount:\n        return {"error": "invalid"}\n    return {"remaining": refund(payment, amount)}\n' > billing/api.py
printf 'vendor/\n' > .gitignore; mkdir -p vendor; echo lib > vendor/lib.txt
git add -A; git commit -qm init
printf '# fixture\n\n## Quorum\n\n- Тесты: `python3 -m pytest -q`\n' > CLAUDE.md
"$Q" config > "$TMP/out"; grep -q 'QUORUM_JUDGE *fable' "$TMP/out"; pass "config prints defaults"
"$Q" brief --out "$TMP/brief.md" >/dev/null 2>&1; grep -q '^## Вопрос' "$TMP/brief.md"; pass "brief template"
grep -q 'Профиль проекта' "$TMP/brief.md"; pass "brief picks the project profile from CLAUDE.md"
printf '## Задача\nОтклонять возврат на ноль.\n\n## Вопрос\nНужна ли проверка в refund()?\n' > "$TMP/q.md"

echo "== plan stage: three advisors, judge picks B, refuter checks the winner"
RUN="$("$Q" consult --brief "$TMP/q.md" --advisors fake:a,fake:b,fake:c --judge fake:x 2>/dev/null)"
[ -d "$RUN/fake:a/snapshot" ] && [ -f "$RUN/fake:a/snapshot/vendor/lib.txt" ]; pass "advisor snapshots with copied deps"
grep -q 'Профиль проекта' "$RUN/prompt.md"; pass "advisor prompt carries the brief and the profile"
for _ in 1 2 3 4 5 6; do "$Q" wait "$RUN" --interval 1 --max 20 >/dev/null && break; done
[ -f "$RUN/verdict.md" ] || fail "no verdict.md"
WIN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["B"])' "$RUN/letters.json")"   # the stub judge always picks B
grep -q "^## Выбор судьи: B = $WIN" "$RUN/verdict.md"; pass "verdict names the winner (letters resolved)"
REF="$(ls -d "$RUN"/refute-* | head -1)"; [ -n "$REF" ] && [ "$(cat "$REF/backend")" != "$WIN" ]; pass "refuter from another family checked the winner"
grep -q 'confirmed' "$RUN/verdict.md"; pass "refuter results in the verdict"
grep -q 'Решение [ABC]' "$RUN/judge-1/prompt.md" && ! grep -q 'fake:' "$RUN/judge-1/prompt.md"; pass "judge prompt is anonymized"
python3 - "$RUN/summary.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
letters = json.load(open(sys.argv[1].replace("summary.json", "letters.json")))
assert s["stage"] == "plan" and s["winner"] == letters["B"] and s["rounds"] == 1, s
assert s["proposals"]["fake:b"]["nothing_needed"] is True and s["proposals"]["fake:a"]["new_concepts"] == 2, s
PY
pass "summary.json: winner, rounds, proposals"
"$Q" feedback "$RUN" "принято: ничего не менять" >/dev/null; grep -q 'принято' "$QUORUM_HOME/feedback.jsonl"; pass "feedback note"

echo "== plan stage: judge finds nothing acceptable → one retry round → judge again"
RUN2="$("$Q" consult --brief "$TMP/q.md" --advisors fake:a,fake:b --judge fake:none --no-refute 2>/dev/null)"
for _ in 1 2 3 4 5 6 7 8; do "$Q" wait "$RUN2" --interval 1 --max 20 >/dev/null && break; done
[ -d "$RUN2/retry-fake:a" ] && [ -d "$RUN2/judge-2" ]; pass "retry jobs and a second judge round"
grep -qE 'нет улики|тест не назван' "$RUN2/retry-fake:a/prompt.md"; pass "retry message carries the judge's feedback for that letter"
grep -q 'Повторный ответ' "$RUN2/judge-2/prompt.md"; pass "second judge round sees the retry answers"
grep -q 'приемлемого решения нет' "$RUN2/verdict.md"; pass "verdict reports no acceptable solution"

echo "== done stage: findings → claims → refuters from other families"
echo "    return p.amount - amount - 1" >> billing/refunds.py   # uncommitted change to accept
RUN3="$("$Q" consult --brief "$TMP/q.md" --stage "done" --advisors fake:a,fake:b --judge fake:x 2>/dev/null)"
grep -q 'Этап: \*\*приёмка\*\*' "$RUN3/header.md" && grep -q 'refunds.py' "$RUN3/header.md"; pass "acceptance header with the diff stat"
for _ in 1 2 3 4 5 6; do "$Q" wait "$RUN3" --interval 1 --max 20 >/dev/null && break; done
python3 - "$RUN3/claims.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
assert len(c) == 3, c                                   # refunds.py:14 and :16 merged, pricing, api
merged = next(x for x in c if x["file"] == "billing/refunds.py")
assert merged["by"] == ["fake:a", "fake:b"] and merged["refuter"] == "fake:x", merged   # both families raised it → the judge refutes
assert all(x["refuter"] for x in c), c
PY
pass "claims deduplicated and assigned to a refuter from another family"
grep -q '^## Подтверждено (1)' "$RUN3/verdict.md" && grep -q '^## Опровергнуто (1)' "$RUN3/verdict.md" && grep -q '^## Не проверено (1)' "$RUN3/verdict.md"; pass "verdict buckets confirmed / refuted / unverified"
! grep -q 'Улика (read)' "$RUN3/refute-fake:b/prompt.md"; pass "refuter prompt carries claims only, not the advisors' reasoning"

echo "== journal and digest"
"$Q" digest > "$TMP/out"; grep -q 'советов запущено: 3' "$TMP/out"; pass "digest counts consults"
grep -q "$WIN ×1" "$TMP/out"; pass "digest counts winners"
"$Q" clean --all >/dev/null; [ -z "$(ls -d "$QUORUM_HOME"/runs/fixture-* 2>/dev/null)" ]; pass "clean removes runs and worktrees"
[ -z "$(git worktree list | grep -v "$FX" || true)" ]; pass "no dangling worktrees"
echo "all good"
