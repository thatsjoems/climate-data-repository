# How to Run This System (Climate Data Repository)

Short instructions for anyone receiving this project who wants to run it
on their own computer.

## What You Need First

**Docker Desktop** - the only application you need to install.
Download it free from: https://www.docker.com/products/docker-desktop/

Install it like any normal program (Next → Next → Finish), then **open
Docker Desktop and wait until it shows as "running"** (the whale icon in
your system tray, not spinning/loading) before continuing.

## Steps to Run

1. **Extract (unzip)** this ZIP file anywhere on your computer (e.g. your
   Desktop).

2. **Open a Terminal / Command Prompt** inside that folder:
   - Windows: open the folder, type `cmd` in the address bar at the top,
     press Enter
   - Or: right-click inside the folder → "Open in Terminal"

3. **Type this one command** (it will take 3-5 minutes the first time,
   downloading and building everything automatically):

   ```
   docker compose up --build
   ```

4. **Wait** until you see this line in the terminal (it means it's ready):
   ```
   Uvicorn running on http://0.0.0.0:8000
   ```

5. **Open your browser** and go to:

   ```
   http://localhost:5173
   ```

That's the whole system running - no further setup is needed.

## Demo Accounts to Try

| Role | Username | Password |
|---|---|---|
| System Admin | `admin` | `Admin@123` |
| BOT Analyst | `bot_analyst` | `Analyst@123` |
| Institution (Bank A) | `bankA_user` | `BankA@123` |
| Institution (Bank B) | `bankB_user` | `BankB@123` |

## Stopping the System

In the same terminal, press `Ctrl + C`. Your data stays safe (nothing is
deleted) as long as you don't use the command `docker compose down -v`.

## Starting It Again Later

After the first run, you don't need `--build` again (unless there's new
code to rebuild):

```
docker compose up
```

## If Something Goes Wrong

- **"docker: command not found"** → Docker Desktop isn't installed or
  hasn't started yet. Open Docker Desktop first and wait until it's ready.
- **Port already in use** → make sure no other program is using port 5173
  or 8000.
- For more detailed technical documentation, see `README.md` in this same
  folder.
