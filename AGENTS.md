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
- DefiLlama `GET /bridges` часто 402 (paid). `collect_candidates.py`
  пробует `/bridges`, затем fallback на `GET /protocols` (category содержит Bridge),
  TVL > $1M, адрес вида `ethereum:0x…`.
- Поле `address` у Llama часто = token/governance. В QUEUE только после
  `validate_bridge_surface(addr) == true` (≥2 non-empty eth_call probes).
- RPC: primary + fallbacks в `config/rpc.json` (llamarpc может отдавать 525).
- EXCLUDED дедуп по **address** и по (name, chain).

## Команды
```
./run.sh collect
./run.sh stage1 <addr>
./run.sh stage2 <addr>
./run.sh stage3 <addr>
```
