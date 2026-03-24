"""
App config and encrypted credential storage.
Credentials are encrypted at rest; we use a machine-bound key so they are not stored in plaintext.
"""
import os
import json
import hashlib
import base64
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Default config directory (next to exe or in user app data)
def _config_dir() -> Path:
    if getattr(os.sys, "frozen", False):
        base = Path(os.sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "config"

CONFIG_DIR = _config_dir()
CREDENTIALS_FILE = CONFIG_DIR / "credentials.dat"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
LAYOUTS_DIR = CONFIG_DIR / "layouts"
SCHEMAS_DIR = CONFIG_DIR / "schemas"
SCHEMAS_INVOICES_DIR = SCHEMAS_DIR / "invoices"
SCHEMAS_BILLABLES_DIR = SCHEMAS_DIR / "billables"
SCHEMAS_TICKETS_DIR = SCHEMAS_DIR / "tickets"

# Salt for key derivation (static per app; real secrecy is encryption + not storing plaintext)
_SALT = b"CommandAlkonInvoiceExport_v1"

def _derived_key() -> bytes:
    """Derive encryption key from machine/user identity so we don't store the key in plaintext."""
    # Use a combination of env and path so it's stable per machine/user
    seed = (os.environ.get("USERNAME", "") + os.environ.get("COMPUTERNAME", "") + str(Path.home())).encode()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT, iterations=480000)
    key = base64.urlsafe_b64encode(kdf.derive(seed))
    return key

def _fernet():
    return Fernet(_derived_key())

def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMAS_INVOICES_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMAS_BILLABLES_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMAS_TICKETS_DIR.mkdir(parents=True, exist_ok=True)


def get_schemas_dir(kind: str | None = None) -> Path:
    """Return the schema cache directory for a data kind.

    kind: 'invoices' | 'billables' | 'tickets' (case-insensitive). Defaults to invoices.
    """
    ensure_dirs()
    k = (kind or "invoices").strip().lower()
    if k in ("billable", "billables"):
        return SCHEMAS_BILLABLES_DIR
    if k in ("ticket", "tickets"):
        return SCHEMAS_TICKETS_DIR
    return SCHEMAS_INVOICES_DIR

def save_credentials(data: dict) -> None:
    """Save credentials encrypted. data: entityRef, apiKey, clientId, clientSecret, apiScopeRef."""
    ensure_dirs()
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    encrypted = _fernet().encrypt(raw)
    CREDENTIALS_FILE.write_bytes(encrypted)

def load_credentials() -> dict | None:
    """Load and decrypt credentials. Returns None if missing or invalid."""
    ensure_dirs()
    if not CREDENTIALS_FILE.exists():
        return None
    try:
        encrypted = CREDENTIALS_FILE.read_bytes()
        raw = _fernet().decrypt(encrypted).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None

def credentials_hash_for_display() -> str:
    """Return a short hash of stored credentials for UI (e.g. 'Saved (••••abc1)')."""
    if not CREDENTIALS_FILE.exists():
        return ""
    try:
        raw = CREDENTIALS_FILE.read_bytes()
        h = hashlib.sha256(raw).hexdigest()[:8]
        return h
    except Exception:
        return ""

def save_settings(settings: dict) -> None:
    ensure_dirs()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

def load_settings() -> dict:
    ensure_dirs()
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
