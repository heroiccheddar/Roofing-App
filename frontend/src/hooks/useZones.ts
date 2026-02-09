import { useQuery } from '@tanstack/react-query'
import { getZones, getZone, getZonesGeoJSON } from '../api/client'
import type { ZoneListParams } from '../types/api'
import useAppStore from '../stores/appStore'

export function useZoneList(params?: Partial<ZoneListParams>) {
  const minScore = useAppStore((s) => s.filters.minScore)

  return useQuery({
    queryKey: ['zones', { ...params, min_score: minScore }],
    queryFn: () => getZones({ min_score: minScore, ...params }),
    staleTime: 30_000,
  })
}

export function useZoneDetail(zoneId: string | null) {
  return useQuery({
    queryKey: ['zone', zoneId],
    queryFn: () => getZone(zoneId!),
    enabled: !!zoneId,
    staleTime: 15_000,
  })
}

export function useZonesGeoJSON() {
  const minScore = useAppStore((s) => s.filters.minScore)

  return useQuery({
    queryKey: ['zones-geojson', minScore],
    queryFn: () => getZonesGeoJSON(undefined, minScore),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}

export default useZoneList
