import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LoadingSpinner from './components/LoadingSpinner'
import useAppStore from './stores/appStore'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Login = lazy(() => import('./pages/Login'))
const ZoneDetail = lazy(() => import('./pages/ZoneDetail'))

function App() {
  const token = useAppStore((state) => state.token)
  const isAuthenticated = !!token

  return (
    <BrowserRouter>
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
