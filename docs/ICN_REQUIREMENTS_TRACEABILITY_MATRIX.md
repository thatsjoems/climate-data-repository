# ICN Requirements Traceability Matrix

Chanzo: "Concept Note on the Proposed Enhancement of the Climate Data Repository" (Bank of Tanzania, Financial Stability Department).

| # | ICN Requirement (kama ilivyoainishwa kwenye Concept Note) | Status | Ilipojengwa (System Component) |
|---|---|---|---|
| 1 | Ufikiaji salama wa nje kwa taasisi zinazoripoti (external accessibility) | **IMEJENGWA** | Login tofauti + role `INSTITUTION_USER`, data isolation kwa `institution_id` |
| 2 | Login na Role-Based Access Control | **IMEJENGWA** | `backend/app/core/security.py`, `deps.py` (JWT + RBAC guards) |
| 3 | Interfaces tofauti kwa taasisi za nje vs watumiaji wa BOT | **IMEJENGWA** | `InstitutionPortal.tsx` vs `InternalPortal.tsx` (frontend) |
| 4 | Download Template (Excel sanifu) | **IMEJENGWA** | `GET /api/templates/loan-collateral/download` |
| 5 | Upload wa data zilizojazwa | **IMEJENGWA** | `POST /api/submissions/upload` |
| 6 | Automated data validation na error feedback | **IMEJENGWA** | `validation_service.py` + `ValidationError` model |
| 7 | Submission history / tracking | **IMEJENGWA** | `GET /api/submissions` (data isolation kwa taasisi) |
| 8 | Dashboard ya BOT yenye overview ya submissions, loans, collateral, climate data | **IMEJENGWA** | `InternalPortal.tsx` + `/api/analytics/kpi-summary` |
| 9 | Advanced filtering (institution, period, geography, hazard) | **SEHEMU (MVP)** | Status filter imejengwa; filtering kamili kwa geography/period ni **SHOULD-HAVE** kwa awamu ijayo |
| 10 | Export Dashboard (PDF, Excel, CSV, image) | **HAIJAJENGWA (Future Work)** | Muundo wa data upo tayari (API zinarudisha JSON) - export endpoints ni hatua inayofuata rahisi kuongeza |
| 11 | Password recovery workflow | **HAIJAJENGWA (Should-Have)** | Imetajwa kwenye ICN kama functionality inayotakiwa; haijajengwa kwenye prototype hii ya wiki 8 |
| 12 | Integration na RTIS, BSIS, QGIS, ArcGIS | **HAIJAJENGWA - Nje ya wigo (Future/Mock)** | Hakuna credentials/API access halisi zilizotolewa. Usanifu wa backend (modular API routers) ni "integration-ready" lakini hakuna adapter halisi iliyojengwa |
| 13 | Institutional onboarding (focal person nomination) | **SEHEMU** | Admin anaweza kuongeza taasisi na watumiaji kwa mkono (`AdminPanel.tsx`); mchakato kamili wa "nomination workflow" haujajengwa |
| 14 | Audit logging | **IMEJENGWA** | `AuditLog` model + `audit_service.py`, inarekodi LOGIN, SUBMISSION_CREATED, USER_CREATED, n.k. |
| 15 | Climate risk assessment kwa sekta ya benki (exposure analysis) | **SEHEMU (Prototype indicator)** | `analytics_service.get_hazard_exposure()` - inaonyesha jumla ya mikopo kwa mkoa/hazard kutoka data halisi za submissions. **Hii SI rasmi "climate risk score"** - ni muhtasari wa maelezo (descriptive) tu |
| 16 | Meteorological data integration (TMA) | **SAMPLE/SYNTHETIC** | `ClimateRecord` table imejazwa data za MFANO (synthetic) zenye `source="SYNTHETIC_SAMPLE"` - SI data halisi za TMA |
| 17 | Climate Vulnerability Maps (PMO) | **HAIJAJENGWA** | Hakuna data au access iliyotolewa - nje ya wigo wa prototype hii |

## Muhtasari

- Mfumo mzima wa **MUST HAVE** (workflow kamili: login → template → upload → validation → storage → internal review → dashboard) **UMEJENGWA na unafanya kazi kikamilifu**.
- **SHOULD HAVE** (export, advanced filters, password recovery) - misingi ipo (API tayari zinarudisha data sahihi), lakini UI/endpoints za ziada bado hazijaongezwa.
- **FUTURE WORK** (live RTIS/BSIS/QGIS/ArcGIS integration, TMA/PMO data halisi) - haziwezekani bila access/credentials halisi kutoka BOT - zimeandikwa wazi humu kama mapungufu, SI zimefichwa.
