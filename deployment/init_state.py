"""Run once with the intended service ownership; never print the encryption key."""
import os
from pathlib import Path
import sys
from cryptography.fernet import Fernet

if len(sys.argv) != 2:
    raise SystemExit("Usage: python init_state.py <absolute service-state directory>")
root = Path(sys.argv[1])
if not root.is_absolute():
    raise SystemExit("Absolute state directory required")
root.mkdir(parents=True, exist_ok=True)
if os.name != "nt":
    root.chmod(0o700)
path = root / "service.env"
content = ("TC_MCP_ENCRYPTION_KEY=" + Fernet.generate_key().decode() + "\n"
           "TC_MCP_DB=" + str(root / "keys.sqlite3") + "\n"
           "TC_PUBLIC_ORIGIN=https://lhtc2026.com\n"
           "TC_UPSTREAM_ORIGIN=https://lhtc2026.com\n"
           "TC_MCP_RPM=60\nTC_MCP_TTL=604800\n")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(content)
print("Created private service configuration. Existing configuration is never overwritten.")
