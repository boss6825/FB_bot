import os
import json
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key

load_dotenv()

STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)
CREDENTIALS_FILE = STORAGE_DIR / "credentials.enc"
ENV_FILE = Path(__file__).parent.parent / ".env"


def get_or_create_encryption_key() -> bytes:
    """Load key from .env, or generate and save one if missing."""
    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key:
        key = Fernet.generate_key().decode()
        # persist it into .env so it survives restarts
        if ENV_FILE.exists():
            set_key(str(ENV_FILE), "ENCRYPTION_KEY", key)
        else:
            with open(ENV_FILE, "w") as f:
                f.write(f"ENCRYPTION_KEY={key}\n")
        os.environ["ENCRYPTION_KEY"] = key
    return key.encode()


def save_credentials(email: str, password: str) -> None:
    """Encrypt and persist FB credentials to disk."""
    key = get_or_create_encryption_key()
    f = Fernet(key)
    payload = json.dumps({"email": email, "password": password}).encode()
    encrypted = f.encrypt(payload)
    CREDENTIALS_FILE.write_bytes(encrypted)


def load_credentials() -> dict | None:
    """Decrypt and return FB credentials, or None if not saved yet."""
    if not CREDENTIALS_FILE.exists():
        return None
    key = get_or_create_encryption_key()
    f = Fernet(key)
    try:
        decrypted = f.decrypt(CREDENTIALS_FILE.read_bytes())
        return json.loads(decrypted)
    except Exception:
        return None


def credentials_exist() -> bool:
    return CREDENTIALS_FILE.exists()