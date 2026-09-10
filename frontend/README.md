# CDR Frontend (React + TypeScript + Vite)

This frontend is run exclusively via Docker Compose from the project root — see the main
`README.md` and `docs/DOCKER.md`. There is no separate manual/local `npm run dev` setup path;
Docker builds it and serves it through nginx at `http://localhost:5173`.

## Structure

```
src/
  api/         -> axios client that talks to the backend
  context/     -> AuthContext (login/session management)
  components/  -> PortalShell (role-aware layout/sidebar), ProtectedRoute,
                  NotificationBell, HazardMap (Leaflet geospatial map)
  pages/       -> Login, ForgotPassword, ChangePassword, InstitutionPortal,
                  InternalPortal (BOT Analyst), AdminPanel
```
