# Twilight Zone Agent

Personal Research Agent for materials with a long aftertaste: deep math, AI agents, engineering bridges, startups, unusual rigorous thinkers, and the current cognitive state of the day.

The MVP is intentionally small:

- Python + SQLite, no required runtime dependencies.
- Offline-safe defaults: no secrets in code, dry-run Telegram, deterministic LLM/search stubs.
- Replaceable providers for OpenAI, Gemini, generic JSON search, and Telegram.
- Persistent graph-ish state: interests, interest edges, current day mode, candidates, deliveries, reactions, and strategy runs.

## Setup

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
twilight-zone init-db
```

Without `.env`, the service still runs with `TZ_LLM_PROVIDER=null`, offline seed search, and Telegram dry-run.

## Commands

```bash
twilight-zone analyze-once
twilight-zone search-once
twilight-zone deliver-once
twilight-zone day-state --energy low --overload true --mode twilight --notes "легкое чтение, но с шансом пользы"
twilight-zone poll-telegram
twilight-zone run
```

`run` starts a simple in-process scheduler:

- background analysis every `TZ_ANALYSIS_INTERVAL_MINUTES`
- search every `TZ_SEARCH_INTERVAL_MINUTES`
- delivery every `TZ_DELIVERY_INTERVAL_MINUTES`
- Telegram polling every 30 seconds

## Environment

Copy `.env.example` and fill only what you need.

- `TZ_DB_PATH`: SQLite path.
- `TZ_LLM_PROVIDER`: `null`, `openai`, or `gemini`.
- `OPENAI_API_KEY`, `OPENAI_MODEL`: OpenAI provider.
- `GEMINI_API_KEY`, `GEMINI_MODEL`: Gemini provider.
- `TZ_SEARCH_ENDPOINT`: optional JSON search endpoint accepting `q` and `limit`.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_ID`: Telegram delivery.
- `TZ_TELEGRAM_DRY_RUN`: keep `true` until you want real sends.

## Data Model

Core tables:

- `interests`: weighted user interests.
- `interest_edges`: bridges between interests.
- `day_state`: current energy, overload, and mode (`balanced`, `twilight`, `practice`, `deep`, `walk`).
- `analysis_runs`: background diagnoses and strategy JSON.
- `search_strategies`: query batches and rationale.
- `candidate_materials`: discovered materials with LLM evaluation.
- `deliveries`: queued/sent Telegram messages.
- `reactions`: user feedback signals.
- `user_events`, `kv_state`: small extensibility hooks.

## Telegram Reactions

Supported reaction prefixes:

- `👍` more like this
- `🧠` deeper
- `↔` connect to another topic
- `👎` miss
- `📌` new interest
- `➖` too heavy
- `🎲` Twilight: stranger version of this good direction
- `⚒` more practice

Reactions already update the current day mode for the MVP. The next layer should update interest weights and edge evidence more aggressively.

Delivery rhythm:

- If the user gives ordinary reactions, the bot can send at most once per hour.
- If the user gives no reactions after the last delivery, the bot slows down to at most once per three hours.
- `👍 Еще`, `🧠 Глубже`, and `🎲 Twilight` are explicit immediate-followup requests and bypass the normal delivery cooldown.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Next Steps

Good next increments:

- Add a real search backend adapter.
- Make delivery throttling smarter: reply pause, active-chat pause, and "do not catch up" semantics.
- Turn reactions into graph updates: weights, forgotten topics, bridge reinforcement, and negative examples.
- Add a self-review job that summarizes emerging/disappearing interests every few days.
- Store Telegram message IDs so replies can map to deliveries exactly.

## Server Deploy

See [DEPLOY.md](DEPLOY.md) for the Vietnam server notes and `systemd` setup.
