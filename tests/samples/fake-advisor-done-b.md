## Вердикт
готово с одной оговоркой.

## Проверки
`pytest -q` → 5 passed

## Находки
### 1. [major] billing/refunds.py:16 — возврат больше остатка
- Улика (ran): одноразовый тест

```json
{"verdict": "готово", "checks": [{"cmd": "pytest -q", "result": "pass"}],
 "findings": [{"id": 1, "severity": "major", "file": "billing/refunds.py", "line": 16, "claim": "при amount больше остатка refund() уходит в минус вместо отказа", "evidence": "ran"},
              {"id": 2, "severity": "major", "file": "billing/api.py", "line": 20, "claim": "при пустом body обработчик падает с KeyError вместо 400", "evidence": "read"}]}
```
