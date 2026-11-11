# How to Run This System (Climate Data Repository)

Short instructions for anyone receiving this project who wants to run it
on their own computer.

## 1. What You Need First

**Docker Desktop** - the only application you need to install.
Download it free from: https://www.docker.com/products/docker-desktop/

Install it like any normal program (Next -> Next -> Finish), then **open
Docker Desktop and wait until it shows as "running"** (the whale icon in
your system tray, not spinning/loading) before continuing.

## 2. Start the System

1. **Extract (unzip)** this ZIP file anywhere on your computer (e.g. your Desktop).

2. **Open a Terminal / Command Prompt** inside that folder:
   - Windows: open the folder, type `cmd` in the address bar at the top, press Enter
   - Or: right-click inside the folder -> "Open in Terminal"

3. **Type this one command** (it takes 3-5 minutes the first time, while it
   downloads and builds everything automatically):

   ```
   docker compose up --build
   ```

4. **Wait** until you see this line in the terminal (it means the system is ready):

   ```
   Uvicorn running on http://0.0.0.0:8000
   ```

## 3. Open the System - Two Separate Sign-in Pages

The system has two sign-in pages, one for each kind of user.
Use the page that matches your account. An account cannot sign in on the other page.

### A. Institution users (banks and other reporting institutions)

| | |
|---|---|
| **Sign-in link** | **http://localhost:5173/login** |
| Who uses it | Staff of a reporting institution (Bank A, Bank B, ...) |
| What they do | Download the template, upload data, see validation results and their own submission history |
| Demo accounts | `bankA_user` / `BankA@123` and `bankB_user` / `BankB@123` |

### B. BOT staff and administrators

| | |
|---|---|
| **Sign-in link** | **http://localhost:5173/staff/login** |
| Who uses it | BOT analysts and system administrators |
| What they do | Analysts review and approve submissions and use the dashboard. Administrators manage users, institutions, keys and the audit log |
| Demo accounts | BOT analyst: `bot_analyst` / `Analyst@123`<br>System admin: `admin` / `Admin@123` |

Forgot your password? Use **http://localhost:5173/forgot-password** (both user types).

> **DEVELOPMENT AND TRAINING ONLY.** These demo accounts and passwords exist only in this
> development setup, and they are written here, so anyone who reads this file knows them.
> They are never created in staging or production, and must never be created or reused there
> (production starts with no accounts; the first administrator is made with
> `scripts/create_admin.py`, see `docs/DATABASE_OPERATIONS.md`).

Links for staging and production are on one page: `docs/LOGIN_LINKS.md`.

## 4. Stopping the System

In the same terminal, press `Ctrl + C`. Your data stays safe (nothing is
deleted) as long as you don't use the command `docker compose down -v`.

## 5. Starting It Again Later

After the first run, you don't need `--build` again (unless there is new code to rebuild):

```
docker compose up
```

## 6. If Something Goes Wrong

- **"docker: command not found"** -> Docker Desktop isn't installed or hasn't started yet.
  Open Docker Desktop first and wait until it is ready.
- **Port already in use** -> make sure no other program is using port 5173 or 8000.
- **"Incorrect username or password"** -> you may be on the wrong page. Institution accounts
  sign in at `/login`; BOT analysts and administrators sign in at `/staff/login`.
- For more detailed technical documentation, see `README.md` in this same folder.
