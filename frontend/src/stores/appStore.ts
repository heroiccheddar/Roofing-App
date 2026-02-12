import { create } from 'zustand'
import { clearAuthToken, getAuthToken } from '../api/client'

interface User {
  id: string
  email: string
  companyName: string
}

interface AppState {
  user: User | null
  token: string | null
  selectedZoneId: string | null
  mapBounds: [number, number, number, number] | null
  homeLat: number | null
  homeLon: number | null
  filters: {
    minScore: number
    maxDistanceKm: number
    leadType: 'storm' | 'roof_age' | 'all'
    dateRange: [string, string] | null
  }
  setUser: (user: User | null) => void
  setToken: (token: string | null) => void
  setSelectedZoneId: (zoneId: string | null) => void
  setMapBounds: (bounds: [number, number, number, number] | null) => void
  setHome: (lat: number, lon: number) => void
  setFilters: (filters: Partial<AppState['filters']>) => void
  logout: () => void
}

const useAppStore = create<AppState>((set) => ({
  // State — restore token from sessionStorage if available
  user: null,
  token: getAuthToken(),
  selectedZoneId: null,
  mapBounds: null,
  homeLat: null,
  homeLon: null,
  filters: {
    minScore: 50,
    maxDistanceKm: 200,
    leadType: 'all',
    dateRange: null,
  },

  // Actions
  setUser: (user) => set({ user }),
  setToken: (token) => set({ token }),
  setSelectedZoneId: (zoneId) => set({ selectedZoneId: zoneId }),
  setMapBounds: (bounds) => set({ mapBounds: bounds }),
  setHome: (lat, lon) => set({ homeLat: lat, homeLon: lon }),
  setFilters: (newFilters) =>
    set((state) => ({
      filters: { ...state.filters, ...newFilters },
    })),
  logout: () => {
    clearAuthToken()
    set({ user: null, token: null, selectedZoneId: null })
  },
}))

export default useAppStore
