[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Backups on Railway

## Enabling Automatic Backups

1.  Open the project in Railway and select the desired database service (usually PostgreSQL).
2.  Go to the **Backups** tab.
3.  Enable **Automatic backups** and set the schedule.
4.  Save changes and ensure new snapshots appear in the backup list.

## Frequency

*   Recommended frequency: **Daily** (e.g., 02:00 UTC).
*   Before releases or data migrations, additionally perform a **manual backup**.

## Recovery Point

*   The recovery point is determined by the **snapshot creation time**.
*   When restoring, choose the closest suitable snapshot by time.

## Restore Procedure

1.  Open the **Backups** tab in the database service.
2.  Select the desired backup by date and time.
3.  Click **Restore** and confirm the operation.
4.  Wait for the restoration to complete and check the application functionality.

> Important: Restoration replaces the current database state with the selected snapshot.

---

# Polski <a name="polski"></a>

# Kopie Zapasowe (Backupy) na Railway

## Włączanie Automatycznych Kopii Zapasowych

1.  Otwórz projekt w Railway i wybierz odpowiednią usługę bazy danych (zazwyczaj PostgreSQL).
2.  Przejdź do zakładki **Backups**.
3.  Włącz **Automatic backups** i ustaw harmonogram.
4.  Zapisz zmiany i upewnij się, że nowe migawki (snapshots) pojawiają się na liście kopii zapasowych.

## Częstotliwość

*   Zalecana częstotliwość: **Codziennie** (np. 02:00 UTC).
*   Przed wydaniami lub migracjami danych wykonaj dodatkowo **manual backup**.

## Punkt Przywracania

*   Punkt przywracania jest określany przez **czas utworzenia migawki**.
*   Podczas przywracania wybierz najbliższy odpowiedni snapshot.

## Procedura Przywracania

1.  Otwórz zakładkę **Backups** w usłudze bazy danych.
2.  Wybierz odpowiedni backup według daty i godziny.
3.  Kliknij **Restore** i potwierdź operację.
4.  Poczekaj na zakończenie przywracania i sprawdź działanie aplikacji.

> Ważne: Przywracanie zastępuje bieżący stan bazy danych wybraną migawką.

---

# Русский <a name="русский"></a>

# Бэкапы на Railway

## Включение автоматических бэкапов

1.  Откройте проект в Railway и выберите нужный сервис базы данных (обычно PostgreSQL).
2.  Перейдите на вкладку **Backups**.
3.  Включите **Automatic backups** и задайте расписание.
4.  Сохраните изменения и убедитесь, что в списке бэкапов появились новые снимки.

## Частота

*   Рекомендуемая частота: **ежедневно** (например, 02:00 UTC).
*   Перед релизами или миграциями данных дополнительно делайте **manual backup**.

## Точка восстановления

*   Точка восстановления определяется **временем создания снимка**.
*   При восстановлении выбирайте ближайший подходящий snapshot по времени.

## Процедура восстановления

1.  Откройте вкладку **Backups** в сервисе базы данных.
2.  Выберите нужный backup по дате и времени.
3.  Нажмите **Restore** и подтвердите операцию.
4.  Дождитесь завершения восстановления и проверьте работу приложения.

> Важно: восстановление заменяет текущее состояние базы данных выбранным снимком.


## Secure retention behavior

- Backups are always created via `pg_dump` and hashed (SHA-256).
- If `FERNET_KEYS` are configured, backup artifacts are encrypted (`.sql.enc`).
- If `BACKUP_REMOTE_STORAGE=true`, local file is deleted after processing (remote uploader hook point).
- If remote storage is not enabled, encrypted backup is retained locally in `DB_BACKUP_DIR` (or `tmp/db_backups`) and pruned by retention.
- Never log `DATABASE_URL` in command output/logs.

Recommended env:

- `BACKUP_REMOTE_STORAGE=true` when S3/R2/B2 uploader is configured.
- `MAX_BACKUP_AGE_HOURS=24` (or your policy).
- `DB_BACKUP_DIR=/data/backups` for persistent Railway Volume when remote upload is not yet enabled.
