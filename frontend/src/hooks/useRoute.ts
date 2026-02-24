import { useMutation } from '@tanstack/react-query'
import { planRoute } from '../api/client'
import type { RouteRequest, RouteResponse } from '../types/api'

export function useRoutePlanner() {
  return useMutation<RouteResponse, Error, RouteRequest>({
    mutationFn: planRoute,
  })
}
