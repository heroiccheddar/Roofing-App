import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { createOrg, getOrg, joinOrg, leaveOrg } from '../api/client'
import type { OrgCreate, OrgJoin } from '../types/api'

export function useOrg() {
  return useQuery({
    queryKey: ['org'],
    queryFn: () => getOrg(),
    retry: false,
    staleTime: 120_000,
  })
}

export function useCreateOrg() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: OrgCreate) => createOrg(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org'] }) },
  })
}

export function useJoinOrg() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: OrgJoin) => joinOrg(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org'] }) },
  })
}

export function useLeaveOrg() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => leaveOrg(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org'] }) },
  })
}
