import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getLeadPins,
  getLeadPinsGeoJSON,
  getLeadPinCallbacks,
  createLeadPin,
  updateLeadPin,
  deleteLeadPin,
  getLeadPinActivities,
  createLeadPinActivity,
} from '../api/client'
import type { LeadPinCreate, LeadPinUpdate, PinActivityCreate } from '../types/api'
import useAppStore from '../stores/appStore'

export function useLeadPins() {
  const mapBounds = useAppStore((s) => s.mapBounds)
  const showTeamPins = useAppStore((s) => s.showTeamPins)
  return useQuery({
    queryKey: ['lead-pins', mapBounds, showTeamPins],
    queryFn: () => getLeadPins(mapBounds ?? undefined, showTeamPins || undefined),
    staleTime: 30_000,
  })
}

export function useLeadPinsGeoJSON(disposition?: string) {
  const mapBounds = useAppStore((s) => s.mapBounds)
  const showTeamPins = useAppStore((s) => s.showTeamPins)
  return useQuery({
    queryKey: ['lead-pins-geojson', mapBounds, disposition, showTeamPins],
    queryFn: () => getLeadPinsGeoJSON(mapBounds ?? undefined, disposition, showTeamPins || undefined),
    staleTime: 30_000,
  })
}

export function useLeadPinCallbacks() {
  const showTeamPins = useAppStore((s) => s.showTeamPins)
  return useQuery({
    queryKey: ['lead-pin-callbacks', showTeamPins],
    queryFn: () => getLeadPinCallbacks(showTeamPins || undefined),
    staleTime: 60_000,
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
      queryClient.invalidateQueries({ queryKey: ['lead-pin-callbacks'] })
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
      queryClient.invalidateQueries({ queryKey: ['lead-pin-callbacks'] })
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
      queryClient.invalidateQueries({ queryKey: ['lead-pin-callbacks'] })
    },
  })
}

export function useCreatePinActivity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ pinId, data }: { pinId: string; data: PinActivityCreate }) =>
      createLeadPinActivity(pinId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead-pin-activities'] })
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
