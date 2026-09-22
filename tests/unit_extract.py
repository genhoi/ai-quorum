#!/usr/bin/env python3
"""Unit tests for bin/lib/extract.py (offline)."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("extract", HERE.parent / "bin" / "lib" / "extract.py")
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


class ParsersTest(unittest.TestCase):
    def test_codex_and_kimi_samples(self):
        p = extract.parse("codex-jsonl", str(HERE / "samples" / "codex.jsonl"))
        self.assertTrue(p.session_id)
        p = extract.parse("kimi-stream-json", str(HERE / "samples" / "kimi-stream.jsonl"))
        self.assertTrue(p.report())

    def test_json_block_picks_last_with_key(self):
        text = "x\n```json\n{\"a\": 1}\n```\ny\n```json\n{\"choice\": \"B\", \"feedback\": {}}\n```\n"
        self.assertEqual(extract.json_block(text, "choice")["choice"], "B")
        self.assertEqual(extract.json_block(text)["choice"], "B")
        self.assertEqual(extract.json_block("no json", "choice"), {})

    def test_section(self):
        text = "# T\n\n## Вопрос\nодин\nдва\n\n## Другое\nтри\n"
        self.assertEqual(extract.section(text, "вопрос"), "один\nдва")
        self.assertEqual(extract.section(text, "нет"), "")

    def test_family(self):
        self.assertEqual(extract.family_of("fake:b"), "fake-b")
        self.assertEqual(extract.family_of("kimi-cli"), "moonshot")
        self.assertEqual(extract.family_of("fable"), extract.family_of("opus"))


class RunTest(unittest.TestCase):
    def _job(self, run, name, role, backend, report, status="done"):
        d = run / name
        d.mkdir()
        (d / "role").write_text(role)
        (d / "backend").write_text(backend)
        (d / "status").write_text(status)
        (d / "report.md").write_text(report, encoding="utf-8")
        return d

    def test_judge_choice_and_letters(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "meta.json").write_text(json.dumps({"stage": "plan", "project": "p", "advisors": ["x", "y"]}))
            (run / "brief.md").write_text("## Вопрос\nчто делать?\n")
            self._job(run, "x", "advisor", "codex", "ответ x")
            self._job(run, "y", "advisor", "grok", "ответ y")
            self._job(run, "z", "advisor", "glm", "", status="timeout")
            m = extract.letters(run)
            self.assertEqual(sorted(m.values()), ["x", "y"])
            self.assertEqual(m, extract.letters(run))  # stable once written
            tpl = run / "judge.md"; tpl.write_text("JUDGE")
            prompt = extract.judge_prompt(run, 1, str(tpl))
            self.assertIn("## Решение A", prompt)
            self.assertNotIn("codex", prompt)
            self._job(run, "judge-1", "judge", "fable", "text\n```json\n{\"choice\": \"a\", \"feedback\": {\"A\": \"f\"}}\n```")
            self.assertEqual(extract.judge_choice(run / "judge-1" / "report.md")["choice"], "A")
            v = extract.verdict(run)
            self.assertIn("## Выбор судьи: A =", v)
            self.assertIn("## Не ответили", v)

    def test_claims_dedup_and_refuter_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "meta.json").write_text(json.dumps({"stage": "done", "project": "p", "advisors": ["codex", "grok"]}))
            (run / "judge").write_text("fable")
            f1 = {"findings": [{"id": 1, "severity": "major", "file": "a.py", "line": 10, "claim": "c1", "evidence": "read"}]}
            f2 = {"findings": [{"id": 1, "severity": "blocker", "file": "./a.py", "line": 20, "claim": "c1b", "evidence": "ran"},
                               {"id": 2, "severity": "major", "file": "b.py", "line": 5, "claim": "c2", "evidence": "read"}]}
            self._job(run, "codex", "advisor", "codex", "```json\n" + json.dumps(f1) + "\n```")
            self._job(run, "grok", "advisor", "grok", "```json\n" + json.dumps(f2) + "\n```")
            claims = extract.build_claims(run)
            self.assertEqual(len(claims), 2)
            merged = next(c for c in claims if c["file"] in ("a.py", "./a.py"))
            self.assertEqual(merged["by"], ["codex", "grok"])
            self.assertEqual(merged["refuter"], "fable")      # both advisor families raised it → the judge's family
            other = next(c for c in claims if c["file"] == "b.py")
            self.assertEqual(other["refuter"], "codex")       # raised by grok → refuted by codex


if __name__ == "__main__":
    unittest.main()
