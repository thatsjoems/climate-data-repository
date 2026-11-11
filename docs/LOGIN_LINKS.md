# Login Links (all environments)

One page listing where to sign in, for every environment and role.
No passwords are stored here. Never write real passwords into project files.

## Which page for which user

| User | Page | Notes |
|---|---|---|
| Institution user (bank, TMA, PMO) | `/login` | Single-step sign-in |
| BOT analyst / System administrator | `/staff/login` | Production also asks for the two-step code |
| Forgot password | `/forgot-password` | Available to everyone |
| After sign-in | `/` (portal), `/admin` (administrators only), `/change-password` | |

An institution account cannot sign in at `/staff/login`, and a staff account cannot sign in at `/login`.

## 1. Development / demo (`docker compose up -d`)

- Institution: http://localhost:5173/login
- BOT staff and administrator: http://localhost:5173/staff/login
- Forgot password: http://localhost:5173/forgot-password
- API documentation (development only): http://localhost:8000/docs
- Demo accounts: printed in the `backend` container log on first start (see `README.md`, `HOW_TO_RUN.md`). For development and training only.

## 2. Staging (`scripts\staging_up.ps1`, this computer only)

- Institution: https://localhost:8443/login
- BOT staff and administrator: https://localhost:8443/staff/login
- Forgot password: https://localhost:8443/forgot-password
- If the browser refuses `localhost`, use `https://127.0.0.1:8443/...` (type `https://` yourself).
- Details: `docs/STAGING.md`

## 3. Production (`scripts\prod_up.ps1`)

The address comes from `CDR_DOMAIN` in `.env.production` (example file: `.env.production.example`).
If ports 80/443 were busy and `HTTPS_PORT` was changed, add that port (for example `:8443`).

- Institution: https://<CDR_DOMAIN>/login
- BOT staff and administrator: https://<CDR_DOMAIN>/staff/login
- Forgot password: https://<CDR_DOMAIN>/forgot-password

To read your address without showing secrets:

```powershell
Select-String -Path .env.production -Pattern "^(CDR_DOMAIN|HTTPS_PORT)="
```

Production has no demo accounts and no `/docs` page. Accounts are created by the administrators.
Details: `docs/PRODUCTION_DEPLOYMENT.md`

## 4. Record the real production address here (fill in at go-live)

- Production address: ______________________________
- Date went live: ______________________________
