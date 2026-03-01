import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getLeadPin,
  getLeadPins,
  getLeadPinsGeoJSON,
  getLeadPinCallbacks,
  createLeadPin,
  updateLeadPin,
  deleteLeadPin,
  getLeadPinActivities,
  createLeadPinActivity,
  getProperty,
} from '../api/client'
import type { LeadPinCreate, LeadPinUpdate, PinActivityCreate, LeadPinResponse, PinActivityResponse } from '../types/api'
import { enqueueOfflineAction } from './useOfflineQueue'
import useAppStore from '../stores/appStore'

export function useLeadPinDetail(pinId: string | null) {
  return useQuery({
    queryKey: ['lead-pin', pinId],
    queryFn: () => getLeadPin(pinId!),
    enabled: !!pinId,
    staleTime: 30_000,
  })
}

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
    mutationFn: async (data: LeadPinCreate) => {
      if (!navigator.onLine) {
        await enqueueOfflineAction('create_pin', data)
        return {
          id: `pending_${Date.now()}`,
          roofer_account_id: '',
          lat: data.lat,
          lon: data.lon,
          address: data.address,
          disposition: data.disposition,
          notes: data.notes,
          lead_zone_id: data.lead_zone_id,
          property_id: data.property_id,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as LeadPinResponse
      }
      return createLeadPin(data)
    },
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
    mutationFn: async ({ pinId, data }: { pinId: string; data: LeadPinUpdate }) => {
      if (!navigator.onLine) {
        await enqueueOfflineAction('update_pin', { pinId, data })
        return { id: pinId, ...data } as LeadPinResponse
      }
      return updateLeadPin(pinId, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead-pins'] })
      queryClient.invalidateQueries({ queryKey: ['lead-pin'] })
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
      queryClient.invalidateQueries({ queryKey: ['lead-pin'] })
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
    mutationFn: async ({ pinId, data }: { pinId: string; data: PinActivityCreate }) => {
      if (!navigator.onLine) {
        await enqueueOfflineAction('create_activity', { pinId, data })
        return {
          id: `pending_${Date.now()}`,
          lead_pin_id: pinId,
          disposition: 'not_home',
          notes: data.notes,
          created_at: new Date().toISOString(),
        } as PinActivityResponse
      }
      return createLeadPinActivity(pinId, data)
    },
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

export function useProperty(propertyId: string | null | undefined) {
  return useQuery({
    queryKey: ['property', propertyId],
    queryFn: () => getProperty(propertyId!),
    enabled: !!propertyId,
    staleTime: 300_000, // property data changes rarely
  })
}
