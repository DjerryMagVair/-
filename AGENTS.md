# AGENTS.md — Bridge Security Audit Pipeline

## Контекст
Аналитический пайплайн аудита мостовых протоколов (методология уровня
Slither/Mythril): сбор данных → проверка инвариантов → регрессионные тесты → отчёт.

Классы инцидентов (по классификации DeFiLlama): Unbacked Mint, Message Spoofing,
Key Compromise, Input Validation.

Пайплайн: QUEUE → STAGE 1 (TRIAGE) → STAGE 2 (CHECKLIST) → STAGE 3 (FORK invariants).
STATE.md — единственный источник правды.

## Роли
- **Strategist (sandbox / локальная модель):** только вердикты в `verdicts/` + `PROGRESS.md`.
  Не делает RPC. Не трогает `STATE.md` / `data/` / `scripts/`.
- **Cursor (исполнитель):** скрипты, RPC, forge, `STATE.md`, `data/`, `queue/current.json`.
- Контракт и цикл: см. **HANDOFF.md** (обязателен).
- Применить вердикты: `python3 scripts/apply_verdicts.py`

## Структура
```
├── AGENTS.md
├── STATE.md
├── config/rpc.json
├── scripts/
│   ├── lib/rpc.py
│   ├── lib/state.py
│   ├── collect_candidates.py
│   ├── stage1_triage.py
│   ├── stage2_checklist.py
│   └── stage3_fork/
├── data/<addr>/
└── findings/
```

## Ограничения
- RPC ≤ 10 на кандидата на stage.
- User-Agent: Mozilla/5.0 во всех HTTP-запросах.
- Селекторы вычислять из сигнатур (Keccak-256), не гадать.
- Большие JSON → data/<addr>/; в stdout только таблица.
- Перед выходом ОБЯЗАТЕЛЬНО обновить STATE.md (stage + CURSOR).
- Finding — только при упавшем инвариант-тесте на форке; иначе гипотеза.
- Stage 3 — регрессионные тесты безопасного поведения (assert инвариантов),
  не payload для атаки.

## Примечания по источникам
- Адреса мостов — только из `config/bridge_allowlist.json` (TokenBridge/Pool/SpokePool…).
  DefiLlama `address` **не** используется (часто token/governance).
- DefiLlama `GET /protocols` (category Bridge*) — только TVL + `listedAt` для score.
- Hunt score = `tvl × age × custom × chain × audit × vanilla`
  (mid $0.5–30M и age&lt;12м вверх; mega-TVL / audited / vanilla OP-Arb вниз).
- Адреса только из allowlist (docs). `./run.sh discover` → `data/discovery.json`
  (Llama = TVL/age + needs-address, без постановки в QUEUE).
- Перед QUEUE: `eth_getCode` + explorer verified + `validate_bridge_surface`.
- Адрес в EXCLUDED → skip (re-audit только с `./run.sh collect --force`).
- RPC: primary + fallbacks в `config/rpc.json` (цепи: ethereum, base, arbitrum, bsc, ink, robinhood).

## Команды
```
./run.sh discover
./run.sh collect
./run.sh stage1 <addr>
./run.sh stage2 <addr>
./run.sh stage3 <addr>
```
