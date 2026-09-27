# Kazbek Assistant

Telegram Business AI assistant for client conversations on Kazbek's personal Telegram account. It uses DeepSeek, persistent SQLite memory, knowledge retrieval, and owner-controlled automation.

## Features

- Telegram Business replies through the connected Business account
- DeepSeek via the OpenAI-compatible API
- Global and per-chat AI controls
- 30-second initial / 5-second active message batching
- 60-minute pause after a manual owner reply
- Persistent SQLite memory, structured lead memory, and compact summaries
- SQLite FTS5 knowledge-base retrieval
- Trusted-contact whitelist with silent handling
- Russian, Kazakh, and English support
- Owner-only admin panel and daily lead reports
- Token-efficient context assembly and rate limiting

## How it works

```text
Telegram Business -> router -> chat/trusted/control checks
    -> debounce -> memory + relevant KB -> DeepSeek -> Business reply
```

## Architecture

| Path | Responsibility |
| --- | --- |
| `app/main.py` | Production entrypoint, database setup, polling, daily report task |
| `app/bot.py` | Business handlers, owner commands, batching, callbacks |
| `app/config.py` | Environment-backed settings |
| `app/db/database.py` | SQLite schema, migrations, persistence, FTS support |
| `app/services/deepseek.py` | DeepSeek requests and layered prompt assembly |
| `app/services/knowledge.py` | Seeded knowledge cards and retrieval |
| `app/services/memory.py` | Structured memory and summaries |
| `app/services/classifier.py` | Controls, language, personal-message, deterministic routing |
| `app/services/report.py` | Deterministic daily owner reports |
| `tests/` | Offline tests with mocked external services |
| `deploy/` | Example systemd unit |

## Tech stack

Python 3.12+, aiogram 3, DeepSeek API, SQLite/aiosqlite with FTS5, asyncio, and python-dotenv.

## Setup

```bash
git clone https://github.com/RealKazbek/assistant.git
cd assistant
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env with local credentials
.venv/bin/python -m app.main
```

The canonical production command is `python -m app.main` from the repository root. The application creates the configured data directory and SQLite database automatically.

## Configuration

See [.env.example](.env.example) for every setting. Required values are `TELEGRAM_BOT_TOKEN`, `DEEPSEEK_API_KEY`, and `OWNER_TELEGRAM_ID`. Important runtime settings include:

- `DATABASE_PATH`: persistent SQLite location
- `INITIAL_REPLY_DEBOUNCE_SECONDS`: 30 seconds for a new or idle conversation
- `ACTIVE_REPLY_DEBOUNCE_SECONDS`: 5 seconds for an active conversation
- `CONVERSATION_IDLE_RESET_MINUTES`: 60 minutes
- `HUMAN_TAKEOVER_MINUTES`: 60 minutes
- `RECENT_MESSAGE_LIMIT`, `SUMMARY_TRIGGER_NEW_MESSAGES`
- `MAX_KNOWLEDGE_CARDS`, `MAX_KNOWLEDGE_CHARS`, `MAX_MEMORY_SUMMARY_CHARS`
- `APP_TIMEZONE`, `DAILY_REPORT_ENABLED`, `DAILY_REPORT_TIME`
- rate-limit, output-token, model, and logging settings

Never commit `.env`, databases, logs, or backups.

## Telegram Business setup

1. Create a bot in BotFather and enable the Telegram Business/Business Mode capability available in the current interface.
2. Open Telegram **Settings -> Telegram Business -> Chatbots**.
3. Connect the bot to the personal Business account and choose the chats it may access.
4. Keep one long-running polling process active. Replies use the incoming `business_connection_id`.

## Owner commands

The configured owner can use these commands in the normal private chat with the bot:

```text
/start
/status
/chats
/profile
/kb
/trusted
/ai_on
/ai_off
/daily_report
/daily_report_yesterday
/memory <chat_id>
/debug_context <chat_id>
```

Additional chat, handoff, knowledge-editing, trusted-contact, and lead-status commands are enforced by `OWNER_TELEGRAM_ID`. Non-owners do not receive admin controls.

## Memory and knowledge

Each DeepSeek request uses layered, bounded context:

1. compact permanent system prompt;
2. relevant SQLite FTS5 knowledge cards;
3. structured client/project memory and a bounded summary;
4. recent meaningful messages.

Raw history remains in SQLite, but the full database is never sent to DeepSeek. Knowledge cards are seeded idempotently and editable only by the owner.

## Reply timing

- New or idle conversation: wait 30 seconds after the last client message.
- Active conversation: wait 5 seconds and batch rapid messages.
- After 60 minutes without meaningful activity, return to initial mode.
- A normal manual owner reply cancels pending AI work and pauses that chat for 60 minutes.
- Controls, trusted-contact handling, and owner commands remain immediate.

## Privacy and security

Credentials are loaded from environment variables. SQLite databases, backups, logs, caches, and virtual environments are ignored by Git. Client history stays in the configured local database. Trusted contacts receive no automatic AI replies and are excluded from lead processing by default. Logs use metadata rather than full message content by default.

## Deployment

This is a persistent long-polling Python service, not a serverless function. Use a Linux VPS with persistent storage and systemd:

```bash
sudo cp deploy/kazbek-assistant.service.example /etc/systemd/system/kazbek-assistant.service
# replace CHANGE_ME values, then:
sudo systemctl daemon-reload
sudo systemctl enable --now kazbek-assistant
sudo journalctl -u kazbek-assistant -f
```

Do not deploy the polling process as a normal Netlify serverless application.

## Development and tests

```bash
.venv/bin/python -m compileall -q app
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests
```

Tests do not require Telegram or DeepSeek credentials and mock external API behavior.

## License

MIT. See [LICENSE](LICENSE).

