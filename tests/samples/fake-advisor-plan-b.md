## Решение
Делать ничего не нужно: `billing/api.py:9` уже отклоняет `amount <= 0` до вызова `refund()`, а `refund()`
вызывается только оттуда (`grep -n "refund(" billing/` → одна точка входа).

## Что добавляется
ничего
Файлов изменить: 0.

## Почему не проще
Проще некуда.

## Чем доказать
`pytest -q tests/test_api.py::test_negative_amount_rejected` — запустил, 1 passed.

```json
{"nothing_needed": true, "new_concepts": [], "files_changed": 0, "proof": "pytest -q tests/test_api.py::test_negative_amount_rejected", "evidence": "ran"}
```
