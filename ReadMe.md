# FB Agent — Backend

AI-powered Facebook automation agent. Natural language in → posts/comments out.

## Run Frontend + Backend Separately (Windows Git Bash)

Open two Git Bash terminals.

### Terminal 1: Backend

```bash
cd backend

# Activate venv (Windows Git Bash)
source venv/Scripts/activate

# If venv does not exist yet:
# python -m venv venv
# source venv/Scripts/activate

uvicorn main:app --reload --port 8000
```

### Terminal 2: Frontend

```bash
cd frontend

# If dependencies are not installed yet:
# npm install

npm run dev
```

## Setup

```bash
cd backend

# 1. Create virtualenv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies (unified entry point at repo root)
pip install -r ../requirements.txt

# 3. Install Playwright browser
playwright install chromium

# 4. Set up .env
cp ../.env.example ../.env
# Add your ANTHROPIC_API_KEY to .env

# 5. Run the server
uvicorn main:app --reload --port 8000
```

## API Endpoints


| Method | Endpoint            | Description                              |
| ------ | ------------------- | ---------------------------------------- |
| GET    | `/health`           | Server health check                      |
| GET    | `/status/setup`     | Check if credentials + session are saved |
| POST   | `/auth/credentials` | Save FB credentials (run once)           |
| POST   | `/auth/logout`      | Clear saved session                      |
| POST   | `/chat`             | Send a natural language command          |
| POST   | `/draft`            | Create post/comment draft (review first) |
| POST   | `/draft/{id}/publish` | Publish reviewed/edited draft          |
| GET    | `/task/{task_id}`   | Poll task status + result                |


## Example Flow

```bash
# 1. Save credentials once
curl -X POST http://localhost:8000/auth/credentials \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'

# 2. Send a command
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "post about how AI is changing sales", "task_id": "abc123"}'

# 3. Poll for result
curl http://localhost:8000/task/abc123
```

## Draft-First Comment by Link (Recommended)

```bash
# 1. Create a draft comment for a specific Facebook post URL
curl -X POST http://localhost:8000/draft \
  -H "Content-Type: application/json" \
  -d '{"task_id":"draft-1","action":"comment","target_url":"https://www.facebook.com/zuck/posts/10102577175875681","content_brief":"thank them for sharing"}'

# 2. Poll until status=draft and copy generated_content
curl http://localhost:8000/task/draft-1

# 3. Publish reviewed/edited text
curl -X POST http://localhost:8000/draft/draft-1/publish \
  -H "Content-Type: application/json" \
  -d '{"text":"Great insight, thanks for sharing this."}'
```

## Architecture

The default flow is **draft-first**: Claude writes the text, the user reviews/edits it in the
chat UI, and only then does the browser agent run. The legacy one-shot `/chat` route is still
available but not used by the React frontend.

```
One-time setup
    User → CredentialModal → POST /auth/credentials
        → Fernet (AES-128) → backend/storage/credentials.enc

Per-command flow (draft-first)
    React ChatView
        → POST /draft  { task_id, message | action+target_url+content_brief }
            → parse_intent          (Claude → action / url / brief)
            → generate_post_text or generate_comment_text  (Claude)
        → status: "draft"  with generated_content
    Frontend polls GET /task/{id} → renders Draft card
    User edits + approves
        → POST /draft/{id}/publish  { text }
            → build_agent_task(action, text, url)
            → run_fb_task()  — browser-use Agent + Playwright
                · loads fb_session.json (re-uses cookies)
                · if expired: re-logs in with decrypted creds
                  via sensitive_data placeholders (LLM never
                  sees raw email/password)
                · posts / comments on Facebook
                · deterministic JS fallback click for Post /
                  Comment if agent stops before "done"
                · saves updated storage_state back to disk
        → status: "done" | "error"
    Frontend polls GET /task/{id} → renders result in chat
```

Frontend pages: **Chat** (drafts + publish), **Dashboard** (per-task stats from
`localStorage`), **History** (past tasks). Backend health + setup status are polled
every 30s so the credential modal can prompt for re-login when needed.

## Session Management

- Credentials are encrypted with Fernet (AES-128) and stored in `backend/storage/credentials.enc`
- Playwright session state (cookies) stored in `backend/storage/fb_session.json`
- On each task, session validity is checked — re-login happens automatically if expired
- Encryption key is auto-generated and saved to `.env` on first run
