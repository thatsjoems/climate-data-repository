// Single shared source of truth for hazard colors - used by both HazardMap.tsx
// (Geospatial Overview) and InternalPortal.tsx (Climate Hazard Exposure
// Distribution pie chart). Both describe the same underlying
// climate_records.hazard_type data, so a given hazard must render as the
// exact same color everywhere it appears - keeping one copy here, rather
// than two independently hand-maintained objects, means they can never
// silently drift out of sync when one is edited without the other.
export const HAZARD_COLORS: Record<string, string> = {
  Flood: '#1F5C8B',
  Drought: '#C1600C',
  Landslide: '#6B4A2E',
  Cyclone: '#7F3FA3',
}

// "None" (no hazard recorded) is kept separate from the map above: the map
// never renders a "None" glow at all (an unrecorded hazard shows nothing,
// not a color), while the pie chart's "None" slice needs an explicit grey
// so an untagged slice reads as "nothing" rather than an arbitrary color.
export const HAZARD_NONE_COLOR = '#B8B4A8'
