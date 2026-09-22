## Утверждение 1
refuted — `sed -n 5,12p billing/api.py`: amount > остатка отклоняется в api.py:9 до вызова refund(); refund() вызывается только оттуда.

## Утверждение 2
confirmed — `python -c "from billing.pricing import apply_discount; print(apply_discount(Decimal('10'), 100))"` → 0.00, но percent=101 → -0.10; вход не ограничен.

## Утверждение 3
unverified — тела запроса в снапшоте нет, обработчик не запускается без веб-сервера.

```json
{"results": [{"id": 1, "verdict": "refuted", "evidence": "billing/api.py:9 отклоняет amount > остатка; единственный вызов refund()"},
             {"id": 2, "verdict": "confirmed", "evidence": "python -c ... percent=101 → -0.10"},
             {"id": 3, "verdict": "unverified", "evidence": "нужен запуск веб-сервера"}]}
```
