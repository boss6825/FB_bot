# FB Agent

Draft-first Facebook automation with a React UI, FastAPI backend, Claude-generated copy, and browser automation through `browser-use` + Playwright.

## What it does

- Accepts natural-language commands for Facebook posting.
- Supports two flows:
  - Create a post.
  - Comment on a specific Facebook post URL.
- Uses a draft-first workflow:
  - Generate draft text.
  - Let user edit/approve.
  - Publish only after confirmation.
- Persists encrypted credentials and browser session for repeat runs.

## Tech stack

- Frontend: React + Vite
- Backend: FastAPI
- LLM: Anthropic Claude
- Browser automation: `browser-use` + Playwright (Chromium)
- Credential encryption: Fernet (AES-128)

## Requirements

- Python 3.10+
- Node.js 18+
- npm
- Chromium runtime for Playwright (`playwright install chromium`)
- Anthropic API key

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
playwright install chromium
```

Create `backend/.env`:

```env
ANTHROPIC_API_KEY=your_key_here
# Optional:
# ANTHROPIC_MODEL=claude-haiku-4-5-20251001
# BROWSER_HEADLESS=false
# BROWSER_KEEP_OPEN=false
# BROWSER_USER_DATA_DIR=backend/storage/tmp-browser-use-profile
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

## Typical usage

1. Open app and connect Facebook credentials in the modal.
2. Send a command in `Chat`:
   - Free-form command: `Post about AI trends in sales`
   - Comment mode: provide a Facebook URL and comment brief.
3. Review/edit generated draft.
4. Publish draft.
5. Track status/result in Chat, Dashboard, and History.

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/status/setup` | Credential/session status |
| POST | `/auth/credentials` | Save encrypted Facebook credentials |
| POST | `/auth/logout` | Remove credentials, session, and browser profile |
| POST | `/draft` | Create draft only (no publishing) |
| POST | `/draft/{id}/publish` | Publish approved draft |
| POST | `/chat` | Legacy one-shot flow (draft step skipped) |
| GET | `/task/{task_id}` | Poll task state/result |

Task statuses include: `processing`, `draft`, `publishing`, `done`, `error`.

## Configuration

The backend reads environment variables from `backend/.env`.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | - | Claude API key |
| `ANTHROPIC_MODEL` | No | `claude-haiku-4-5-20251001` | Model used for parsing and copy generation |
| `ENCRYPTION_KEY` | No | Auto-generated | Written to `backend/.env` if missing |
| `BROWSER_HEADLESS` | No | `false` | Browser visibility |
| `BROWSER_KEEP_OPEN` | No | `false` | Keep browser session alive after task |
| `BROWSER_USER_DATA_DIR` | No | `backend/storage/tmp-browser-use-profile` | Persistent Playwright profile path |
| `BROWSER_CHANNEL` | No | `chrome` | Browser to launch. `chrome` uses the real installed Chrome (lower automation fingerprint, fewer login captchas). Set to `chromium` to fall back to the Playwright-bundled build if Chrome isn't installed. |
| `BROWSER_USER_AGENT` | No | - | Optional user-agent override. Empty = browser default. |

## Data and security

- Credentials are encrypted and stored at `backend/storage/credentials.enc`.
- Session cookies/state are stored at `backend/storage/fb_session.json`.
- Raw credentials are injected into browser actions via placeholders (`sensitive_data`) so they are not sent as plain text in agent prompts.
- `POST /auth/logout` clears credentials, session state, and browser profile directory.

## Project structure

```text
FB_bot/
  backend/
    main.py
    agent.py
    llm.py
    auth.py
    session.py
    config.py
    requirements.txt
  frontend/
    src/
    package.json
    vite.config.js
  ReadMe.md
```

## Limitations

- Task state is kept in-memory (`tasks` dict), so active task status is lost on backend restart.
- This is currently built for local/single-user usage.
- Facebook UI changes may occasionally break selectors and require updates.

## Troubleshooting

- `Backend is offline`: ensure `uvicorn main:app --reload --port 8000` is running in `backend/`.
- `No Facebook credentials saved`: connect account again from the credentials modal.
- Browser launch or automation issues: run `playwright install chromium` again and retry.
- Stale/invalid login state: use logout in UI (`/auth/logout`) and reconnect credentials.
