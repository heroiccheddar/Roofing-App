import { useQuery } from '@tanstack/react-query'
import { getLeaderboard } from '../api/client'
import type { LeaderboardPeriod } from '../types/api'

export function useLeaderboard(period: LeaderboardPeriod = 'this_week') {
  return useQuery({
    queryKey: ['leaderboard', period],
    queryFn: () => getLeaderboard(period),
    staleTime: 120_000,
  })
}
