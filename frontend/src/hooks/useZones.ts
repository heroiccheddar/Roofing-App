import { useQuery } from '@tanstack/react-query'

interface UseZonesOptions {
  bbox?: [number, number, number, number]
  minScore?: number
  startDate?: string
  endDate?: string
}

function useZones(options: UseZonesOptions = {}) {
  // TODO: Implement in WP 4.1
  // - Fetch lead zones from API with filters
  // - Handle loading/error states
  // - Cache results with React Query
  // - Refetch on filter changes
  // - Return zones as GeoJSON

  return useQuery({
    queryKey: ['zones', options],
    queryFn: async () => {
      // API call placeholder
      return []
    },
    enabled: false, // Disabled until API is implemented
  })
}

export default useZones
