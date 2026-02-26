import { useQuery } from '@tanstack/react-query'
import { getPropertiesGeoJSON } from '../api/client'
import useAppStore from '../stores/appStore'

export function usePropertyPointsGeoJSON() {
  const mapBounds = useAppStore((s) => s.mapBounds)
  const mapZoom = useAppStore((s) => s.mapZoom)

  return useQuery({
    queryKey: ['property-points-geojson', mapBounds],
    queryFn: () => getPropertiesGeoJSON(mapBounds!),
    enabled: !!mapBounds && mapZoom >= 13,
    staleTime: 60_000,
  })
}
