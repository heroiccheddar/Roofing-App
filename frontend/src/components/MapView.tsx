import { useEffect, useRef, useState, useMemo } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { useZonesGeoJSON, useZoneTracts } from '../hooks/useZones'
import useAppStore from '../stores/appStore'
import { haversineKm } from '../utils/distance'

// Mapbox token from env
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || ''

// 21-stop color ramp matching panel scoreColor() palette (every 5 points)
// Matches: grays(0-15) → blues(20-25) → purples(30-45) → teals(50-65)
//          → yellows(70-80) → orange/red/rose/magenta(85-100)
const SCORE_COLOR_RAMP: mapboxgl.Expression = [
  'interpolate', ['linear'],
  ['get', 'composite_score'],
    0, '#64748b',   // slate-500
    5, '#5b6270',   // gray-steel
   10, '#475876',   // blue-gray
   15, '#3b4f7a',   // steel-blue
   20, '#1e40af',   // blue-800
   25, '#4338ca',   // indigo-700
   30, '#6d28d9',   // violet-700
   35, '#7e22ce',   // purple-700
   40, '#a21caf',   // fuchsia-700
   45, '#9d174d',   // pink-800
   50, '#0f766e',   // teal-700
   55, '#0e7490',   // cyan-700
   60, '#047857',   // emerald-700
   65, '#15803d',   // green-700
   70, '#4d7c0f',   // lime-700
   75, '#a16207',   // yellow-700
   80, '#b45309',   // amber-700
   85, '#c2410c',   // orange-700
   90, '#dc2626',   // red-600
   95, '#be123c',   // rose-700
  100, '#86198f',   // fuchsia-800
]

// Priority color ramp: gray → blue → yellow → orange → red
const PRIORITY_COLOR_RAMP: mapboxgl.Expression = [
  'interpolate', ['linear'],
  ['get', 'canvass_priority'],
    0, '#94a3b8',   // gray
   20, '#3b82f6',   // blue
   40, '#06b6d4',   // cyan
   60, '#eab308',   // yellow
   80, '#f97316',   // orange
  100, '#ef4444',   // red
]

function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const fittedRef = useRef(false)
  const [mapLoaded, setMapLoaded] = useState(false)
  const homeMarkerRef = useRef<mapboxgl.Marker | null>(null)
  const tractPopupRef = useRef<mapboxgl.Popup | null>(null)
  const { data: geojson } = useZonesGeoJSON()
  const selectedZoneId = useAppStore((s) => s.selectedZoneId)
  const setSelectedZoneId = useAppStore((s) => s.setSelectedZoneId)
  const setMapZoom = useAppStore((s) => s.setMapZoom)
  const setMapBounds = useAppStore((s) => s.setMapBounds)
  const homeLat = useAppStore((s) => s.homeLat)
  const homeLon = useAppStore((s) => s.homeLon)
  const maxDistanceMiles = useAppStore((s) => s.filters.maxDistanceMiles)
  const routeGeometry = useAppStore((s) => s.routeGeometry)
  const focusedTractId = useAppStore((s) => s.focusedTractId)
  const { data: tractsGeojson } = useZoneTracts(selectedZoneId)

  // Filter GeoJSON features by max distance from home
  const filteredGeojson = useMemo(() => {
    if (!geojson) return null
    if (homeLat == null || homeLon == null || maxDistanceMiles >= 200) return geojson
    const maxKm = maxDistanceMiles * 1.60934
    const filtered = geojson.features.filter((f: any) => {
      const lat = f.properties?.centroid_lat
      const lon = f.properties?.centroid_lon
      if (lat == null || lon == null) return true
      return haversineKm(homeLat, homeLon, lat, lon) <= maxKm
    })
    return { ...geojson, features: filtered }
  }, [geojson, homeLat, homeLon, maxDistanceMiles])

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return

    // Start at home location if available, otherwise fall back to Georgia
    const store = useAppStore.getState()
    const initLat = store.homeLat ?? 32.8
    const initLon = store.homeLon ?? -83.5

    const map = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/light-v11',
      center: [initLon, initLat],
      zoom: store.homeLat != null ? 8 : 5,
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
          'fill-color': SCORE_COLOR_RAMP as any,
          'fill-opacity': 0.55,
        },
      })

      // Outline layer — same gradient, slightly darker via opacity
      map.addLayer({
        id: 'zones-outline',
        type: 'line',
        source: 'zones',
        paint: {
          'line-color': SCORE_COLOR_RAMP as any,
          'line-width': 2,
          'line-opacity': 0.8,
        },
      })

      // Score labels inside each hex tile (visible at zoom >= 9)
      map.addLayer({
        id: 'zones-labels',
        type: 'symbol',
        source: 'zones',
        layout: {
          'text-field': ['to-string', ['round', ['get', 'composite_score']]],
          'text-size': [
            'interpolate', ['linear'], ['zoom'],
            9, 9,
            12, 13,
          ],
          'text-allow-overlap': true,
          'text-ignore-placement': true,
        },
        paint: {
          'text-color': '#0f172a',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1.5,
        },
        minzoom: 9,
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

      // Census tract overlay source + layers (visible at zoom >= 12)
      map.addSource('tracts', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      map.addLayer({
        id: 'tracts-fill',
        type: 'fill',
        source: 'tracts',
        paint: {
          'fill-color': PRIORITY_COLOR_RAMP as any,
          'fill-opacity': 0.3,
        },
        minzoom: 12,
      })

      map.addLayer({
        id: 'tracts-outline',
        type: 'line',
        source: 'tracts',
        paint: {
          'line-color': '#334155',
          'line-width': 1,
          'line-opacity': 0.6,
        },
        minzoom: 12,
      })

      // Focused tract highlight (controlled by focusedTractId store)
      map.addLayer({
        id: 'tracts-focused',
        type: 'line',
        source: 'tracts',
        paint: {
          'line-color': '#2563eb',
          'line-width': 3.5,
          'line-opacity': 1,
        },
        filter: ['==', ['get', 'geoid'], ''],
        minzoom: 12,
      })

      map.addLayer({
        id: 'tracts-labels',
        type: 'symbol',
        source: 'tracts',
        layout: {
          'text-field': ['concat', ['to-string', ['round', ['get', 'canvass_priority']]], '%'],
          'text-size': 11,
          'text-allow-overlap': false,
        },
        paint: {
          'text-color': '#0f172a',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1.5,
        },
        minzoom: 13,
      })

      // Route polyline source + layer
      map.addSource('route', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        paint: {
          'line-color': '#2563eb',
          'line-width': 4,
          'line-dasharray': [2, 1],
          'line-opacity': 0.8,
        },
      })

      // Tract hover popup
      map.on('mouseenter', 'tracts-fill', (e) => {
        map.getCanvas().style.cursor = 'crosshair'
        if (e.features && e.features.length > 0) {
          const props = e.features[0].properties || {}
          const html = `
            <div style="font-size:12px;line-height:1.4">
              <strong>Priority: ${props.canvass_priority}%</strong><br/>
              Owner-Occupied: ${props.owner_occupied_pct != null ? props.owner_occupied_pct + '%' : 'N/A'}<br/>
              Single Family: ${props.single_family_pct != null ? props.single_family_pct + '%' : 'N/A'}<br/>
              Pre-1980: ${props.pct_built_before_1980 != null ? props.pct_built_before_1980 + '%' : 'N/A'}<br/>
              Home Value: ${props.median_home_value != null ? '$' + Number(props.median_home_value).toLocaleString() : 'N/A'}<br/>
              Era: ${props.dominant_decade || 'N/A'}
            </div>
          `
          tractPopupRef.current = new mapboxgl.Popup({ closeButton: false, closeOnClick: false, offset: 10 })
            .setLngLat(e.lngLat)
            .setHTML(html)
            .addTo(map)
        }
      })
      map.on('mousemove', 'tracts-fill', (e) => {
        if (tractPopupRef.current) {
          tractPopupRef.current.setLngLat(e.lngLat)
        }
      })
      map.on('mouseleave', 'tracts-fill', () => {
        map.getCanvas().style.cursor = ''
        if (tractPopupRef.current) {
          tractPopupRef.current.remove()
          tractPopupRef.current = null
        }
      })

      // Track zoom and viewport changes
      const updateBounds = () => {
        const b = map.getBounds()
        if (!b) return
        setMapBounds([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
        setMapZoom(map.getZoom())
      }
      let boundsTimer: ReturnType<typeof setTimeout> | null = null
      map.on('moveend', () => {
        if (boundsTimer) clearTimeout(boundsTimer)
        boundsTimer = setTimeout(updateBounds, 300)
      })
      // Set initial bounds
      updateBounds()

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

      // Fit to 60-mile radius around home immediately on load
      if (store.homeLat != null && store.homeLon != null) {
        const radiusDeg = 75 / 69.0
        const lonSpread = radiusDeg / Math.cos((store.homeLat * Math.PI) / 180)
        map.fitBounds(
          [[store.homeLon - lonSpread, store.homeLat - radiusDeg],
           [store.homeLon + lonSpread, store.homeLat + radiusDeg]],
          { padding: 20, duration: 0 }
        )
      }

      setMapLoaded(true)
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [setSelectedZoneId, setMapZoom])

  // Update GeoJSON data when it changes (filtered by distance)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded || !filteredGeojson) return

    const source = map.getSource('zones') as mapboxgl.GeoJSONSource | undefined
    if (source) {
      source.setData(filteredGeojson as any)
    }
  }, [filteredGeojson, mapLoaded])

  // Fit bounds once on first load — only when no home location is set
  // (if home is set, the map already initialized centered on it)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded || fittedRef.current) return
    if (!filteredGeojson?.features?.length) return

    fittedRef.current = true

    // Skip fitBounds when we already centered on home
    if (useAppStore.getState().homeLat != null) return

    const bounds = new mapboxgl.LngLatBounds()
    const sample = filteredGeojson.features.slice(0, 50)
    for (const feature of sample) {
      const coords = (feature.geometry as any).coordinates
      if (!coords) continue
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
  }, [filteredGeojson, mapLoaded])

  // Fit map to 60-mile radius around home on load and when home changes
  const homeFittedRef = useRef(false)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded || homeLat == null || homeLon == null) return
    const radiusDeg = 75 / 69.0
    const lonSpread = radiusDeg / Math.cos((homeLat * Math.PI) / 180)
    const animate = homeFittedRef.current // skip animation on first fit
    homeFittedRef.current = true
    map.fitBounds(
      [[homeLon - lonSpread, homeLat - radiusDeg],
       [homeLon + lonSpread, homeLat + radiusDeg]],
      { padding: 20, duration: animate ? 1000 : 0 }
    )
  }, [homeLat, homeLon, mapLoaded])

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

  // Update tract overlay when tracts data changes
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return

    const source = map.getSource('tracts') as mapboxgl.GeoJSONSource | undefined
    if (!source) return

    if (tractsGeojson && selectedZoneId) {
      source.setData(tractsGeojson as any)
    } else {
      source.setData({ type: 'FeatureCollection', features: [] })
    }
  }, [tractsGeojson, selectedZoneId, mapLoaded])

  // Highlight focused tract
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return
    map.setFilter('tracts-focused', ['==', ['get', 'geoid'], focusedTractId || ''])
  }, [focusedTractId, mapLoaded])

  // Update route polyline when routeGeometry changes
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return
    const source = map.getSource('route') as mapboxgl.GeoJSONSource | undefined
    if (!source) return

    if (routeGeometry) {
      source.setData({
        type: 'Feature',
        geometry: routeGeometry,
        properties: {},
      } as any)
    } else {
      source.setData({ type: 'FeatureCollection', features: [] })
    }
  }, [routeGeometry, mapLoaded])

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
