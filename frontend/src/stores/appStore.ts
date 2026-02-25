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
    maxDistanceMiles: number
    leadType: 'standard' | 'storm_boosted' | 'all'
    dateRange: [string, string] | null
  }
  listViewMode: 'cards' | 'table'
  sortBy: 'score' | 'nearest' | 'route'
  activeCanvassSessionId: string | null
  mapZoom: number
  darkMode: boolean
  routeZoneIds: string[]
  routeGeometry: any | null
  isOffline: boolean
  pendingQueueCount: number
  focusedTractId: string | null
  selectedLeadPinId: string | null
  isPinDropMode: boolean
  pendingPinLocation: { lat: number; lon: number } | null
  setUser: (user: User | null) => void
  setToken: (token: string | null) => void
  setSelectedZoneId: (zoneId: string | null) => void
  setMapBounds: (bounds: [number, number, number, number] | null) => void
  setHome: (lat: number, lon: number) => void
  setFilters: (filters: Partial<AppState['filters']>) => void
  setListViewMode: (mode: 'cards' | 'table') => void
  setSortBy: (sortBy: 'score' | 'nearest' | 'route') => void
  setActiveCanvassSessionId: (id: string | null) => void
  setMapZoom: (zoom: number) => void
  setDarkMode: (dark: boolean) => void
  setRouteZoneIds: (ids: string[]) => void
  setRouteGeometry: (geom: any | null) => void
  setIsOffline: (offline: boolean) => void
  setPendingQueueCount: (count: number) => void
  toggleZoneInRoute: (zoneId: string) => void
  clearRoute: () => void
  setFocusedTractId: (geoid: string | null) => void
  setSelectedLeadPinId: (id: string | null) => void
  setIsPinDropMode: (mode: boolean) => void
  setPendingPinLocation: (loc: { lat: number; lon: number } | null) => void
  logout: () => void
}

const useAppStore = create<AppState>((set) => ({
  // State — restore token from sessionStorage if available
  user: null,
  token: getAuthToken(),
  selectedZoneId: null,
  mapBounds: null,
  homeLat: (() => { const v = sessionStorage.getItem('roofiq_home_lat'); return v ? parseFloat(v) : null })(),
  homeLon: (() => { const v = sessionStorage.getItem('roofiq_home_lon'); return v ? parseFloat(v) : null })(),
  filters: {
    minScore: 50,
    maxDistanceMiles: 75,
    leadType: 'all',
    dateRange: null,
  },
  listViewMode: 'cards',
  sortBy: 'score',
  activeCanvassSessionId: null,
  mapZoom: 5,
  darkMode: localStorage.getItem('roofiq_dark_mode') === 'true',
  routeZoneIds: [],
  routeGeometry: null,
  isOffline: typeof navigator !== 'undefined' ? !navigator.onLine : false,
  pendingQueueCount: 0,
  focusedTractId: null,
  selectedLeadPinId: null,
  isPinDropMode: false,
  pendingPinLocation: null,

  // Actions
  setUser: (user) => set({ user }),
  setToken: (token) => set({ token }),
  setSelectedZoneId: (zoneId) => set({ selectedZoneId: zoneId }),
  setMapBounds: (bounds) => set({ mapBounds: bounds }),
  setHome: (lat, lon) => {
    sessionStorage.setItem('roofiq_home_lat', String(lat))
    sessionStorage.setItem('roofiq_home_lon', String(lon))
    set({ homeLat: lat, homeLon: lon })
  },
  setFilters: (newFilters) =>
    set((state) => ({
      filters: { ...state.filters, ...newFilters },
    })),
  setListViewMode: (mode) => set({ listViewMode: mode }),
  setSortBy: (sortBy) => set({ sortBy }),
  setActiveCanvassSessionId: (id) => set({ activeCanvassSessionId: id }),
  setMapZoom: (zoom) => set({ mapZoom: zoom }),
  setDarkMode: (dark) => set({ darkMode: dark }),
  setRouteZoneIds: (ids) => set({ routeZoneIds: ids }),
  setRouteGeometry: (geom) => set({ routeGeometry: geom }),
  setIsOffline: (offline) => set({ isOffline: offline }),
  setPendingQueueCount: (count) => set({ pendingQueueCount: count }),
  toggleZoneInRoute: (zoneId) =>
    set((state) => {
      const ids = state.routeZoneIds.includes(zoneId)
        ? state.routeZoneIds.filter((id) => id !== zoneId)
        : [...state.routeZoneIds, zoneId].slice(0, 10)
      return { routeZoneIds: ids }
    }),
  clearRoute: () => set({ routeZoneIds: [], routeGeometry: null }),
  setFocusedTractId: (geoid) => set({ focusedTractId: geoid }),
  setSelectedLeadPinId: (id) => set({ selectedLeadPinId: id }),
  setIsPinDropMode: (mode) => set({ isPinDropMode: mode }),
  setPendingPinLocation: (loc) => set({ pendingPinLocation: loc }),
  logout: () => {
    clearAuthToken()
    sessionStorage.removeItem('roofiq_home_lat')
    sessionStorage.removeItem('roofiq_home_lon')
    set({ user: null, token: null, selectedZoneId: null, homeLat: null, homeLon: null, selectedLeadPinId: null, isPinDropMode: false, pendingPinLocation: null })
  },
}))

export default useAppStore
