# Database Schema

Mfumo huu unatumia SQLAlchemy ORM (angalia `backend/app/models/models.py`) kama
"chanzo cha ukweli" (single source of truth) cha muundo wa database.

Majedwali (tables) yanatengenezwa moja kwa moja unapoendesha:

```
python init_db.py
```

Hii inatumika kwa SQLite (default, hauitaji usanidi) na PostgreSQL (baada ya
kubadilisha DATABASE_URL kwenye .env).

## Muhtasari wa Majedwali (Entity Summary)

| Jedwali | Kusudi |
|---|---|
| institutions | Taasisi zinazoripoti (mabenki, TMA, n.k.) |
| users | Watumiaji wote wa mfumo (Admin, BOT_USER, INSTITUTION_USER) |
| submissions | Kila uwasilishaji wa faili ya data |
| submission_records | Kila safu (row) ya data ndani ya submission (mfano: mkopo mmoja) |
| validation_errors | Makosa yaliyopatikana wakati wa validation ya submission |
| climate_records | Data za hali ya hewa (SAMPLE/SYNTHETIC - angalia backend README) |
| audit_logs | Kumbukumbu za matukio muhimu ya mfumo |

Kwa ERD kamili, tumia zana kama `dbdiagram.io` ukiweka muundo wa juu, au
tumia `sqlalchemy_schemadisplay` baada ya kusakinisha packages zote.
