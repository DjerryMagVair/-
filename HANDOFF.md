# HANDOFF — Cursor ↔ Strategist (sandbox)

Окончательный контракт. Транспорт = **git** (GitHub).  
Два писателя **никогда** не правят один и тот же файл.

## Роли

| Кто | Среда | Пишет | Читает |
|-----|--------|-------|--------|
| **Cursor** (исполнитель) | `/home/djerry/repos/dash-repo` | `STATE.md`, `data/`, `queue/`, `scripts/`, `findings/` | `verdicts/` |
| **Strategist** (локальная модель / sandbox) | clone того же репо | `verdicts/**`, `PROGRESS.md` | всё остальное **RO** |

Strategist **не** делает RPC, forge, collect. Только вердикты по JSON-отчётам.

## Дерево

```
dash-repo/
├── STATE.md                 # ТОЛЬКО Cursor
├── queue/
│   └── current.json         # ТОЛЬКО Cursor — зеркало CURSOR + paths
├── data/<addr>/
│   ├── stage1.json          # ТОЛЬКО Cursor (RPC)
│   ├── stage2.json
│   └── stage3.json          # результат forge / invariant run
├── verdicts/
│   ├── stage1/<addr>.json   # ТОЛЬКО Strategist
│   ├── stage2/<addr>.json
│   └── stage3/<addr>.json
├── findings/                # ТОЛЬКО Cursor (после FINDING + упавший тест)
└── PROGRESS.md              # ТОЛЬКО Strategist (append-only лог)
```

## Схема вердикта (`verdicts/stageN/<addr>.json`)

```json
{
  "addr": "0xa45b…",
  "stage": 1,
  "verdict": "STAGE2",
  "reason": "bridge_surface + Ownable owner; need mint/lock access checks",
  "evidence": [
    "stage1: stargateType+owner",
    "eip1967_admin: null"
  ],
  "next_cmd": "./run.sh stage2 0xa45b5130f36cdca45667738e2a258ab09f4a5f7f",
  "ts": "2026-11-25T12:00:00Z",
  "agent": "strategist"
}
```

Допустимые `verdict` по stage:

| stage | verdict |
|-------|---------|
| 1 | `SAFE` \| `EXCLUDED` \| `STAGE2` |
| 2 | `SAFE` \| `EXCLUDED` \| `FORK` |
| 3 | `SAFE` \| `HYPOTHESIS` \| `FINDING` |

- `FINDING` — только если в `data/<addr>/stage3.json` есть `invariant_failed: true` (или forge test failed на инварианте). Иначе `HYPOTHESIS`.
- `next_cmd` — одна shell-команда для Cursor, или `null`.

## Цикл (1 кандидат = 1 ход)

```
Cursor:  pull → apply_verdicts → run stageN → push data/ + STATE + queue/
You:     «Strategist: pull и вердикт»
Strategist: pull → читать queue/current.json + data/<addr>/stageN.json
            → писать verdicts/stageN/<addr>.json → push
Cursor:  pull → apply_verdicts (STATE) → выполнить next_cmd → push
```

Правило: **пока нет нового файла в `verdicts/` — Cursor не двигает stage сам.**

## Git / доступ для sandbox

1. Репо: `https://github.com/DjerryMagVair/-` (лучше сделать private).
2. Strategist: fine-grained PAT, scope только этот репо:
   - Contents: Read and Write
   - Metadata: Read
3. Один раз в sandbox:
   ```bash
   git clone https://<PAT>@github.com/DjerryMagVair/-.git dash-repo
   cd dash-repo && git checkout cursor/bridge-audit-pipeline-8342
   ```
4. Каждая сессия strategist:
   ```bash
   git pull --ff-only
   # …писать verdicts/… и PROGRESS.md…
   git add verdicts/ PROGRESS.md
   git commit -m "verdict: stage1 <addr> → STAGE2"
   git push
   ```
5. Cursor на машине djerry:
   ```bash
   git pull --ff-only
   python3 scripts/apply_verdicts.py
   # затем next_cmd из вывода / queue/current.json
   git push
   ```

SSH sandbox не нужен — только HTTPS + PAT.

## Почему не один STATE.md на двоих

Merge-конфликты и «кто последний».  
STATE — реестр исполнителя. Вердикты — события. Cursor применяет события скриптом.

## Что Strategist НЕ делает

- не правит `STATE.md`, `data/`, `scripts/`, `queue/`
- не пишет exploit PoC / forge tests
- не клонирует чужие ветки без checkout согласованной working branch
- не берёт >1 кандидата за сессию

## Старт прямо сейчас

Активный кандидат уже в очереди (после `git pull`):

- addr: `0xa45b5130f36cdca45667738e2a258ab09f4a5f7f`
- stage: 1 done → ждём `verdicts/stage1/0xa45b5130f36cdca45667738e2a258ab09f4a5f7f.json`
- отчёт: `data/0xa45b5130f36cdca45667738e2a258ab09f4a5f7f/stage1.json`
