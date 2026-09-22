## Решение
Повторный ответ: делать ничего не нужно, граница в `billing/api.py:9` (`grep -rn "refund(" billing/` → одна точка входа).

## Что добавляется
ничего
Файлов изменить: 0.

## Почему не проще
Проще некуда.

## Чем доказать
`pytest -q tests/test_api.py` — 3 passed.

```json
{"nothing_needed": true, "new_concepts": [], "files_changed": 0, "proof": "pytest -q tests/test_api.py", "evidence": "ran"}
```
