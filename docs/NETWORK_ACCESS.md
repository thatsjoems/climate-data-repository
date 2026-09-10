# Sharing the CDR on Your Local Network (LAN)

This lets other devices on the **same WiFi/office network** as your PC open the
CDR in their own browser — for example, a colleague's laptop or your own phone.
It does **not** make the system reachable from the internet at large.

## It usually already works

Docker's port mapping (`"5173:80"` for the frontend, `"8000:8000"` for the backend, in
`docker-compose.yml`) listens on **all** of your computer's network interfaces by default,
not just `localhost`. So once `docker compose up` is running, another device on the same
network can typically reach it immediately — no extra configuration needed.

## Step 1: Find your computer's network (IP) address

Open Command Prompt and run:

```
ipconfig
```

Look for "IPv4 Address" under your active network adapter (Wi-Fi or Ethernet),
e.g. `192.168.1.42`. This is YOUR computer's address on the local network.

## Step 2: Open it from another device

On the other device (must be on the **same WiFi**), open a browser and go to:

```
http://192.168.1.42:5173
```

(using YOUR actual IP address from Step 1).

## If it doesn't connect: Windows Firewall

The first time you do this, Windows may show a popup asking to allow Docker Desktop
through the firewall — click **Allow access** (for Private networks at least). If the
other device still cannot connect, check Windows Defender Firewall → Advanced Settings →
Inbound Rules, and confirm ports `8000` and `5173` are allowed for Private networks.

## Limitations

- Your computer must stay switched on and `docker compose up` must keep running —
  if you stop the containers or sleep the PC, nobody else can access it.
- This only works for devices on the same network (e.g. the same office WiFi).
  It will not work for someone outside that network or over mobile data.
- For access from anywhere, the system needs to be deployed to a real hosting
  server with a public address — this is a step beyond `docker compose up` on a laptop,
  and is noted in `docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md` as still outstanding.
