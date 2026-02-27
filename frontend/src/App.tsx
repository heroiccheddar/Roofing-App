import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LoadingSpinner from './components/LoadingSpinner'
import useAppStore from './stores/appStore'
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
  const isAuthenticated = !!token

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
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
