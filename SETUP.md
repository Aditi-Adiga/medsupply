# Local setup and demo

This is a hackathon prototype. Use synthetic data only. It is not production ready. It does not establish medical privacy compliance.

Run commands from `C:\medsupply\MedicalSupplyIntelligence`. Use the same Python environment for the API and dashboard.

```powershell
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` only if `.env` does not exist. Otherwise add its new settings to the existing file. Keep existing database settings. Do not commit `.env`.

For an automatic local configuration, run:

```powershell
$env:NTFY_ENABLED = 'false'
python -m app.configure_local
```

This command creates missing keys in `.env`. It preserves valid existing keys, database settings, and unrelated settings. It disables real ntfy delivery. Repeating it does not change valid keys. Restart any running API or worker to load the setting. If you use this command, skip the manual key generation below.

Generate two independent keys. Paste each output into the matching setting in `.env`.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The first key is `AUTH_SIGNING_KEY`. The second is `TOTP_ENCRYPTION_KEY`. Protect and back up both keys. Changing the signing key ends sessions. Losing the encryption key prevents authenticator verification. `MSI_DEBUG=false` is the optional debug setting.

## Database migration

Stop the API and worker. Back up the SQLite database before the migration.

```powershell
Copy-Item -LiteralPath medical_supply.db -Destination medical_supply.before-operations.db
python -m alembic upgrade head
python -m app.manage seed-demo
```

The migration adds tables. It preserves existing hospitals, medicines, inventory snapshots and consumption records. It works on an empty database too. Repeating the migration has no effect. There is no destructive downgrade. Restore the backup if needed.

`stock_batches` is the current stock source. Historical `inventory` rows and the CSV are history only. The API, dashboard and transfer service all read current stock from `stock_batches`. The CSV remains available to the existing protected demand and anomaly tools. Do not edit the CSV to change current stock.

Demo conversion assumptions:

- Use the latest row for each hospital and medicine. Do not sum historical snapshots.
- Create one batch with ID `DEMO-{hospital}-{medicine}`. The dataset has no real batch identities.
- Treat each quantity as a compatible `unit`. This is a synthetic assumption, not a verified packaging conversion.
- Shift expiry dates by the difference between today and the latest dataset date. This preserves relative shelf life. Already expired relative dates stay expired.
- Use the last 14 demand values as a constant daily demand forecast for 30 days. Keep supplier lead time. Add three days of safety stock.
- Existing locations are district names. Travel takes one simulated day in the same district, or two otherwise. These are not measured routes.
- Repeated seeding skips existing policies and stock. It does not replenish transferred units.

## Accounts and launch

Create individual synthetic accounts. The command prompts for a password. Use at least 12 characters. No default password is provided.

```powershell
python -m app.manage create-account --hospital H01 --username h01-admin
python -m app.manage create-account --hospital H02 --username h02-admin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
python -m streamlit run dashboard/dashboard_app.py
```

`dashboard/dashboard_app.py` is the single active entry point. `dashboard/app.py` forwards to it. Its prior local code is retained below the forwarding block. There is no hospital switch. Set `MSI_API_URL` in the dashboard process environment if the local API uses another address.

In a third terminal, run the persistent alert and delivery worker:

```powershell
python -m app.manage worker
```

The worker also updates alerts when no dashboard is open. Use `--once` for one pass. External delivery stays disabled while `NTFY_ENABLED=false`. Dashboard alerts still work. Run one worker for this SQLite prototype.

## Authenticator and recovery

1. Enter the account username and password.
2. Scan the QR code in an authenticator app. The second code is a time-based one-time password (TOTP).
3. Enter the current code. Private data remains blocked until verification succeeds.
4. Save the eight recovery codes shown after setup. Each code works once. Only hashes are stored.
5. For later sign-in, enter the password and a new authenticator code. A used TOTP cannot be reused. Wait for the next code if needed.
6. If the authenticator is lost, select `Use a recovery code` after password sign-in.
7. In Account settings, reset two-factor access with the password and a fresh TOTP or unused recovery code. Reset ends all sessions and removes the old recovery codes. Sign in and scan the new QR code.

There is no password-only two-factor reset. If both the authenticator and recovery codes are lost, local operator identity verification is needed. This prototype does not automate that process.

After five failed account attempts, sign-in is blocked for 15 minutes. Challenges expire after five minutes. Full sessions expire after `SESSION_MINUTES` (30 by default). Logout revokes the session in the database. Accounts must be active and have the `hospital_admin` role. The original project had no central administrator role. This change does not add network administrator permissions.

## Protected ntfy topics

Use a self-hosted HTTPS ntfy server with access control. Public topic names do not protect messages. Follow the [official ntfy access-control guide](https://docs.ntfy.sh/config/#access-control).

Set this in the ntfy server configuration:

```yaml
auth-file: /var/lib/ntfy/user.db
auth-default-access: deny-all
```

On that server, create ordinary users and explicit topic grants:

```text
ntfy user add msi-publisher
ntfy user add h01-reader
ntfy user add h02-reader
ntfy access msi-publisher msi-h01 write-only
ntfy access msi-publisher msi-h02 write-only
ntfy access h01-reader msi-h01 read-only
ntfy access h02-reader msi-h02 read-only
ntfy token add msi-publisher
```

Repeat the topic and reader configuration for each hospital. Do not make readers ntfy administrators. Verify that H01 credentials cannot read H02, publish to H01, or read an ungranted topic. Unauthenticated reads must fail too. Give each hospital only its own reader credentials. Store the publisher token only in the backend `.env`.

```dotenv
NTFY_ENABLED=true
NTFY_URL=https://ntfy.example.org
NTFY_TOKEN=your-backend-publisher-token
NTFY_TOPICS={"H01":"msi-h01","H02":"msi-h02"}
```

After checking the server access rules, this explicit command sends one real test notification:

```powershell
python -m app.manage manual-notify --hospital H01
```

No real messages are sent by automated tests. Delivery failures remain in the queue for retry. They do not cancel transfers. Delivery uses at-least-once semantics: a crash after ntfy accepts a message but before SQLite commits can cause a duplicate delivery. Stable local event IDs prevent normal refresh duplicates. Exactly-once remote delivery is not promised.

Supply severity maps to ntfy priority: LOW=2, MEDIUM=3, HIGH=4, CRITICAL=5. Notification priority does not decide allocation. The requester supplies Routine or Urgent urgency and a reason. The donor makes the allocation decision. There was no validated allocation engine in the original active dashboard; its transfer counts were simulated. This version does not invent an automatic allocation order.

## H01 and H02 demo

1. Open separate browser sessions for H01 and H02. Sign in and complete both authenticator setups.
2. H01 sees only H01 inventory and alerts. Try H02 inventory through the API with the H01 token. The API returns 403.
3. H01 searches for Paracetamol and a positive quantity. The assistant also accepts `We need 500 units of Paracetamol. Which nearby hospital can supply them?`.
4. If H02 has safe stock, select H02 and submit the request. If not, show `No safe transfer is available`. Do not fabricate a successful demo transfer.
5. H02 sees the incoming request and its alert. H01 cannot approve it.
6. H02 approves a safe quantity. Approved units are reserved. H01 sees the approval.
7. H02 dispatches. Stock leaves H02 and becomes stock in transit.
8. H01 receives. Stock arrives with the same batch ID and expiry date. Repeating receipt is blocked.
9. Refresh the alert list. An unchanged condition does not add a delivery. Acknowledge an alert. The supply problem remains active until its condition clears.

Either participant can cancel Requested or Approved requests. Cancellation releases approved reservations. Dispatched and Received requests cannot be cancelled. Only the donor can approve, reject or dispatch. Only the recipient can receive. All actions are audited.

## Verification and limits

Verified on 9 October 2026: 33 tests passed. This includes API access tests, concurrent stock approval, the full dashboard transfer flow, logout, the legacy dashboard entry point, and a repeatable migration that preserves existing records. Python compilation and `git diff --check` also passed. External ntfy delivery was mocked. No real notification was sent.

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\medsupply\msi-test-temp
```

Use a new dedicated test directory. Pytest owns and clears this directory on a later run. Tests use isolated SQLite databases and mock delivery. The tests cover hospital access, setup, recovery, replay prevention, session expiry, stock reservation races, cancellation, duplicate dispatch and receipt, alert routing, retry and lead-time risk.

This prototype supports SQLite only. Port transaction locking before using another database. The worker claims deliveries with a short database transaction, then sends outside the stock lock. An unfinished claim becomes eligible again after 60 seconds. Use one worker for the demo. Demand and travel estimates are synthetic. The assistant is a controlled local parser, not a general language model. It cannot execute SQL or perform transfer actions. Search is deliberately conservative and can reject transfers that need more detailed demand or routing data. There is no claim of production security or medical privacy compliance.
