# Coordinate validation against official boundaries

**What it does.** When an institution uploads loans, the latitude/longitude of the loan (and, separately, of the collateral)
is checked against the region, district and ward named in the same row, using the official ward boundaries of the National
Bureau of Statistics (NBS), 2022 Population and Housing Census.

| The point is... | Result | Row |
|---|---|---|
| inside the place named (or within 500 m of its edge) | nothing to report | accepted |
| in **another region** (for example Katavi coordinates under Morogoro) | **error**, the message names where the point really is | rejected |
| in the right region but **another district** | **error** | rejected |
| in the right district but **another ward** | warning | accepted, flagged for the reviewer |
| in no ward at all (a lake, the sea, another country) | warning | accepted, flagged |
| the place named is not in the boundary data | checked as before (distance from the region's centre, 300 km) | warning only |

When the point would fit if a common slip were undone, the message says so: a forgotten minus sign on the latitude
(Tanzania is south of the equator) or latitude and longitude typed the wrong way round.

Both locations are checked on every row: the loan's own location and the collateral's. A row without coordinates is not
checked (coordinates stay optional for collateral).

## Why a ward is only a warning, and the tolerance

* The ward names in the repository's own list and in the NBS file are spelt differently in a few places (tables below). A
  ward that cannot be matched is checked at district level instead of being refused.
* The shapes in the file are simplified to about 25 m so that the application stays fast and small; surveys use slightly
  different datums, and a phone's GPS is a few metres out. A point within **500 m** of the named place therefore counts as
  inside. A farm on the edge of a ward is never refused.
* Region and district are errors because the file's region and district outlines are reliable and a point in another
  region cannot be explained by spelling or rounding.

## Where the data comes from

`backend/app/data/tanzania_ward_boundaries.json.gz` (2 MB), built by `backend/scripts/build_boundaries.py` from
NBS's "2022 Population and Housing Census, Tanzania Wards" shapefile (published at
https://www.nbs.go.tz/statistics/topic/gis). The shapefile is not in the repository (18 MB). It holds 4,344 ward polygons:
31 regions, 150 districts. The script needs only the Python standard library:

```bash
python scripts/build_boundaries.py path/to/TANZANIA_2022PHC_WARDS_SHAPEFILES.shp
```

Run it again when NBS publishes new boundaries, then run the tests. The application loads the file the first time a row
with coordinates is validated (about 0.3 s) and keeps it in memory. If the file is missing, the application still works
and falls back to the old region-centre check.

**Licence.** The NBS page offers the files for download without stating a licence and refers to a copyright statement.
BOT should confirm with NBS (sg@nbs.go.tz) that the boundaries may be embedded in the repository. See `GO_LIVE_READINESS.md`.

## What it does not do

* It does not check the **village/street** (NBS has not published that level).
* It does not check climate readings from TMA/PMO (their coordinates are optional and the check is not wired to them).
* It does not change data already stored: it applies to new uploads. Nothing is corrected automatically.
* A point close to a boundary can be on the wrong side by up to the simplification, so the 500 m tolerance is deliberate.
* The NBS file has **150 districts**, the same as the repository's list; the Concept Note's figure of 151 should be
  confirmed with NBS.

## Names that differ between the repository's list and NBS

Wards in the repository's list that the boundary file does not hold under the same name (checked at district level):

| Region | District | Ward in the repository's list |
|---|---|---|
| Morogoro | Morogoro | Kibungo |
| Morogoro | Ulanga | Mahenge Mjini |
| Lindi | Nachingwea | Raha Leo |
| Lindi | Ruangwa | Mbwemkuru (Machang'anja) |
| Ruvuma | Songea | Magagula |
| Tabora | Kaliua | Mkindo |
| Njombe | Wanging'ombe | Kipengele |
| Katavi | Mpanda | Uruwira |
| Kusini Unguja | Kati | Zawiani |

Wards in the boundary file that are not in the repository's list (so they cannot be chosen from the template's dropdown yet;
an upload naming one gets the existing "not a valid ward" warning, and the coordinates are still checked at district level):

| Region | District | Ward in the NBS file |
|---|---|---|
| Arusha | Arumeru | Usa River |
| Arusha | Longido | Matale |
| Arusha | Karatu | Oldean |
| Tanga | Muheza | Kwemkabara |
| Morogoro | Morogoro | Kibungo Juu |
| Morogoro | Morogoro | Sabasaba |
| Morogoro | Kilombero | Viwanja Sitini |
| Morogoro | Ulanga | Chilombora |
| Morogoro | Ulanga | Mahenge |
| Lindi | Nachingwea | Rahaleo (Raha Leo) |
| Lindi | Ruangwa | Mbwemkuru |
| Mtwara | Mtwara | Msanga Mkuu |
| Mtwara | Newala | Kitangali |
| Mtwara | Masasi | Chikoropola |
| Ruvuma | Songea | Magagula (Magagura) |
| Mbeya | Mbeya | Izyira |
| Tabora | Igunga | Mtungulu |
| Tabora | Igunga | Ibologelo |
| Tabora | Urambo | Ugala |
| Tabora | Kaliua | Mkindo (Kanindo) |
| Tabora | Kaliua | Igombe Mkulu |
| Kigoma | Kasulu | Kagera Nkanda |
| Kagera | Bukoba | Buhendangabo |
| Kagera | Bukoba | Kanyengereko |
| Kagera | Bukoba | Kikomero |
| Mara | Tarime | Nyansicha |
| Mara | Serengeti | Isenye |
| Mara | Rorya | Nyathorongo |
| Njombe | Wanging'ombe | Kipengele(Kipengere) |
| Katavi | Mpanda | Uruwira (Urwira) |
| Kusini Unguja | Kati | Kiboje Muembe Shauri |
| Kusini Unguja | Kati | Kijibwe Mtu |
| Kusini Unguja | Kati | Ndijani Muembe Punda |
| Kusini Unguja | Kati | Zuwiyani |
| Mjini Magharibi | Mjini | Mwembe Makumbi |
| Mjini Magharibi | Mjini | Muembeladu |
| Mjini Magharibi | Mjini | Muembe Shauri |
| Mjini Magharibi | Mjini | Kisima Majongoo |
| Mjini Magharibi | Magharibi A | Chemuchem |
| Mjini Magharibi | Magharibi A | Muwembemchomeke |
| Mjini Magharibi | Magharibi A | Mtoni Chem Chem |
| Mjini Magharibi | Magharibi A | Sharifumsa |
| Mjini Magharibi | Magharibi A | Kwagoa |
| Mjini Magharibi | Magharibi B | Kiembe Samaki |
| Mjini Magharibi | Magharibi B | Kwamchina |
| Kusini Pemba | Mkoani | Kisiwa Panza |
| Mwanza | Sengerema | Nyatukala |

Both lists should be reconciled by BOT with NBS before go-live (`GO_LIVE_READINESS.md`, item 12).

## Tests

`backend/tests/test_boundaries.py` (28 tests): the data (every region and district of the repository's list exists, more than
99.5 % of its wards match), locating a point, the three kinds of mismatch, spelling, the sea, the tolerance, the typing
mistake hints, running without the data file, and uploads (an invalid loan is stored invalid, a good one in the same file
is not affected).
