# CDR Frontend (React + TypeScript + Vite)

## Kuanzisha

```bash
cd frontend
npm install
copy .env.example .env     # Windows (Mac/Linux: cp .env.example .env)
npm run dev
```

Frontend itapatikana kwenye: http://localhost:5173

**MUHIMU**: Backend (`uvicorn app.main:app --reload`) LAZIMA iwe inaendesha kwanza,
vinginevyo login na kurasa zote hazitafanya kazi.

## Muundo

```
src/
  api/        -> axios client inayoongea na backend
  context/    -> AuthContext (usimamizi wa login/session)
  components/ -> Navbar, ProtectedRoute
  pages/      -> Login, InstitutionPortal (taasisi), InternalPortal (BOT), AdminPanel
```
