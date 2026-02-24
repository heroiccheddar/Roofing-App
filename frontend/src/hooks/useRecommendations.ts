import { useQuery } from '@tanstack/react-query'
import { getRecommendations } from '../api/client'

export function useRecommendations(
  lat: number | null,
  lon: number | null,
  limit: number = 5,
  stormOnly: boolean = false,
) {
  return useQuery({
    queryKey: ['recommendations', lat, lon, limit, stormOnly],
    queryFn: () => getRecommendations(lat!, lon!, limit, stormOnly),
    enabled: lat !== null && lon !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })
}
