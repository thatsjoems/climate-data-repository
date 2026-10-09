// The smooth hazard surface of the Geospatial Overview (moved out of HazardMap.tsx unchanged, so it can be replaced in tests).

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dp = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lon2 - lon1) * Math.PI) / 180
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

// Inverse Distance Weighting (IDW) - the same real, published spatial
// interpolation technique national hazard-mapping studies use (for example,
// Al-Hemoud et al. 2023, "Hazard Assessment and Hazard Mapping for Kuwait",
// Int. J. Disaster Risk Science, which interpolates rainfall/drought indices
// from a small number of weather stations into a smooth national surface
// using IDW in ArcGIS). Built here in plain JavaScript/Canvas - no GIS
// library was available to install in this environment - to turn this
// project's own sparse per-region hazard exposure into the same kind of
// smooth, continuous, country-wide surface, rather than isolated dots.
export function buildIdwSurface(
  dataPoints: { lat: number; lon: number; value: number }[],
  bounds: { south: number; north: number; west: number; east: number },
  colorRgb: [number, number, number],
  gridSize = 140,
): string {
  const canvas = document.createElement('canvas')
  canvas.width = gridSize
  canvas.height = gridSize
  const ctx = canvas.getContext('2d')
  if (!ctx || dataPoints.length === 0) return ''
  const imageData = ctx.createImageData(gridSize, gridSize)
  const maxValue = Math.max(...dataPoints.map((p) => p.value), 0.0001)
  const power = 2.2
  const minOpacity = 0
  const maxOpacity = 235 // out of 255 - never fully solid, base map stays faintly visible

  for (let row = 0; row < gridSize; row++) {
    const lat = bounds.north - (row / (gridSize - 1)) * (bounds.north - bounds.south)
    for (let col = 0; col < gridSize; col++) {
      const lon = bounds.west + (col / (gridSize - 1)) * (bounds.east - bounds.west)
      let weightedSum = 0
      let weightSum = 0
      for (const p of dataPoints) {
        const d = haversineKm(lat, lon, p.lat, p.lon)
        const w = 1 / Math.pow(Math.max(d, 1), power)
        weightedSum += w * p.value
        weightSum += w
      }
      const interpolatedValue = weightSum > 0 ? weightedSum / weightSum : 0
      // The line above is intentionally NOT the bug it looks like: weightedSum
      // and weightSum are DIFFERENT accumulators (sum of weight*value vs sum
      // of weight) - weightedSum / weightSum IS the correct IDW weighted
      // average. Normalize that against this layer's own max value to get a
      // 0..1 intensity, then map to an alpha channel - never a fixed/solid
      // color, so the surface genuinely reads as low-to-high concentration.
      const normalizedIntensity = Math.max(0, Math.min(1, interpolatedValue / maxValue))
      const alpha = Math.round(minOpacity + normalizedIntensity * (maxOpacity - minOpacity))

      const idx = (row * gridSize + col) * 4
      imageData.data[idx] = colorRgb[0]
      imageData.data[idx + 1] = colorRgb[1]
      imageData.data[idx + 2] = colorRgb[2]
      imageData.data[idx + 3] = alpha
    }
  }
  ctx.putImageData(imageData, 0, 0)
  return canvas.toDataURL()
}
