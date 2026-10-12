# Interface migration checklist

Inspection found one active secured Streamlit view: `dashboard/dashboard_app.py`. `dashboard/app.py` forwards to it. FastAPI uses the same SQLite database and shared services for authentication, stock, transfers and alerts.

| Actual feature before migration | Evidence | React requirement or gap |
|---|---|---|
| Password and TOTP sign-in | `auth.login`, `setup`, `verify` | Password, setup QR, verification and recovery screens |
| Hospital permission enforcement | `current_user`, `allowed`, request participant checks | Preserve every backend check; no hospital switch |
| Recovery and reset | Hashed one-use codes, reset with password and second factor | Show codes once; account reset; no recovery after all codes are lost |
| Session expiry and logout | Revocable JWT sessions stored in SQLite | Memory-only browser token; clear workspace on expiry |
| Inventory and export | Hospital-filtered API and batch source | Search, sort, unit-aware tables and export |
| Risk and expiry | `alerts.assess` | Read backend results; no risk formula in React |
| Demand history | CSV loader available, not shown in the secured Streamlit view | Add hospital-only medicine detail endpoint; preserve dates |
| Forecast | Stock policy uses a recent average for 30 days | Show that same forecast; label synthetic assumptions; no validated uncertainty interval |
| Supply assistant | Controlled local parser; no LLM | Accurate supply assistant label; no fabricated donors |
| Requests and transfers | Six states, transactional reservations, batch receipt and audit | Incoming/outgoing views; add permitted audit history endpoint |
| Alerts | Persistent states and hospital queue; GET originally evaluated alert conditions | Make browser refresh read-only; worker updates conditions independently |
| ntfy | Optional backend delivery and retry queue | Browser cannot publish; enabled status only; real delivery disabled |
| Central administrator | None | Do not invent network permissions |
| Password change and notification preferences | No supported endpoint | Show the limitation; do not add nonfunctional controls |

React uses Radix Themes for consistent controls and Recharts for demand charts. Official documentation was checked: [Vite](https://vite.dev/guide/), [Radix Themes](https://www.radix-ui.com/themes/docs/overview/getting-started), [Recharts](https://recharts.github.io/en-US/examples/).

Streamlit remains available throughout this migration. Existing local work and the original database remain intact.

## Feature parity

| Required function | React implementation | Verification |
|---|---|---|
| Password, TOTP, first-time setup and one-time recovery display | Sign-in screens with backend-generated QR | React tests and real browser setup for H01 and H02 |
| Recovery sign-in and secure authenticator reset | Recovery checkbox and Account settings reset | React recovery test; backend reset and recovery tests |
| Logout and session expiry | Database revocation; memory-only token; idle expiry timer using backend expiry time | Backend tests, React tests and browser logout |
| Hospital-only inventory and export | Inventory filters, sort and authenticated export | Backend cross-hospital tests and browser 403 checks |
| Medicine detail, batches, history and forecast | Separate historical and predicted charts; accessible value tables | Hospital-scoped API tests and desktop/mobile browser inspection |
| Shortage, lead time and expiry risk | Shared Python results with exact depletion day | Backend risk, zero stock, expiry and lead-time tests |
| Form and local supply assistant | Controlled supply endpoint; donor details only | React tests and browser search |
| Submit supply request | Explicit source selection, quantity, urgency and reason | React submission test and real browser request |
| Review incoming/outgoing requests and status history | Participant-only detail and audit history | Backend participant and audit tests |
| Approve, reject, cancel, dispatch and receive | Permission-based controls; backend state and stock checks | React action checks; backend state, concurrency and duplicate-action tests; browser approval, dispatch and receipt |
| Reservation and preserved batches | Existing SQLite transaction rules retained | Backend concurrency test; browser verifies 100 reserved units, then 900 donor units with zero reservation after dispatch |
| Hospital alerts and acknowledgement | State filter, detail links and acknowledgement | Backend routing and deduplication tests; React acknowledgement test |
| No notifications on refresh | GET endpoints read-only; worker updates conditions | Dedicated backend test; no frontend ntfy publisher |
| Account and notification status | Assigned hospital, role, verified factor status, external delivery flag | Backend account response and React account screen |
| Connection, loading, empty and conflict states | One API client and explicit status messages | React tests for each supported error class and empty/loading states |
| Narrow screens and keyboard access | Wrapped navigation, scrollable tables, labelled controls, chart value tables and focus outlines | Chromium at 1440 × 1000 and 390 × 844; no page-wide horizontal overflow; keyboard navigation verified |

Streamlit is retained. Its supported authentication, export, supply, transfer, alert and reset functions are available in React. The React detail screen adds demand history and status history that the secured Streamlit view did not display.

## Remaining limits

- No general language model is connected. The supply assistant is a local controlled parser.
- The forecast uses the same synthetic recent-average policy as stock risk and safe transfers. No validated confidence interval is available. The older protected ML endpoints remain available, but their separate predictions are not presented as the stock-safety forecast.
- Supply units and batch identity are demo assumptions documented in SETUP.md. Travel times are simulated. Safe source availability depends on actual seeded stock.
- Password changes and personal notification preferences have no backend endpoint. The account screen states this instead of showing nonfunctional controls.
- Loss of both the authenticator and all recovery codes needs operator identity verification. There is no automated recovery flow for that case.
- There is no central administrator role or network-wide hospital view.
- SQLite remains the supported database. Remote ntfy delivery has at-least-once semantics and can repeat after a crash. Normal refresh and event duplicates are prevented.
- Real ntfy topics and access rules have not been tested externally. Delivery remained disabled and mocked during verification.
- Screens were inspected in Chromium. Other browsers, assistive technology and production hosting were not tested. This is a prototype, not a production security or privacy certification.

## Local launch

Verification on 9 October 2026: 38 backend and retained Streamlit tests passed. All 13 React tests passed. TypeScript checks and the Vite production build passed. The Chromium integration test passed the real H01/H02 flow, backend stock checks, hospital access denials, logout, desktop/mobile layout and keyboard navigation. External notifications were mocked or disabled. No LLM service was connected or called.

Exact PowerShell install, database, account and launch commands are in [frontend/README.md](frontend/README.md). Backend origin configuration is in the root `.env.example`. The frontend example contains only its API address.

No schema change is required for this interface migration. No original database migration or stock reset was performed during verification. Tests and browser inspection used separate synthetic databases under `.verification` or pytest temporary directories. No push, deployment, real notification or Streamlit deletion was performed.
