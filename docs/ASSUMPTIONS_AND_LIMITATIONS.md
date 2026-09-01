# Assumptions, Sample Data, na Limitations

## Data - Kilichotumika

| Aina ya Data | Hali | Maelezo |
|---|---|---|
| Loan / Collateral records | **SAMPLE tu (mfano mmoja kwenye template)** | Data halisi zitatoka kwa taasisi zinazoripoti kupitia upload |
| Climate records (rainfall, temperature, hazard) | **SYNTHETIC (imetengenezwa kirandomly)** | `init_db.py` inatengeneza miaka 2024-2026, mikoa 6, kwa madhumuni ya kuonyesha jinsi analytics/dashboard zitakavyofanya kazi. **SI data halisi za TMA au PMO** |
| Users / Institutions | **DEMO accounts** | `admin`, `bot_analyst`, `bankA_user`, `bankB_user` - badilisha password kabla ya matumizi halisi |

## Assumptions zilizofanywa (kwa sababu ICN haikutaja kwa undani)

1. Roles tatu zimechaguliwa: `SYSTEM_ADMIN`, `BOT_USER` (mtumiaji wa ndani wa BOT), `INSTITUTION_USER` (taasisi ya nje). ICN ilitaja "role-based access" bila kuorodhesha majina rasmi ya roles.
2. Muundo wa template ya Excel (column: loan_id, borrower_name, loan_amount_tzs, n.k.) ni **pendekezo la kiufundi** - siyo muundo rasmi uliotolewa na BOT. Taasisi halisi itahitaji kutoa muundo rasmi wa data zake.
3. Workflow ya "Approve/Reject" kwa BOT_USER ni assumption ya kiprototype - ICN haikuainisha kama approval workflow rasmi ipo.
4. `reporting_period` format (YYYY-Qn) ni uamuzi wa kiufundi, siyo rasmi kutoka ICN.

## Ambazo HAZIJAJENGWA kwa makusudi (nje ya wigo wa wiki 8 / hazina access)

- **Live integration** na RTIS, BSIS, QGIS, ArcGIS - hazina credentials/API access halisi.
- **Data halisi** kutoka TMA (Tanzania Meteorological Authority) na PMO (Climate Vulnerability Maps) - hazipo kwenye mazingira haya.
- Password recovery (forgot password) workflow.
- Export ya Dashboard kwa PDF/Excel/Image (muundo wa data upo, lakini export endpoints hazijaongezwa).
- Enterprise SSO, production-grade deployment, na certification za usalama.

## Usalama - Kilichofanyika kwa Prototype hii

- Password zote zime-hash (bcrypt) - hazihifadhiwi kama maandishi wazi (plain text).
- Hakuna secret/password iliyowekwa moja kwa moja kwenye code (hardcoded) - zote zinatoka `.env`.
- RBAC (Role-Based Access Control) imetekelezwa kwenye kila endpoint nyeti.
- Data isolation: mtumiaji wa taasisi (`INSTITUTION_USER`) anaona TU submissions za taasisi yake mwenyewe.

**Kabla ya matumizi ya uzalishaji (production):** hii ni prototype ya mafunzo (EASTC 8-week
training) - haijafanyiwa penetration testing, haina production security certification,
na SECRET_KEY ya demo LAZIMA ibadilishwe.
