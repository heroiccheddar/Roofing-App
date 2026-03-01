import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LoadingSpinner from './components/LoadingSpinner'
import useAppStore from './stores/appStore'
import { getAccount } from './api/client'
import { DispositionPicker } from './components/LeadPinPanel'
import { useCreateLeadPin } from './hooks/useLeadPins'
import type { LeadPinDisposition } from './types/api'

function lazyRetry(factory: () => Promise<{ default: React.ComponentType }>) {
  return lazy(() =>
    factory().catch(() => {
      // Stale chunk after deploy — reload once to pick up new assets
      const key = 'chunk-reload'
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, '1')
        window.location.reload()
      }
      sessionStorage.removeItem(key)
      return factory()
    }),
  )
}

const Dashboard = lazyRetry(() => import('./pages/Dashboard'))
const Login = lazyRetry(() => import('./pages/Login'))
const ZoneDetail = lazyRetry(() => import('./pages/ZoneDetail'))
const Settings = lazyRetry(() => import('./pages/Settings'))
const PipelineBoard = lazyRetry(() => import('./pages/PipelineBoard'))
const CalendarView = lazyRetry(() => import('./pages/CalendarView'))

function PendingPinCreator() {
  const pendingPinLocation = useAppStore((s) => s.pendingPinLocation)
  const setPendingPinLocation = useAppStore((s) => s.setPendingPinLocation)
  const setIsPinDropMode = useAppStore((s) => s.setIsPinDropMode)
  const createPin = useCreateLeadPin()

  if (!pendingPinLocation) return null

  const handleConfirm = (disposition: LeadPinDisposition, notes: string, callbackDate?: string) => {
    createPin.mutate(
      {
        lat: pendingPinLocation.lat,
        lon: pendingPinLocation.lon,
        disposition,
        notes: notes || undefined,
        address: pendingPinLocation.address,
        property_id: pendingPinLocation.property_id,
        lead_zone_id: pendingPinLocation.lead_zone_id,
        callback_date: callbackDate,
      },
      {
        onSuccess: () => {
          setPendingPinLocation(null)
          setIsPinDropMode(false)
        },
      },
    )
  }

  return (
    <DispositionPicker
      title="New Lead Pin"
      onConfirm={handleConfirm}
      onCancel={() => setPendingPinLocation(null)}
      isLoading={createPin.isPending}
    />
  )
}

function App() {
  const token = useAppStore((state) => state.token)
  const user = useAppStore((s) => s.user)
  const setUser = useAppStore((s) => s.setUser)
  const setHome = useAppStore((s) => s.setHome)
  const isAuthenticated = !!token

  // Restore user profile on page refresh (token persists but user object doesn't)
  useEffect(() => {
    if (token && !user) {
      getAccount()
        .then((profile) => {
          setUser({ id: profile.id, email: profile.email, companyName: profile.company_name })
          if (profile.service_area_lat != null && profile.service_area_lon != null) {
            setHome(profile.service_area_lat, profile.service_area_lon)
          }
        })
        .catch(() => {
          // Token expired or invalid — force re-login
          useAppStore.getState().logout()
        })
    }
  }, [token, user, setUser, setHome])

  return (
    <BrowserRouter>
      <PendingPinCreator />
      <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          <Route path="/login" element={
            isAuthenticated ? <Navigate to="/" /> : <Login />
          } />
          <Route path="/" element={
            isAuthenticated ? <Dashboard /> : <Navigate to="/login" />
          } />
          <Route path="/zones/:id" element={
            isAuthenticated ? <ZoneDetail /> : <Navigate to="/login" />
          } />
          <Route path="/settings" element={
            isAuthenticated ? <Settings /> : <Navigate to="/login" />
          } />
          <Route path="/pipeline" element={
            isAuthenticated ? <PipelineBoard /> : <Navigate to="/login" />
          } />
          <Route path="/calendar" element={
            isAuthenticated ? <CalendarView /> : <Navigate to="/login" />
          } />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
