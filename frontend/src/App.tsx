import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LoadingSpinner from './components/LoadingSpinner'
import useAppStore from './stores/appStore'
import { DispositionPicker } from './components/LeadPinPanel'
import { useCreateLeadPin } from './hooks/useLeadPins'
import type { LeadPinDisposition } from './types/api'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Login = lazy(() => import('./pages/Login'))
const ZoneDetail = lazy(() => import('./pages/ZoneDetail'))

function PendingPinCreator() {
  const pendingPinLocation = useAppStore((s) => s.pendingPinLocation)
  const setPendingPinLocation = useAppStore((s) => s.setPendingPinLocation)
  const setIsPinDropMode = useAppStore((s) => s.setIsPinDropMode)
  const createPin = useCreateLeadPin()

  if (!pendingPinLocation) return null

  const handleConfirm = (disposition: LeadPinDisposition, notes: string) => {
    createPin.mutate(
      {
        lat: pendingPinLocation.lat,
        lon: pendingPinLocation.lon,
        disposition,
        notes: notes || undefined,
        address: pendingPinLocation.address,
        property_id: pendingPinLocation.property_id,
        lead_zone_id: pendingPinLocation.lead_zone_id,
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
