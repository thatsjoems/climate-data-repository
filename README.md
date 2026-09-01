# Climate Data Repository (CDR) — Bank of Tanzania
### Mradi wa Mafunzo ya EASTC (Wiki 8) — Prototype Kamili Inayofanya Kazi

Hii ni **prototype halisi inayofanya kazi** (siyo dhana tu / concept only) ya mfumo
uliopendekezwa kwenye Concept Note yako: usajili wa taasisi, kupakua template,
kupakia data, uhakiki wa data (validation), uhifadhi, ukaguzi wa ndani (BOT), na
dashboard za uchambuzi (analytics).

**Soma faili hii MZIMA kabla ya kuanza.** Fuata hatua kwa mpangilio — usiruke hatua.

---

## SEHEMU YA 0: Ni nini hiki?

Mfumo una vipande viwili vinavyofanya kazi pamoja, kila kimoja lazima "kiwashwe" (run)
kwenye Terminal yake:

1. **Backend** (Python/FastAPI) — "ubongo" wa mfumo: database, validation, security.
   Inaendesha kwenye: `http://localhost:8000`
2. **Frontend** (React) — hii ndiyo website unayoiona na kuibofya kwa panya.
   Inaendesha kwenye: `http://localhost:5173`

Zote mbili lazima ziwe "zinaendesha" (running) kwa wakati mmoja, kwenye Terminal
mbili tofauti, ili mfumo ufanye kazi.

---

## SEHEMU YA 1: WASHA BACKEND (fanya hivi kwanza)

1. Fungua VS Code kwenye folda ya `climate-data-repository` uliyoipokea.
2. Fungua **Terminal mpya** (Terminal → New Terminal).
3. Andika amri hizi MOJA BAADA YA NYINGINE, ukibonyeza Enter baada ya kila moja:

```
cd backend
python -m venv venv
venv\Scripts\activate
```

Ukifanikiwa, utaona neno `(venv)` mwanzoni mwa mstari wa terminal — hii inaonyesha
"mazingira" maalum ya mradi yamewashwa.

4. Sasa sakinisha maktaba (libraries) zote zinazohitajika (hii inaweza kuchukua dakika 2-5):

```
pip install -r requirements.txt
```

5. Tengeneza faili ya mipangilio (bado ndani ya folda `backend`):

```
copy .env.example .env
```

6. Tengeneza database na uweke akaunti za majaribio (demo):

```
python init_db.py
```

Utaona ujumbe wenye majina ya akaunti za DEMO (username/password) — **zihifadhi**,
utazihitaji Sehemu ya 3.

7. Washa backend:

```
uvicorn app.main:app --reload
```

Ukiona mstari unaosema `Uvicorn running on http://127.0.0.1:8000` — Hongera!
Backend inafanya kazi. **USIFUNGE Terminal hii** — iache ikiendelea kuendesha.

Unaweza kuthibitisha kwa kufungua browser na kwenda: http://localhost:8000/docs
(utaona ukurasa wa API documentation moja kwa moja).

---

## SEHEMU YA 2: WASHA FRONTEND (Terminal MPYA — ya pili)

**MUHIMU:** Usifunge Terminal ya Backend. Fungua Terminal NYINGINE mpya
(kwenye VS Code: bonyeza alama ya "+" juu ya eneo la Terminal).

Kwenye Terminal hii mpya:

```
cd frontend
npm install
copy .env.example .env
npm run dev
```

`npm install` inaweza kuchukua dakika 2-5 (inapakua maktaba za React).

Ukiona `Local: http://localhost:5173/` — frontend inafanya kazi.

Fungua browser (Chrome/Edge) nenda: **http://localhost:5173**

Utaona ukurasa wa Login wa mfumo wa CDR.

---

## SEHEMU YA 3: INGIA NA UJARIBU MFUMO

Tumia mojawapo ya akaunti za DEMO ulizoziona kwenye Hatua ya 6 (Sehemu ya 1):

| Aina ya Mtumiaji | Username | Password |
|---|---|---|
| System Admin | `admin` | `Admin@123` |
| BOT Analyst (Internal) | `bot_analyst` | `Analyst@123` |
| Taasisi (Bank A) | `bankA_user` | `BankA@123` |

**Jaribu mfumo mzima (end-to-end) hivi:**

1. Ingia kama `bankA_user` → utaona "Portal ya Taasisi".
2. Bonyeza "Pakua Template" → faili la Excel litapakuliwa.
3. Fungua faili hilo, ijaze data (au acha mfano uliopo kwenye row 2), ihifadhi.
4. Rudi kwenye website, chagua faili hilo, weka "Reporting Period" (mfano `2026-Q3`), bonyeza "Pakia".
5. Utaona matokeo ya validation papo hapo.
6. Toka (Logout), ingia kama `bot_analyst` → utaona Dashboard ya Ndani yenye KPI zote,
   submission uliyopakia, na uwezo wa "Kubali" au "Kataa".
7. Ingia kama `admin` → utaona ukurasa wa "Usimamizi" wa kuongeza taasisi/watumiaji wapya.

---

## Kila siku unapoendelea na kazi (baada ya usanidi wa mara ya kwanza)

Huhitaji kurudia `pip install` au `npm install` tena. Fanya tu:

**Terminal 1 (Backend):**
```
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload
```

**Terminal 2 (Frontend):**
```
cd frontend
npm run dev
```

---

## Ukikwama (Troubleshooting)

| Tatizo | Suluhisho |
|---|---|
| `'python' is not recognized` | Python haikusakinika vizuri — rudia usakinishaji, hakikisha "Add to PATH" ilikuwa na tiki |
| `'npm' is not recognized` | Node.js haikusakinika vizuri — sakinisha tena kutoka nodejs.org |
| Ukurasa wa frontend unasema "Network Error" au haujibu | Hakikisha Terminal ya Backend bado inaendesha (Sehemu ya 1, hatua ya 7) |
| `pip install` inashindwa | Hakikisha uko ndani ya `(venv)` — angalia neno hilo mwanzoni mwa terminal |
| Umefunga Terminal kimakosa | Fungua mpya, fuata sehemu ya "Kila siku unapoendelea" hapo juu |

Ukikwama mahali popote, niletee **ujumbe kamili wa error** unaoonekana kwenye terminal
au browser, nitakusaidia kuurekebisha.

---

## Muundo wa Mradi

```
climate-data-repository/
  backend/          -> FastAPI (Python) - database, API, validation, security
  frontend/          -> React (TypeScript) - website
  database/           -> maelezo ya muundo wa database
  data/                -> sample/synthetic data
  docs/                -> Requirements Traceability Matrix, Assumptions & Limitations
```

Kwa maelezo zaidi ya kiufundi:
- `docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md` — ni requirements gani za Concept Note
  zimejengwa, zipi bado, na kwanini.
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md` — nini ni sample/synthetic data, na nini
  hakijajengwa kwa sababu ya ukosefu wa access (RTIS, BSIS, QGIS, ArcGIS, TMA, PMO).
- `backend/README.md` na `frontend/README.md` — maelezo ya kiufundi zaidi ya kila upande.

**Hii ni prototype ya wiki 8 ya EASTC** — inaonyesha workflow kamili
(login → template → upload → validation → storage → review → dashboard) ikifanya kazi
kwa data za mfano. Kwa matumizi halisi ya BOT, itahitajika: data halisi kutoka TMA/PMO,
access ya RTIS/BSIS/QGIS/ArcGIS, na review ya kiusalama (security review) kamili.
