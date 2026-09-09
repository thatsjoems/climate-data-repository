"""
MODULE: Geographic reference data (region-level centroid coordinates).

Approximate centroid (regional capital) coordinates for Tanzania's 31 regions,
sourced from Wikipedia region articles (verified via web search, not invented).
Used to plot REGION-LEVEL markers on the Geospatial Overview map using data we
already have (climate hazard exposure aggregated by region from institution
submissions) - this works independently of any external GIS system and
without needing exact per-loan coordinates, which are not yet collected.

These are region centroids, not exact loan/collateral locations - the map
built from this data is clearly labelled as region-level, not precise.
"""

REGION_COORDINATES: dict[str, tuple[float, float]] = {
    # (latitude, longitude)
    "Dodoma": (-6.1630, 35.7516),
    "Singida": (-4.8180, 34.7453),
    "Tabora": (-5.0425, 32.8197),
    "Dar es Salaam": (-6.7924, 39.2083),
    "Lindi": (-9.9968, 39.7144),
    "Morogoro": (-6.8235, 37.6612),
    "Mtwara": (-10.2692, 40.1839),
    "Pwani": (-7.3238, 38.8205),
    "Kagera": (-1.3316, 31.8225),
    "Kigoma": (-4.8824, 29.6615),
    "Geita": (-2.8710, 32.2320),
    "Mara": (-1.5000, 33.8000),
    "Mwanza": (-2.5164, 32.9000),
    "Shinyanga": (-3.6614, 33.4233),
    "Simiyu": (-2.8000, 34.0000),
    "Arusha": (-3.3667, 36.6833),
    "Kilimanjaro": (-3.3500, 37.3400),
    "Manyara": (-4.3150, 36.9541),
    "Tanga": (-5.3050, 38.3166),
    "Iringa": (-7.7681, 35.6861),
    "Katavi": (-6.3677, 31.2626),
    "Mbeya": (-8.9000, 33.4500),
    "Njombe": (-9.3300, 34.7700),
    "Rukwa": (-7.9667, 31.6167),
    "Ruvuma": (-10.6833, 35.6500),
    "Songwe": (-9.0000, 32.9000),
    "Mjini Magharibi": (-6.2298, 39.2583),
    "Kaskazini Unguja": (-5.9395, 39.2791),
    "Kusini Unguja": (-6.3500, 39.5000),
    "Kaskazini Pemba": (-5.0500, 39.7300),
    "Kusini Pemba": (-5.3147, 39.7756),
}


def get_region_coordinates(region: str) -> tuple[float, float] | None:
    return REGION_COORDINATES.get(region)
