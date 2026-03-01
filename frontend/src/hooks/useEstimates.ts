import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getEstimates,
  createEstimate,
  updateEstimate,
  deleteEstimate,
} from '../api/client'
import type { EstimateCreate, EstimateUpdate } from '../types/api'

export function useEstimates(pinId: string | null) {
  return useQuery({
    queryKey: ['estimates', pinId],
    queryFn: () => getEstimates(pinId!),
    enabled: !!pinId,
    staleTime: 30_000,
  })
}

export function useCreateEstimate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: EstimateCreate) => createEstimate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['estimates'] })
    },
  })
}

export function useUpdateEstimate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ estimateId, data }: { estimateId: string; data: EstimateUpdate }) =>
      updateEstimate(estimateId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['estimates'] })
    },
  })
}

export function useDeleteEstimate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (estimateId: string) => deleteEstimate(estimateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['estimates'] })
    },
  })
}
