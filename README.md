# Telegram Business AI assistant

Production-oriented local assistant using Python 3.12, aiogram 3, SQLite, and DeepSeek's OpenAI-compatible API. It listens to Telegram Business updates and replies through the same `business_connection_id`, so replies are sent on behalf of the connected Business account.

## Run locally

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.main
```

Copy `.env.example` to `.env` and fill in the values. The real `.env` is ignored by git and must never be committed. `DATABASE_PATH` controls the persistent SQLite location; the existing installation defaults to `data/assistant.db` so upgrades do not silently create a new database.

The production entrypoint from the repository root is:

```bash
.venv/bin/python -m app.main
```

## Telegram setup

1. In BotFather create the bot and enable Telegram Business / Business Mode in the bot settings (the exact label can vary with Telegram's current UI).
2. In Telegram, open **Settings → Telegram Business → Chatbots**.
3. Select this bot, connect it to the personal Business account, and choose which chats it may access.
4. Keep the local process running. Telegram will deliver `business_connection` and `business_message` updates by long polling.

The bot uses `business_connection_id` for outgoing replies. It ignores groups/channels, empty messages, duplicates, bot loops, and unsupported media; text captions are supported.

## Commands

Only the configured owner ID can use control commands in a normal bot chat. Global controls: `/ai_on`, `/ai_off`, `/ai_status`, `/pause_15`, `/pause_60`, `/status`, `/pause`, `/resume`. Per-chat controls: `/chats`, `/chat_info 123456789`, `/chat_on 123456789`, `/chat_off 123456789`, `/chat_status 123456789`, `/handoff 123456789`, `/unhandoff 123456789`. Profile controls: `/profile`, `/profile_set timezone Asia/Almaty`, `/profile_delete timezone`.

Global and per-chat state, profile data, handoffs, manual takeover pauses, and conversation history persist in SQLite. `/pause` and `/resume` map to global AI off/on. A human-handoff phrase pauses that chat indefinitely; `/unhandoff` clears it. When an incoming Business update is reliably identified as sent by the configured owner, that chat is paused for `HUMAN_TAKEOVER_MINUTES` (default 60). Bot-generated messages are not treated as owner activity.

## Configuration

See `.env.example` for all variables: database path, model, batching windows, idle reset, history limits, knowledge limits, rate limit, human takeover duration, reports, timezone, and log level. Data directories are created automatically. Logs contain IDs and lengths, not message text or secrets.

## Tests and deployment

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests
```

For a VPS, install Python 3.12, copy the repository, create `.venv`, configure environment variables, and keep the configured `DATABASE_PATH` on persistent disk. Long polling requires one continuously running Python process; this application is not a Netlify/serverless function.

An installable unit template is provided at `deploy/kazbek-assistant.service.example`. Copy it to `/etc/systemd/system/kazbek-assistant.service`, replace `CHANGE_ME`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kazbek-assistant
sudo journalctl -u kazbek-assistant -f
```

Back up the SQLite database before upgrades. Never copy `.env`, database files, logs, or conversation backups into a public repository.

For a deployment smoke check:

```bash
.venv/bin/python -m compileall -q app
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests
```

## Knowledge, memory, and reports

The assistant stores a seeded SQLite knowledge base with FTS5 retrieval. Only relevant cards are included in each DeepSeek request, together with a compact per-chat memory and the last six messages. Structured memory is updated from the conversation and summarized after the configured threshold; the full raw history remains in SQLite.

Owner commands include `/kb`, `/kb_search <query>`, `/kb_show <key>`, `/kb_set <key> <category> <content>`, `/kb_enable`, `/kb_disable`, `/kb_delete`, `/memory <chat_id>`, `/memory_clear <chat_id>`, `/lead_status <chat_id> <status>`, `/daily_report`, `/daily_report_yesterday`, and `/debug_context <chat_id>`. The daily report is generated deterministically at 00:00 Asia/Almaty and sent only to the owner.

Trusted contacts use `/trusted`, `/trusted_add <chat_id_or_user_id>`, `/trusted_remove <chat_id_or_user_id>`, `/trusted_info <id>`, `/trusted_note <id> <text>`, and `/chat_type <chat_id> trusted|business|personal|unknown`. Trusted contacts are silent by default and never trigger knowledge retrieval, lead memory, or DeepSeek. Russian, Kazakh, and English are supported; personal messages get a deterministic fallback, mixed business messages keep the business flow, and confidently unsupported languages receive a fixed fallback without an API request.

Business client messages use per-chat batching: the first reply after a new/idle conversation waits 30 seconds after the last message; after a successful AI reply, active conversations wait 5 seconds. After 60 minutes without activity the next batch returns to the 30-second initial mode. Messages are stored immediately and one combined DeepSeek request is made after silence. A normal manually sent owner message cancels that chat's pending batch, stores the owner message, and pauses automatic replies for 60 minutes. Control phrases remain immediate. Pending messages have durable processed markers and are rescheduled after restart; messages covered by manual takeover are not sent later as stale replies.

## Troubleshooting

- No Business messages: confirm Business Mode, the Telegram Business chatbot connection, and allowed chat categories.
- Unauthorized bot: verify the token with BotFather and restart.
- AI fallback responses: inspect logs for the exception type and check DeepSeek balance/API availability.
- To clear one chat's stored AI history, delete its rows from `messages` and its `conversations` row in SQLite while the bot is stopped.
