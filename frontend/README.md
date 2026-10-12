# React hospital interface

This is the new hospital interface. FastAPI remains the only backend. Streamlit stays available for comparison.

Requirements: Python with the root requirements installed, and Node.js 22.12 or later. The checked local version is Node.js 22.15.1. Vite's supported versions are described in its [official guide](https://vite.dev/guide/).

## Install and configure

From PowerShell:

```powershell
cd C:\medsupply\MedicalSupplyIntelligence
python -m pip install -r requirements.txt
$env:NTFY_ENABLED = 'false'
python -m app.configure_local
```

The configuration command preserves valid existing keys and database settings. It disables ntfy delivery. The default API allows only `http://localhost:5173` and `http://127.0.0.1:5173`. To change the list, set `FRONTEND_ORIGINS` in the backend `.env` to a JSON array of explicit origins. The browser sends a bearer token in the Authorization header. It does not use authentication cookies. Tokens stay in memory and are removed at logout or session expiry. Reloading the page requires sign-in again.

The frontend example contains only `VITE_API_URL`. It must not contain credentials. The default API URL is `http://127.0.0.1:8000/api/v1`, so no frontend `.env` is required for the normal demo. A custom API address can be put in `frontend/.env.local`:

```dotenv
VITE_API_URL=http://127.0.0.1:8000/api/v1
```

If the database has not been updated, stop running services and run:

```powershell
cd C:\medsupply\MedicalSupplyIntelligence
$backup = "medical_supply.before-demo-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item -LiteralPath medical_supply.db -Destination $backup
python -m alembic upgrade head
python -m app.manage seed-demo
python -m app.manage create-account --hospital H01 --username h01-admin
python -m app.manage create-account --hospital H02 --username h02-admin
```

The account commands prompt for a password with at least 12 characters. Skip account creation if those usernames already exist. Demo seeding preserves existing stock. No additional migration is needed for the React endpoints.

Install frontend dependencies:

```powershell
cd C:\medsupply\MedicalSupplyIntelligence\frontend
npx --offline=false --yes npm@11 ci --offline=false
```

This uses the committed lockfile. npm 11 is invoked locally because the installed npm 10 crashed while resolving optional test-library peer dependencies. No global npm installation is required.

## Start

Backend terminal:

```powershell
cd C:\medsupply\MedicalSupplyIntelligence
$env:NTFY_ENABLED = 'false'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend terminal:

```powershell
cd C:\medsupply\MedicalSupplyIntelligence\frontend
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development server is a frontend tool, not another business backend.

Alert worker terminal:

```powershell
cd C:\medsupply\MedicalSupplyIntelligence
$env:NTFY_ENABLED = 'false'
python -m app.manage worker
```

Run the worker to update saved stock and expiry alerts. Browser refresh is read-only and cannot queue or send notifications. Supply actions save their own event alerts immediately. The backend worker owns external delivery. Keep ntfy disabled until the protected server topics are checked manually.

Optional Streamlit comparison:

```powershell
cd C:\medsupply\MedicalSupplyIntelligence
python -m streamlit run dashboard/dashboard_app.py
```

## H01 and H02 walkthrough

1. Open two separate browser sessions. Sign in as H01 and H02.
2. For a new account, scan the QR code with an authenticator app. Enter its six-digit TOTP code. TOTP means time-based one-time password. Save the recovery codes shown once.
3. H01 opens Inventory and inspects a medicine. History and prediction appear in separate charts. Chart values are also available as a table for keyboard and screen-reader use.
4. H01 opens Find supply. Select a medicine and quantity, or ask the supply assistant. It uses controlled local search. No general language model is connected.
5. If H02 has safe stock, H01 selects it, enters a reason, and submits a request. If there is no safe donor, the screen states this. The existing dataset does not guarantee a donor for every quantity.
6. H02 reviews the incoming request. Choose an approved quantity and confirm. The backend rechecks stock and reserves units in one transaction.
7. H02 records dispatch. H01 records receipt. Both can read their participating request's audit history and allocated batches.
8. Review Alerts. Acknowledge an alert to mark it as seen. The stock condition can still be active.
9. In Account settings, a password and fresh TOTP or unused recovery code can reset the authenticator. All sessions end. The next sign-in requires setup again.

## Tests

```powershell
cd C:\medsupply\MedicalSupplyIntelligence
python -m pytest -q -p no:cacheprovider --basetemp=C:\medsupply\react-backend-test-temp
cd frontend
npm run typecheck
npm test
npm run build
npx --offline=false playwright install chromium
npm run test:e2e
```

Pytest owns the dedicated temporary directory. The browser test starts its own API on port 8001 and frontend on 5173. Stop other processes on those ports before that test. It uses a separate database under `.verification`, a generated test password, and synthetic stock derived from the CSV with documented test-only adjustments. It never opens the original database. ntfy is disabled, and no LLM is called. Browser screenshots contain authenticated synthetic data, but no passwords, QR secrets or recovery codes. They are saved under `.verification/screenshots` and ignored by Git.

See [FRONTEND_MIGRATION.md](../FRONTEND_MIGRATION.md) for the parity checklist, verification results and remaining limits. See [SETUP.md](../SETUP.md) for batch conversion assumptions and the protected ntfy setup.
