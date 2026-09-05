# Sharing the CDR on Your Local Network (LAN)

This lets other devices on the **same WiFi/office network** as your PC open the
CDR in their own browser — for example, a colleague's laptop or your own phone.
It does **not** make the system reachable from the internet at large.

## Step 1: Find your computer's network (IP) address

Open Command Prompt and run:

```
ipconfig
```

Look for "IPv4 Address" under your active network adapter (Wi-Fi or Ethernet),
e.g. `192.168.1.42`. This is YOUR computer's address on the local network.

## Step 2: Start the backend so it accepts connections from other devices

```
cd backend
venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

(`--host 0.0.0.0` means "accept connections from any device on the network",
not just this computer.)

## Step 3: Point the frontend at your computer's address

Edit `frontend/.env` and change:

```
VITE_API_URL=http://localhost:8000/api
```

to (using YOUR actual IP address from Step 1):

```
VITE_API_URL=http://192.168.1.42:8000/api
```

## Step 4: Start the frontend in network mode

```
cd frontend
npm run dev:network
```

The terminal will print two URLs — a "Local" one and a "Network" one, e.g.:

```
Local:   http://localhost:5173/
Network: http://192.168.1.42:5173/
```

## Step 5: Open it from another device

On the other device (must be on the **same WiFi**), open a browser and go to
the "Network" address shown, e.g. `http://192.168.1.42:5173`.

## Windows Firewall

The first time you do this, Windows may show a popup asking to allow Python
and/or Node.js through the firewall — click **Allow access** (for Private
networks at least). If the other device still cannot connect, check Windows
Defender Firewall → Advanced Settings → Inbound Rules, and confirm ports
`8000` and `5173` are allowed for Private networks.

## Limitations

- Your computer must stay switched on and both servers must keep running —
  if you close the terminals or sleep the PC, nobody else can access it.
- This only works for devices on the same network (e.g. the same office WiFi).
  It will not work for someone outside that network or over mobile data.
- For access from anywhere, the system needs to be deployed to a real hosting
  server with a public address — see `docs/DOCKER.md` as a step toward that,
  and note in `docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md` that formal
  production deployment is still outstanding.
