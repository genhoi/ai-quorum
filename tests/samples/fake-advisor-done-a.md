## Вердикт
не готово: возврат больше остатка проходит.

## Проверки
`pytest -q` → 5 passed

## Находки
### 1. [blocker] billing/refunds.py:14 — возврат больше остатка
- При каком входе: amount = остаток + 1
- Система делает: списывает, вместо: отказ
- Улика (read): refunds.py:14 нет сравнения с остатком
- Чем грозит: деньги

### 2. [major] billing/pricing.py:6 — скидка 100% даёт отрицательную сумму
- Улика (read): pricing.py:6

```json
{"verdict": "не готово", "checks": [{"cmd": "pytest -q", "result": "pass"}],
 "findings": [{"id": 1, "severity": "blocker", "file": "billing/refunds.py", "line": 14, "claim": "при amount больше остатка refund() списывает сумму вместо отказа", "evidence": "read"},
              {"id": 2, "severity": "major", "file": "billing/pricing.py", "line": 6, "claim": "при percent=100 apply_discount возвращает отрицательную сумму вместо нуля", "evidence": "read"}]}
```
