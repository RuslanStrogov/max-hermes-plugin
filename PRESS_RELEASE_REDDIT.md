# Reddit / Hacker News — Show HN

## Title
Show HN: MAX Hermes — Connect AI Agent Hermes to MAX Messenger (Russian Telegram alternative)

## Body
I built two open-source projects to connect [Hermes Agent](https://hermes-agent.nousresearch.com) (an open-source AI agent platform) to [MAX](https://max.ru), a Russian messenger with a Bot API similar to Telegram.

**max-hermes** — a Python bridge (standalone daemon):
- Receives webhooks from MAX Bot API
- Calls Hermes Agent via CLI
- Sends responses back to MAX
- Supports inline keyboards, typing indicators, file uploads, message edit/delete
- Docker, systemd, CI/CD with auto-deploy

**max-hermes-plugin** — a native Hermes Gateway plugin:
- Registers MAX as a first-class platform in Hermes
- Direct integration without a bridge
- Full access to Hermes features (cron, sessions, send_message)

Both are MIT licensed, Python 3.11+.

GitHub:
- https://github.com/RuslanStrogov/max-hermes
- https://github.com/RuslanStrogov/max-hermes-plugin

Would love feedback, especially from anyone working with MAX Bot API or Hermes Agent.
