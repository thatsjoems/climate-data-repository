# Installing without internet (offline network)

The Bank's server network may have no internet. Building the images needs it (about 4 minutes and several hundred MB of downloads). So the images are built **once on a machine with internet**, packed into one file, carried over, and started there with `--offline`. Nothing is built or pulled on the offline machine.

## What is needed on the offline machine
Docker with Compose v2, the project folder (copy it, without `.git` if you like), `.env.production` (or `.env.staging`) and the certificate files. `python3` is optional (it runs the configuration check; without it the check is skipped with a note).

## 1. On the machine with internet
Start the stack once so the images exist, then pack them:

```bash
scripts/staging_up.sh                       # or prod_up.sh (builds the images)
scripts/offline_bundle.sh save --stack staging
```
Windows: `.\scripts\offline_bundle.ps1 save -Stack staging`

Result: `offline/cdr-images.tar` and `offline/cdr-images.tar.sha256` (backend, frontend and `postgres:16-alpine`). One bundle serves both stacks.

## 2. Carry both files
Copy both files into the project's `offline/` folder on the target machine (USB or the Bank's approved transfer route). The checksum is verified before anything is loaded.

## 3. On the offline machine
```bash
scripts/prod_up.sh --offline          # or staging_up.sh --offline
```
Windows: `.\scripts\prod_up.ps1 -Offline`. Use `--bundle <file>` / `-Bundle <file>` for another location. The four stages are the same as always; only `--build` becomes `--no-build`.

## Updating later
Build the new version on the internet machine, run `save` again, carry the new pair, run `--offline` again. The data volumes are untouched.

## Limits to know
- The images must match the code in the project folder: after changing code, build and `save` again.
- The bundle is architecture-specific (an amd64 bundle does not run on an ARM server).
- TMA/PMO/RTIS/BSIS and e-mail still need their own network routes; offline here means only the installation.
