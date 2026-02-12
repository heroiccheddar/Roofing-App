import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { useZonesGeoJSON } from '../hooks/useZones'
import useAppStore from '../stores/appStore'

// Mapbox token from env
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || ''

// Continuous color ramp expressions (interpolate on composite_score 0-100)
// Roof age: cool blue → teal → green → amber → red
const ROOF_AGE_COLOR_RAMP: mapboxgl.Expression = [
  'interpolate', ['linear'],
  ['get', 'composite_score'],
  20, '#93C5FD',   // Blue-300  (low)
  35, '#5EEAD4',   // Teal-300
  50, '#34D399',   // Emerald-400
  65, '#FBBF24',   // Amber-400
  80, '#EF4444',   // Red-500   (high)
]

// Storm: indigo → sky → amber → orange → red
const STORM_COLOR_RAMP: mapboxgl.Expression = [
  'interpolate', ['linear'],
  ['get', 'composite_score'],
  20, '#A5B4FC',   // Indigo-300 (low)
  35, '#7DD3FC',   // Sky-300
  50, '#FDE68A',   // Amber-200
  65, '#FB923C',   // Orange-400
  80, '#DC2626',   // Red-600    (high)
]

function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const fittedRef = useRef(false)
  const [mapLoaded, setMapLoaded] = useState(false)
  const homeMarkerRef = useRef<mapboxgl.Marker | null>(null)
  const { data: geojson } = useZonesGeoJSON()
  const selectedZoneId = useAppStore((s) => s.selectedZoneId)
  const setSelectedZoneId = useAppStore((s) => s.setSelectedZoneId)
  const homeLat = useAppStore((s) => s.homeLat)
  const homeLon = useAppStore((s) => s.homeLon)

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return

    const map = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/light-v11',
      center: [-98.5, 39.8], // Center of Tornado Alley
      zoom: 5,
    })

    map.addControl(new mapboxgl.NavigationControl(), 'top-right')

    map.on('load', () => {
      // Add empty source (will be updated when data arrives)
      map.addSource('zones', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      // Fill layer for zone polygons — continuous color gradient
      map.addLayer({
        id: 'zones-fill',
        type: 'fill',
        source: 'zones',
        paint: {
          'fill-color': [
            'case',
            ['==', ['get', 'lead_type'], 'roof_age'],
            ROOF_AGE_COLOR_RAMP,
            STORM_COLOR_RAMP,
          ] as any,
          'fill-opacity': 0.55,
        },
      })

      // Outline layer — same gradient, slightly darker via opacity
      map.addLayer({
        id: 'zones-outline',
        type: 'line',
        source: 'zones',
        paint: {
          'line-color': [
            'case',
            ['==', ['get', 'lead_type'], 'roof_age'],
            ROOF_AGE_COLOR_RAMP,
            STORM_COLOR_RAMP,
          ] as any,
          'line-width': 2,
          'line-opacity': 0.8,
        },
      })

      // Highlight fill for selected zone
      map.addLayer({
        id: 'zones-highlight-fill',
        type: 'fill',
        source: 'zones',
        paint: {
          'fill-color': '#00BFFF',
          'fill-opacity': 0.25,
        },
        filter: ['==', ['get', 'id'], ''],
      })

      // Highlight outline for selected zone
      map.addLayer({
        id: 'zones-highlight-outline',
        type: 'line',
        source: 'zones',
        paint: {
          'line-color': '#00BFFF',
          'line-width': 3,
        },
        filter: ['==', ['get', 'id'], ''],
      })

      // Click handler for zones
      map.on('click', 'zones-fill', (e) => {
        if (e.features && e.features.length > 0) {
          const feature = e.features[0]
          const zoneId = feature.properties?.id
          if (zoneId) {
            setSelectedZoneId(zoneId)
          }
        }
      })

      // Cursor change on hover
      map.on('mouseenter', 'zones-fill', () => {
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', 'zones-fill', () => {
        map.getCanvas().style.cursor = ''
      })

      setMapLoaded(true)
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [setSelectedZoneId])

  // Update GeoJSON data when it changes, fit bounds on first load
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded || !geojson) return

    const source = map.getSource('zones') as mapboxgl.GeoJSONSource | undefined
    if (source) {
      source.setData(geojson as any)
    }

    // Fit map to zone bounds on first data load
    if (!fittedRef.current && geojson.features && geojson.features.length > 0) {
      fittedRef.current = true
      const bounds = new mapboxgl.LngLatBounds()
      for (const feature of geojson.features) {
        const coords = (feature.geometry as any).coordinates
        if (!coords) continue
        // Polygon: coords[0] is the outer ring
        for (const ring of coords) {
          for (const coord of Array.isArray(ring[0]) ? ring : [ring]) {
            if (Array.isArray(coord) && coord.length >= 2) {
              bounds.extend([coord[0], coord[1]] as [number, number])
            }
          }
        }
      }
      if (!bounds.isEmpty()) {
        map.fitBounds(bounds, { padding: 80, maxZoom: 12 })
      }
    }
  }, [geojson, mapLoaded])

  // Update highlight filter when selection changes
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const filter: any = selectedZoneId
      ? ['==', ['get', 'id'], selectedZoneId]
      : ['==', ['get', 'id'], '']
    if (map.getLayer('zones-highlight-fill')) {
      map.setFilter('zones-highlight-fill', filter)
    }
    if (map.getLayer('zones-highlight-outline')) {
      map.setFilter('zones-highlight-outline', filter)
    }
  }, [selectedZoneId])

  // Fly to zone when selected from sidebar
  useEffect(() => {
    const map = mapRef.current
    if (!map || !selectedZoneId || !geojson?.features) return

    const feature = geojson.features.find(
      (f: any) => f.properties?.id === selectedZoneId
    )
    if (!feature) return

    const coords = (feature.geometry as any).coordinates
    if (!coords?.[0]) return

    // Compute centroid from polygon ring
    const ring = coords[0] as [number, number][]
    const lon = ring.reduce((s, c) => s + c[0], 0) / ring.length
    const lat = ring.reduce((s, c) => s + c[1], 0) / ring.length

    map.flyTo({ center: [lon, lat], zoom: 11, duration: 1000 })
  }, [selectedZoneId, geojson])

  // Show home marker
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded || homeLat == null || homeLon == null) return

    // Remove existing marker
    if (homeMarkerRef.current) {
      homeMarkerRef.current.remove()
    }

    // Create a simple home marker element
    const el = document.createElement('div')
    el.style.cssText = 'width:14px;height:14px;background:#2563eb;border:2px solid #fff;border-radius:50%;box-shadow:0 1px 4px rgba(0,0,0,0.3);'

    const marker = new mapboxgl.Marker({ element: el })
      .setLngLat([homeLon, homeLat])
      .setPopup(new mapboxgl.Popup({ offset: 10 }).setText('Home'))
      .addTo(map)

    homeMarkerRef.current = marker

    return () => {
      marker.remove()
    }
  }, [homeLat, homeLon, mapLoaded])

  return <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
}

export default MapView
