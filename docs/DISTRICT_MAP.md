# District map of the Hazard Summary

The Hazard Summary (BOT analysts only) shows, besides the table and the bars, a map of Tanzania with every district coloured by the **highest severity recorded there** for the chosen hazard (Concept Note, Figure 3). The panel is called "Districts on the map".

## How it is built
* **Plain SVG, no map tiles.** The browser draws the outlines itself; nothing is requested from an outside map service. It works on a closed network and no district or loan data leaves the Bank. It is not a street map: it shows outlines only.
* **Data.** `backend/app/data/tanzania_district_shapes.json.gz` (150 districts) is built by `backend/scripts/build_boundaries.py` from the NBS 2022 ward boundaries (see `COORDINATE_VALIDATION.md` for source and licence). Wards are simplified to about 330 m, which is enough for a screen and not for deciding which district a point lies in (that uses the finer ward file). Each district has `rings` (the filled shapes) and `borders` (lines of its outer limit).
* **Borders.** The ward file is not topological (neighbouring wards do not share vertices), so district outlines cannot be found by cancelling shared edges. A ring edge is treated as internal when its midpoint is within 0.0065 degrees (about 720 m) of another ring of the same district; the rest are drawn as a thin white line over the fills. This is an approximation for display only; a very narrow gap between two wards of one district could show a short stray line.
* **Matching readings to outlines.** `map_key` = normalised region + district (capitals and spaces ignored), returned with every district of `/analytics/hazard-summary`. Two spellings of one district land on one outline and their figures are added. A district whose name the map does not know is listed under the map ("not placed on the map"); it still appears in the table.
* **Endpoint.** `GET /api/analytics/district-shapes`, BOT_USER only (others 403). Same answer for everyone and no institution data, so it is sent with `ETag` and `Cache-Control: private, max-age=86400` (304 when unchanged). Only this static answer is gzip-compressed (about 0.37 MB instead of about 1.9 MB); compression is not switched on for the API in general, because compressing answers that mix secrets with attacker-influenced text is what the BREACH attack uses.

## How to read it
* Colours: High, Medium, Low, Not graded. **Grey-blue = no reading of that hazard in the selection. It does not mean safe.** The legend says so.
* Pointing at a district or touching it shows its name, highest severity and number of readings. The same facts are in the table below, which is the alternative for anyone who cannot use the map. The map has a text description for screen readers.
* Region, hazard, period and "validated only" change the map and the table together. If the outlines cannot be loaded, the panel says the map is not available and the table stays.

## Limits
* Colour shows the highest severity only, not how many readings or how large the district is; small districts (Dar es Salaam, Zanzibar towns) are hard to touch on a phone, so use the table for those.
* No population figures; no colour for wards.
* 150 districts, as in the NBS file and now in the repository's own list (its former 151st was a duplicate "korogwe", removed; see `COORDINATE_VALIDATION.md`). The Concept Note says 151: to be confirmed with the Bank.

## Tests
`backend/tests/test_district_shapes.py` (data, borders, key, endpoint, gzip, 304, access, missing file, map_key in the summary) and `frontend/src/components/DistrictMap.test.tsx` and `HazardSummary.test.tsx` (colours, legend wording, hover and touch, borders over fills, map shown and hidden, unplaced districts).
