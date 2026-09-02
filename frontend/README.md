# CDR Frontend (React + TypeScript + Vite)

## Getting Started

```bash
cd frontend
npm install
copy .env.example .env     # Windows (macOS/Linux: cp .env.example .env)
npm run dev
```

The frontend will be available at: http://localhost:5173

**IMPORTANT**: The backend (`uvicorn app.main:app --reload`) must already be running,
otherwise login and all pages will fail to load data.

## Structure

```
src/
  api/        -> axios client that talks to the backend
  context/    -> AuthContext (login/session management)
  components/ -> Navbar, ProtectedRoute
  pages/      -> Login, InstitutionPortal, InternalPortal (BOT), AdminPanel
```
