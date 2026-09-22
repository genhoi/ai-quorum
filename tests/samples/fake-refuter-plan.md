## Утверждение 1: api.py:9 отклоняет amount <= 0
confirmed — `sed -n 9p billing/api.py` → `if amount <= 0 or amount > payment.amount - payment.refunded:`.

## Утверждение 2: refund() вызывается только из api.py
confirmed — `grep -rn "refund(" billing/` → одна строка, billing/api.py:11.

```json
{"results": [{"id": 1, "claim": "api.py:9 отклоняет amount <= 0", "verdict": "confirmed", "evidence": "billing/api.py:9"},
             {"id": 2, "claim": "refund() вызывается только из api.py", "verdict": "confirmed", "evidence": "grep -rn refund( billing/ → api.py:11"}]}
```
