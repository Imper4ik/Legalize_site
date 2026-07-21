# Field-level encryption and key rotation

High-sensitivity text and JSON fields are encrypted at rest with Fernet. In `FERNET_KEYS`, the first comma-separated key encrypts new values and every listed key may decrypt existing values. A deterministic key derived from `SECRET_KEY` is for local development only.

Generate a key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Searchable client identity fields (blind indexes)

`Client.first_name`, `last_name`, `email` and `phone` are encrypted at rest.
Because Fernet ciphertext is non-deterministic, they cannot be matched, sorted,
or substring-searched in SQL. Search is preserved with keyed **blind indexes**
(HMAC-SHA256 over `SECRET_KEY`, mirroring the case-number hash):

- `email_hash` / `phone_hash` columns hold the HMAC of the normalized value for
  exact-match lookups (email is case/space-insensitive; phone is digits-only).
- `ClientSearchToken` stores HMACs of every lowercase name prefix (length ≥ 3,
  plus whole short words), so staff can search names by a word or its beginning
  without decrypting. `Client.build_search_filter(query)` combines all of these.

Hashes and tokens are rebuilt automatically in `Client.save()`; the migration
`0127_encrypt_client_identity_pii` backfills existing rows. Rotating `SECRET_KEY`
invalidates the blind indexes — rebuild them by re-saving clients (or re-running
the backfill logic) after such a rotation. The Fernet key ring is independent of
`SECRET_KEY`, so a Fernet rotation does not affect the blind indexes.

## Safe rotation procedure

1. Back up the database and retain every historical Fernet key separately.
2. Configure `FERNET_KEYS` as `new_key,all_previous_keys` on every web, worker, cron, and administrative process.
3. Run a read-only validation with the complete key ring:

   ```bash
   python manage.py validate_encrypted_data
   ```

4. Drain or stop every process that can write the database. Keep all writers stopped through step 6.
5. Rotate all project-local encrypted text and JSON columns:

   ```bash
   python manage.py rotate_fernet_fields --maintenance-confirmed
   ```

   The command performs guarded raw database updates, bypasses model hooks and signals, and rolls back the entire transaction on unreadable data, malformed encrypted JSON, or a concurrent field update.

6. Prove that every encrypted token uses the primary key:

   ```bash
   python manage.py validate_encrypted_data --primary-key-only
   ```

7. Restart services with the complete key ring. Remove old keys only after the backup is verified and both validations succeed. Then restart every process again and repeat the primary-key-only validation.

## Dry run and model filters

A dry run validates and reports rows without changing data or taking row locks:

```bash
python manage.py rotate_fernet_fields --dry-run
```

Limit validation or rotation to one or more concrete models when investigating an incident:

```bash
python manage.py validate_encrypted_data --model clients.Client
python manage.py rotate_fernet_fields --dry-run --model clients.Client
```

## Failure handling

If a value is unreadable, restore the missing historical key before any write. Never replace unreadable data with an empty value or the visible unavailable placeholder. Fernet ciphertext cannot be recovered if its only matching key is lost.

Never log decrypted personal data or ciphertext. Operational logs may contain only the model label, row ID, field name, and a generic failure reason.
