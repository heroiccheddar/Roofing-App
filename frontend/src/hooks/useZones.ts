import { useQuery } from '@tanstack/react-query'
import { getZones, getZone, getZonesGeoJSON, getZoneTracts, getTractProperties } from '../api/client'
import type { ZoneListParams } from '../types/api'
import useAppStore from '../stores/appStore'

export function useZoneList(params?: Partial<ZoneListParams>) {
  const minScore = useAppStore((s) => s.filters.minScore)
  const leadType = useAppStore((s) => s.filters.leadType)
  const lead_type = leadType === 'all' ? undefined : leadType

  return useQuery({
    queryKey: ['zones', { ...params, min_score: minScore, lead_type }],
    queryFn: () => getZones({ min_score: minScore, lead_type, sort_by: 'score', page_size: 100, ...params }),
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
  const leadType = useAppStore((s) => s.filters.leadType)
  const lead_type = leadType === 'all' ? undefined : leadType
  const mapBounds = useAppStore((s) => s.mapBounds)

  return useQuery({
    queryKey: ['zones-geojson', minScore, lead_type, mapBounds],
    queryFn: () => getZonesGeoJSON(mapBounds ?? undefined, minScore, lead_type),
    enabled: !!mapBounds,
    staleTime: 30_000,
  })
}

export function useZoneTracts(zoneId: string | null) {
  return useQuery({
    queryKey: ['zone-tracts', zoneId],
    queryFn: () => getZoneTracts(zoneId!),
    enabled: !!zoneId,
    staleTime: 60_000,
  })
}

export function useTractProperties(zoneId: string | null, tractGeoid: string | null) {
  return useQuery({
    queryKey: ['tract-properties', zoneId, tractGeoid],
    queryFn: () => getTractProperties(zoneId!, tractGeoid!),
    enabled: !!zoneId && !!tractGeoid,
    staleTime: 120_000,
  })
}

export default useZoneList
