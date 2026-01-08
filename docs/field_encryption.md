# Field-level encryption and key rotation

This project uses `django-fernet-fields` to encrypt PII at rest for the `Client`
model (passport and case numbers).

## Configuration

Set the Fernet keys via the `FERNET_KEYS` environment variable. Provide a
comma-separated list where the first key is used for new encryption and the
remaining keys are used for decryption during key rotation.

Generate a key:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

Example:

```bash
export FERNET_KEYS="newest_key,previous_key"
```

If `FERNET_KEYS` is not provided, a deterministic key derived from `SECRET_KEY`
is used for local development only.

## Key rotation procedure

1. **Generate a new key** (see command above).
2. **Update `FERNET_KEYS`** so the new key is first, followed by previous keys.
3. **Deploy** the configuration change.
4. **Re-encrypt existing rows** by running a management task or a one-off
   script that loads and saves all clients, ensuring values are written with
   the newest key.
5. **Remove the old key** from `FERNET_KEYS` after re-encryption completes and
   all services use the new key.

## Logging policy

* Avoid logging PII fields (`passport_num`, `case_number`) directly.
* The application adds a log filter that redacts known PII field names in log
  messages to reduce accidental leakage.
