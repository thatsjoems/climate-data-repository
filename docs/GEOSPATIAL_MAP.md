# Geospatial Overview Map

## What this is

The "Geospatial Overview — Hazard Exposure & Portfolio" panel on the BOT
Analyst dashboard renders a real, interactive map (not a placeholder) showing
climate hazard exposure by region.

- **Map technology:** [Leaflet](https://leafletjs.com/) with
  [OpenStreetMap](https://www.openstreetmap.org/) tiles — free, open-source,
  self-hosted client-side. No API key, no external account, no QGIS/ArcGIS
  dependency.
- **What's plotted:** one circle per region that has valid submitted loan
  data. Circle **size** is proportional to total loan exposure in that
  region (square-root scaled so the largest region doesn't visually swamp
  the map); circle **color** reflects the dominant reported climate hazard
  for that region (Drought, Flood, Cyclone, Landslide, or None).
- **Coordinates used:** region **centroid** coordinates (approximately each
  region's capital), sourced from Wikipedia region articles (verified via
  web search — not invented). See `backend/app/services/geo_reference.py`
  for the full table of all 31 regions.

## Why region-level, not exact loan locations

`SubmissionRecord` currently stores `region` and `district` as text, not
coordinates — institutions do not yet submit exact latitude/longitude per
loan. Per explicit direction, adding coordinate fields to the submission
template is deliberately deferred until BOT provides their own official data
template (which is expected to include geospatial points). Building this
map now, at region-level, using data we already have, avoids waiting on that
and avoids depending on an external system:

> "mfumo huu unatakiwa u-operate kupitia data tu zitakazo kuwa submitted
> na institutions na zile data za climate — kifupi ni mfumo wa
> kujitegemea kabisa" (the system should operate only on data submitted by
> institutions and our own climate data — in short, a self-sufficient system)

## What happens when BOT's template arrives

Once `longitude`/`latitude` columns are added to the submission template and
`SubmissionRecord`, the same `HazardMap` component can be extended to plot
individual loan/collateral markers (in addition to, or instead of, the
region-level circles) — the map infrastructure itself does not need to
change, only the data feeding it.

## Relationship to RTIS/BSIS/QGIS/ArcGIS (still not integrated)

This map remains **independent** of RTIS, BSIS, QGIS Server, and ArcGIS -
none of those are connected, and no credentials or API access exist for
them; they remain listed as "Not Connected" in the sidebar, honestly.

**PMO's Tanzania Climate Vulnerability Map is the one exception**, added
per explicit request - see the "Update" section immediately below for what
was added and why. It is a separate, independent government platform (not
QGIS/ArcGIS/RTIS/BSIS), and the integration is a thin, optional tile-overlay
layer, not a data-sharing pipeline of the kind envisioned for RTIS/BSIS.

## Update: PMO hazard layer overlay (added after direct request)

Per explicit direction, an optional overlay tile layer from PMO's own
**Tanzania Climate Vulnerability Maps** platform (`tcvmp.pmo.go.tz`, run
jointly with the Global Center on Adaptation) was added underneath our
institution-exposure circles, matching the visual style shown in the
original ICN Figure 3 mockup (a hazard heatmap + location markers together).

**How the endpoint was found:** `tcvmp.pmo.go.tz` runs on
[g3w-suite](https://github.com/g3w-suite) (an open-source, QGIS-Server-based
web GIS platform). Its built-in layer "Information" tool failed to load a
legend for the layers it exposed by default, so the actual tile URL pattern
was found by inspecting the browser's Network tab while using the live
public map:

```
https://tcvmp.pmo.go.tz/tiles/singleband/climatology/{indicator}/{scenario}/{period}/{z}/{x}/{y}.png?colormap={colormap}
```

This is a standard XYZ tile scheme, directly compatible with Leaflet's
`TileLayer`. `flood` was confirmed working; `drought` is used by the same
pattern based on the platform's own indicator list, on the reasonable
assumption of a consistent naming convention, but has not been individually
re-verified tile-by-tile.

**Important caveats, stated plainly:**
- This is a **discovered public endpoint**, not a documented API and not the
  result of a data-sharing agreement with PMO. PMO could change, rate-limit,
  or retire it without notice.
- The layer is **optional and fails gracefully**: a `tileerror` handler
  ensures a broken/unreachable tile never breaks the map or hides this
  system's own institution-exposure circles, which come entirely from our
  own data and remain functional with or without the PMO layer.
- Per the project's honesty principle, the map clearly labels the PMO layer
  as an independent external data source, distinct from institution
  submissions, right under the map (not just in this doc).
- This reintroduces one external, unofficial runtime dependency for this
  visual layer only - a deliberate, explicit trade-off against the
  "self-sufficient system" preference stated earlier in the project, made
  because the visual match to the ICN mockup was judged worth it for this
  specific element. Nothing else in the system depends on PMO's endpoint.



## Update: choosing more than one hazard and financial layer (at BOT's request)

The two lists above the map ("Hazard layer" and "Financial layer") are now tick-box lists instead of single-choice lists:

- Open a list, tick the boxes you want, and press **Apply**. Nothing on the map changes until Apply; closing the list any other way (a click elsewhere, Escape) keeps the previous choice.
- **Hazard layer:** None, All, Flood, Drought, Landslide, Cyclone. Any number can be ticked, for example Flood and Drought together. The map draws one surface for each ticked hazard, each in its own colour (the same colours as the hazard pie chart), and the legend lists each one. A hazard with no recorded exposure under the current filters is named in the legend as such instead of silently drawing nothing.
- **Financial layer:** None, All, Loan, Collateral. All ticks both; Loan or Collateral can also be chosen alone. Each ticked layer is drawn as dots at the real latitude and longitude entered on the template (the loan's own location for Loan, the collateral's own for Collateral), in its own pale-to-saturated colour scale. Collateral is drawn first so a loan dot is never hidden under it.
- "All" is ticked when every box is, and "None" when no box is; the closed list shows the choice ("Flood, Drought", "All", "None").
- The hazard chosen in Dashboard Filters still drives the hazard list: choosing Flood there ticks only Flood here.
- The data is the same as before (`GET /api/analytics/hazard-exposure`, `/map-points` and `/exposure-points`); nothing changed on the server. The choice rules are in `frontend/src/data/mapLayers.ts`, the list in `CheckboxDropdown.tsx`, and the tests in `mapLayers.test.ts`, `CheckboxDropdown.test.tsx` and `HazardMap.test.tsx`.

**Known limit:** each of Loan and Collateral returns at most 20,000 points (`get_exposure_points`), so choosing All can draw up to 40,000 dots. The map draws them on one canvas, but a very large portfolio may feel slower than choosing one layer; narrow it with the Dashboard Filters if so.

## API

`GET /api/analytics/map-points` (BOT_USER and INSTITUTION_USER, scoped to
own institution for INSTITUTION_USER) returns:

```json
[
  {
    "region": "Dodoma",
    "latitude": -6.163,
    "longitude": 35.7516,
    "total_exposure_tzs": 5000000.0,
    "record_count": 3,
    "dominant_hazard": "Drought"
  }
]
```

A region is only included if it has valid submitted exposure data AND a
known centroid coordinate — an unrecognized region name is silently
excluded rather than plotted at a guessed location.
