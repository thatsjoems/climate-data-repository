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

This map is intentionally **independent** of those systems. Real GIS
platforms like QGIS Server or ArcGIS would be useful later for overlaying
official hazard-vulnerability zone polygons (e.g. from PMO's Tanzania
Climate Vulnerability Map, `tcvmp.pmo.go.tz` — confirmed to be a real public
platform, GCA/PMO-run) underneath our own institution markers. That
integration was explicitly **not** pursued here in favor of keeping the
system self-sufficient; RTIS/BSIS/QGIS/ArcGIS remain listed as
"Not Connected" in the sidebar, honestly, since no credentials or API access
exist for them.

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
