## Решение
Добавить `assert amount > 0` в `billing/refunds.py:12`.

## Что добавляется
ничего
Файлов изменить: 1.

## Почему не проще
Одна строка.

## Чем доказать
`pytest -q` (не запускал).

```json
{"nothing_needed": false, "new_concepts": [], "files_changed": 1, "proof": "pytest -q", "evidence": "read"}
```
