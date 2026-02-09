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
  skip: '#9CA3AF',   // Gray
}

function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const { data: geojson } = useZonesGeoJSON()
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
            '#9CA3AF', // default
          ],
          'fill-opacity': 0.4,
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
            '#6B7280',
          ],
          'line-width': 2,
        },
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

  // Update GeoJSON data when it changes
  useEffect(() => {
    const map = mapRef.current
    if (!map || !geojson) return

    const source = map.getSource('zones') as mapboxgl.GeoJSONSource | undefined
    if (source) {
      source.setData(geojson as any)
    }
  }, [geojson])

  return <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
}

export default MapView
