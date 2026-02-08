import { create } from 'zustand'

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
  filters: {
    minScore: number
    dateRange: [string, string] | null
  }
  setUser: (user: User | null) => void
  setToken: (token: string | null) => void
  setSelectedZoneId: (zoneId: string | null) => void
  setMapBounds: (bounds: [number, number, number, number] | null) => void
  setFilters: (filters: Partial<AppState['filters']>) => void
}

const useAppStore = create<AppState>((set) => ({
  // State
  user: null,
  token: null,
  selectedZoneId: null,
  mapBounds: null,
  filters: {
    minScore: 50,
    dateRange: null,
  },

  // Actions
  setUser: (user) => set({ user }),
  setToken: (token) => set({ token }),
  setSelectedZoneId: (zoneId) => set({ selectedZoneId: zoneId }),
  setMapBounds: (bounds) => set({ mapBounds: bounds }),
  setFilters: (newFilters) =>
    set((state) => ({
      filters: { ...state.filters, ...newFilters },
    })),
}))

export default useAppStore
