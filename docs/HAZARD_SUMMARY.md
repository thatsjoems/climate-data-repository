# Climate Data - Hazard Summary

The panel "Climate Data - Hazard Summary" of the BOT dashboard (Concept Note, Figure 3) answers one question: **for one hazard, in which
districts was it recorded, and how severe?** It sits below the Geospatial Overview.

## What it shows
* Choices: **Hazard type** (Drought, Flood, Landslide, Cyclone), **Time period** (a reporting period such as 2026-Q2, or all), **Region**, and a box
  "Include readings not yet validated".
* Figures: districts with the hazard recorded, regions, the highest severity recorded, and the number of readings counted.
* A bar for the number of districts at each highest severity (High, Medium, Low, Not graded).
* A table of districts, worst first (highest severity, then more readings, then name); the worst ten, with "Show all".

## Where the figures come from
`GET /api/analytics/hazard-summary?filter_hazard_type=Drought[&filter_reporting_period=2026-Q2][&filter_region=Dodoma][&validated_only=false]`
(BOT analysts only; an administrator or an institution user is refused with 403).

* Only recorded **climate readings** (`climate_records`) are read. Loans and submissions are not looked at, so the panel works before any institution
  has reported anything.
* By default only **VALIDATED** readings count (the supervisory default, as for Hazard Exposure). With the box ticked, every reading that is not
  FLAGGED counts. **Flagged readings never count.**
* A reading belongs to a period by its own `reporting_period`; an older reading without one is placed by its year and month (April to June 2026 = 2026-Q2),
  exactly as Hazard Exposure does.
* A district's severity is the **highest grade among its readings** (LOW, MEDIUM, HIGH); a district whose readings carry no grade is "Not graded".
* Readings recorded for a region only (no district) are counted in the totals and mentioned in a note, but cannot be placed in a district.
* The lists offered in the Time period and Region choices are the periods and regions that have readings of the chosen quality, whatever else is chosen.

## What it deliberately does not do
* **A district that is not listed has no reading of this hazard in the selection.** That does not mean it is safe; the panel never shows "normal" for a
  place without data.
* **No affected population.** The concept note's mock-up shows "Affected Population 2.45 M". The repository holds no population figures, and none is
  estimated. It needs an agreed source (for example the census figures per district) and a rule for what "affected" means.
* **No district-by-district colour map.** The mock-up colours a map of Tanzania by district. That needs the boundary of every district, which the repository
  does not hold, and the boundaries must match the district names used in the data. It needs a Bank-approved boundary source (see
  `docs/GO_LIVE_READINESS.md`). Until then the table and the bars carry the same information.
* **Three grades, not five.** The mock-up's legend has Normal, Low, Moderate, High and Very High. The data model (and its database rule) allows LOW,
  MEDIUM and HIGH, so the panel shows those three and "Not graded".

## Tests
`backend/tests/test_hazard_summary.py` (ordering and counts, one hazard at a time, period and region, readings without a period, validated-only and flagged
readings, readings without a district, no readings, the pickers' lists, refused parameters, who may read it) and
`frontend/src/components/HazardSummary.test.tsx` (figures and order, hazard change, pickers, the validated box, ten districts and "Show all", region-only
note, the empty and failed states).

*Update:* district boundaries now exist in the repository (`COORDINATE_VALIDATION.md`), so a colour map by district is possible later; it is not built, and population figures are still missing.
