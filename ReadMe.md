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

## Architecture

```
User message
    → FastAPI /chat
        → Claude parses intent (post vs comment)
        → Claude generates post/comment text
        → browser-use Agent executes on Facebook
            → Playwright saves session cookies
    → Poll /task/{id} for result
```

## Session Management

- Credentials are encrypted with Fernet (AES-128) and stored in `backend/storage/credentials.enc`
- Playwright session state (cookies) stored in `backend/storage/fb_session.json`
- On each task, session validity is checked — re-login happens automatically if expired
- Encryption key is auto-generated and saved to `.env` on first run
