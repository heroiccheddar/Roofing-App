import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { useZonesGeoJSON } from '../hooks/useZones'
import useAppStore from '../stores/appStore'

// Mapbox token from env
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || ''

// Score band colors
const BAND_COLORS: Record<string, string> = {
  hot: '#EF4444',    // Red
  warm: '#F97316',   // Orange
  cool: '#EAB308',   // Yellow
  skip: '#6366F1',   // Indigo (visible on light basemap)
}

function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const fittedRef = useRef(false)
  const { data: geojson } = useZonesGeoJSON()
  const selectedZoneId = useAppStore((s) => s.selectedZoneId)
  const setSelectedZoneId = useAppStore((s) => s.setSelectedZoneId)

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

      // Fill layer for zone polygons
      map.addLayer({
        id: 'zones-fill',
        type: 'fill',
        source: 'zones',
        paint: {
          'fill-color': [
            'match', ['get', 'score_band'],
            'hot', BAND_COLORS.hot,
            'warm', BAND_COLORS.warm,
            'cool', BAND_COLORS.cool,
            'skip', BAND_COLORS.skip,
            '#6366F1', // default
          ],
          'fill-opacity': 0.55,
        },
      })

      // Outline layer
      map.addLayer({
        id: 'zones-outline',
        type: 'line',
        source: 'zones',
        paint: {
          'line-color': [
            'match', ['get', 'score_band'],
            'hot', BAND_COLORS.hot,
            'warm', BAND_COLORS.warm,
            'cool', BAND_COLORS.cool,
            'skip', BAND_COLORS.skip,
            '#6366F1',
          ],
          'line-width': 3,
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
    if (!map || !geojson) return

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
  }, [geojson])

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

  return <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
}

export default MapView
