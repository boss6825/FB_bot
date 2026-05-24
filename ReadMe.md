# FB Agent

Draft-first Facebook automation with a React UI, FastAPI backend, Claude-generated copy, and browser automation through `browser-use` + Playwright. Login uses a **human-in-the-loop** flow — the backend opens a real Chrome window, the user logs in themselves, and the persistent browser profile is reused for all future automation.

## What it does

- Accepts natural-language commands for Facebook posting.
- Supports two flows:
  - Create a post.
  - Comment on a specific Facebook post URL.
- Draft-first workflow: generate text → user reviews/edits → publish on confirmation.
- Reuses a persistent local Chrome profile across runs, so the user only logs in once.
- Surfaces checkpoints/CAPTCHA to the UI mid-automation so the user can solve them in the live browser window.

## Tech stack

- Frontend: React + Vite
- Backend: FastAPI
- LLM: Anthropic Claude (`claude-haiku-4-5` by default)
- Browser automation: `browser-use` + Playwright (Chromium / Chrome)
- Task state: SQLite

> The project no longer stores Facebook credentials. There is no encryption layer for FB passwords because the bot never sees them — the user logs in directly in the browser window opened by Playwright. `backend/auth.py` is legacy and unused by the live API.

## Requirements

- Python 3.10+
- Node.js 18+
- npm
- Anthropic API key
- A local installation of Google Chrome (recommended — lower automation fingerprint). Falls back to the Playwright-bundled Chromium if `BROWSER_CHANNEL=chromium`.

## Quick start

Run backend and frontend in separate terminals.

### 1) Backend

```bash
cd backend
python -m venv venv

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# macOS/Linux
# source venv/bin/activate

pip install -r requirements.txt
playwright install chromium   # only needed if you set BROWSER_CHANNEL=chromium
```

Create `backend/.env`:

```env
ANTHROPIC_API_KEY=your_key_here
# Optional:
# ANTHROPIC_MODEL=claude-haiku-4-5-20251001
# BROWSER_HEADLESS=false
# BROWSER_KEEP_OPEN=false
# BROWSER_USER_DATA_DIR=backend/storage/persistent-profile
# BROWSER_CHANNEL=chrome
# BROWSER_USER_AGENT=
```

Start API server:

```bash
uvicorn main:app --reload --port 8000
```

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Login flow (human-in-the-loop)

Login is interactive — the backend never handles a password.

1. User clicks **Connect Facebook** in the UI → frontend calls `POST /auth/login/start`.
2. Backend launches a real Chrome window via Playwright using the persistent profile at `backend/storage/persistent-profile/` and navigates to facebook.com.
3. User logs in manually in that window (handles 2FA, checkpoints, CAPTCHA — anything Facebook throws at them).
4. User clicks **I've logged in** in the UI → frontend calls `POST /auth/login/verify/{session_id}`.
5. Backend checks the Facebook cookies for `c_user` (the logged-in user ID cookie). If present, it exports Playwright storage state to `backend/storage/fb_session.json` and closes the login window.
6. Future automation runs reuse the persistent profile + storage state, so the user stays logged in until cookies expire.

If cookies expire later, the agent returns `"Login expired"` and the UI prompts the user to reconnect.

## Automation flow

1. User sends a natural-language message (e.g. `Post about AI trends in sales`, or `Comment on <fb-url> saying ...`).
2. Backend parses intent with Claude → `parse_intent` returns `{action, content_brief, target_url}`.
3. Backend generates draft text with `generate_post_text` / `generate_comment_text`.
4. Draft is returned to the UI; status moves to `draft`.
5. User reviews/edits text and clicks publish → `POST /draft/{id}/publish`.
6. Backend builds an agent task string with explicit efficiency rules (single-batch composer flow, deterministic `done` condition, no emoji rewriting, etc.) and runs a `browser-use` `Agent` against the persistent Chrome profile.
7. After the LLM agent submits, a deterministic fallback re-clicks the **Post** / **Comment** button via raw CDP if it's still visible (works around stale element indices when Facebook's React tree mutates between agent steps).
8. Final storage state is exported back to `fb_session.json` so the next run starts already-logged-in.

The `browser-use` Agent runs on a dedicated background event loop (`_browser_loop_thread`) so Playwright's Windows ProactorEventLoop doesn't clash with FastAPI's main loop.

## CAPTCHA / checkpoint during automation

If the agent encounters a sign-in prompt, checkpoint, or CAPTCHA mid-run, it stops and reports `"Login expired"` — the UI then prompts the user to reconnect Facebook through the login flow above. The backend exposes `POST /task/{task_id}/captcha-solved` for manual resumption hooks, but the current agent prompt is configured to bail out and require a fresh manual login rather than wait inline.

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/status/setup` | Whether a saved session exists |
| POST | `/auth/login/start` | Open a local Chrome window for manual FB login |
| POST | `/auth/login/verify/{session_id}` | Confirm login, persist cookies/storage state |
| POST | `/auth/login/cancel/{session_id}` | Cancel the login window |
| POST | `/auth/logout` | Clear saved session + persistent profile |
| POST | `/draft` | Generate post/comment text only |
| POST | `/draft/{id}/publish` | Publish approved draft via browser automation |
| POST | `/chat` | Legacy one-shot flow (no draft step) |
| GET | `/task/{task_id}` | Poll task state/result |
| POST | `/task/{task_id}/captcha-solved` | Resume an automation task waiting on a CAPTCHA |

Task statuses: `processing`, `draft`, `publishing`, `done`, `error`, `captcha_required`.

## Configuration

The backend reads environment variables from `backend/.env`.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | - | Claude API key |
| `ANTHROPIC_MODEL` | No | `claude-haiku-4-5-20251001` | Used for intent parsing, copy generation, and the browser-use agent |
| `BROWSER_HEADLESS` | No | `false` | Headless mode for the automation runs. Login window is always visible. |
| `BROWSER_KEEP_OPEN` | No | `false` | Keep the automation browser alive between tasks |
| `BROWSER_USER_DATA_DIR` | No | `backend/storage/persistent-profile` | Persistent Chrome profile (cookies survive here) |
| `BROWSER_CHANNEL` | No | `chrome` | `chrome` uses installed Chrome (preferred); `chromium` uses Playwright's bundled build |
| `BROWSER_USER_AGENT` | No | - | Optional UA override |

## Data and storage

- `backend/storage/persistent-profile/` — full Chrome user data dir. Cookies, localStorage, and IndexedDB live here; this is the primary source of truth for the logged-in session.
- `backend/storage/fb_session.json` — Playwright storage state snapshot used by `browser-use` and as a signal that a session exists.
- `backend/storage/tasks.db` — SQLite task store for polling.
- `POST /auth/logout` wipes both `fb_session.json` and the persistent profile directory.

## Project structure

```text
FB_bot/
  backend/
    main.py            # FastAPI routes + background runners
    agent.py           # browser-use Agent + deterministic Post/Comment click fallbacks
    llm.py             # Anthropic intent parsing + text generation
    session.py         # Storage state + persistent profile management
    config.py          # Env var config
    store.py           # SQLite task store
    requirements.txt
  frontend/
    src/
    package.json
    vite.config.js
  README.md
```

## Limitations

- Local/single-user only — the persistent Chrome profile is shared, so this is not multi-tenant.
- Facebook UI changes can break the agent's selectors. The deterministic Post/Comment fallback in `agent.py` is the main defense; if FB renames the aria-labels, that JS will need updating.

## Troubleshooting

- **`Backend is offline`** — make sure `uvicorn main:app --reload --port 8000` is running in `backend/`.
- **`Login expired`** — cookies aged out or Facebook invalidated the session. Reconnect via Settings.
- **Login window doesn't open** — make sure Chrome is installed, or set `BROWSER_CHANNEL=chromium` and run `playwright install chromium`.
- **Post button never clicks** — check backend logs for the `Post-click fallback attempt` lines; if all three attempts fail, Facebook likely changed its composer DOM and the locator script in `agent.py` needs updating.
- **Stuck in `processing`** — inspect logs; the agent loop runs on a separate thread so tracebacks land in stdout, not the FastAPI request log.
