import { useState, useEffect, useCallback } from 'react'

interface GeolocationState {
  lat: number | null
  lon: number | null
  accuracy: number | null
  error: string | null
  loading: boolean
  refresh: () => void
}

export function useGeolocation(options?: PositionOptions): GeolocationState {
  const [state, setState] = useState<Omit<GeolocationState, 'refresh'>>({
    lat: null, lon: null, accuracy: null, error: null, loading: true,
  })

  const getPosition = useCallback(() => {
    if (!navigator.geolocation) {
      setState(prev => ({ ...prev, error: 'Geolocation not supported', loading: false }))
      return
    }
    setState(prev => ({ ...prev, loading: true }))
    navigator.geolocation.getCurrentPosition(
      (pos) => setState({
        lat: pos.coords.latitude, lon: pos.coords.longitude,
        accuracy: pos.coords.accuracy, error: null, loading: false,
      }),
      (err) => setState(prev => ({ ...prev, error: err.message, loading: false })),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000, ...options },
    )
  }, [])

  useEffect(() => { getPosition() }, [getPosition])

  return { ...state, refresh: getPosition }
}
