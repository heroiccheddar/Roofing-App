import { useQuery } from '@tanstack/react-query'
import { getAnalyticsDashboard } from '../api/client'
import type { LeaderboardPeriod } from '../types/api'

export function useAnalyticsDashboard(period: LeaderboardPeriod) {
  return useQuery({
    queryKey: ['analytics', period],
    queryFn: () => getAnalyticsDashboard(period),
    staleTime: 120_000,
  })
}
