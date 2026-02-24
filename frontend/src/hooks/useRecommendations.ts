import { useQuery } from '@tanstack/react-query'
import { getRecommendations } from '../api/client'

function isValidCoord(lat: number | null, lon: number | null): boolean {
  return lat !== null && lon !== null &&
    lat >= -90 && lat <= 90 &&
    lon >= -180 && lon <= 180
}

export function useRecommendations(
  lat: number | null,
  lon: number | null,
  limit: number = 5,
  stormOnly: boolean = false,
) {
  return useQuery({
    queryKey: ['recommendations', lat, lon, limit, stormOnly],
    queryFn: () => getRecommendations(lat!, lon!, limit, stormOnly),
    enabled: isValidCoord(lat, lon),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })
}
