import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getLeadPins,
  getLeadPinsGeoJSON,
  createLeadPin,
  updateLeadPin,
  deleteLeadPin,
  getLeadPinActivities,
} from '../api/client'
import type { LeadPinCreate, LeadPinUpdate } from '../types/api'
import useAppStore from '../stores/appStore'

export function useLeadPins() {
  const mapBounds = useAppStore((s) => s.mapBounds)
  return useQuery({
    queryKey: ['lead-pins', mapBounds],
    queryFn: () => getLeadPins(mapBounds ?? undefined),
    staleTime: 30_000,
  })
}

export function useLeadPinsGeoJSON(disposition?: string) {
  const mapBounds = useAppStore((s) => s.mapBounds)
  return useQuery({
    queryKey: ['lead-pins-geojson', mapBounds, disposition],
    queryFn: () => getLeadPinsGeoJSON(mapBounds ?? undefined, disposition),
    staleTime: 30_000,
  })
}

export function useCreateLeadPin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: LeadPinCreate) => createLeadPin(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead-pins'] })
      queryClient.invalidateQueries({ queryKey: ['lead-pins-geojson'] })
      queryClient.invalidateQueries({ queryKey: ['property-points-geojson'] })
    },
  })
}

export function useUpdateLeadPin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ pinId, data }: { pinId: string; data: LeadPinUpdate }) =>
      updateLeadPin(pinId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead-pins'] })
      queryClient.invalidateQueries({ queryKey: ['lead-pins-geojson'] })
      queryClient.invalidateQueries({ queryKey: ['lead-pin-activities'] })
      queryClient.invalidateQueries({ queryKey: ['property-points-geojson'] })
    },
  })
}

export function useDeleteLeadPin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (pinId: string) => deleteLeadPin(pinId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead-pins'] })
      queryClient.invalidateQueries({ queryKey: ['lead-pins-geojson'] })
      queryClient.invalidateQueries({ queryKey: ['property-points-geojson'] })
    },
  })
}

export function useLeadPinActivities(pinId: string | null) {
  return useQuery({
    queryKey: ['lead-pin-activities', pinId],
    queryFn: () => getLeadPinActivities(pinId!),
    enabled: !!pinId,
    staleTime: 30_000,
  })
}
