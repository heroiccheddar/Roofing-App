/**
 * Mapbox Directions API wrapper for driving route generation.
 */

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

export interface DirectionsResult {
  geometry: GeoJSON.LineString
  distance_km: number
  duration_minutes: number
}

/**
 * Get a driving route through an ordered list of coordinates.
 *
 * Uses the Mapbox Directions API v5 with GeoJSON geometry output.
 * Supports up to 25 waypoints per request.
 *
 * @param coordinates Array of [lon, lat] pairs (first = start, rest = stops)
 */
export async function getDirectionsRoute(
  coordinates: [number, number][],
): Promise<DirectionsResult> {
  if (coordinates.length < 2) {
    throw new Error('At least 2 coordinates required for a route')
  }

  const coordStr = coordinates.map(([lon, lat]) => `${lon},${lat}`).join(';')
  const url = `https://api.mapbox.com/directions/v5/mapbox/driving/${coordStr}?geometries=geojson&overview=full&access_token=${MAPBOX_TOKEN}`

  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`Mapbox Directions API error: ${res.status}`)
  }

  const data = await res.json()
  if (!data.routes || data.routes.length === 0) {
    throw new Error('No route found between the given coordinates')
  }

  const route = data.routes[0]
  return {
    geometry: route.geometry,
    distance_km: route.distance / 1000,
    duration_minutes: route.duration / 60,
  }
}
