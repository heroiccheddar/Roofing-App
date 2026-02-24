import { useState, useEffect } from 'react'

export function useServiceWorker() {
  const [isInstalled, setIsInstalled] = useState(false)
  const [needsUpdate, setNeedsUpdate] = useState(false)
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null)

  useEffect(() => {
    if (!('serviceWorker' in navigator)) return
    navigator.serviceWorker.getRegistration().then((reg) => {
      if (reg) {
        setRegistration(reg)
        setIsInstalled(!!reg.active)
        reg.addEventListener('updatefound', () => {
          const newWorker = reg.installing
          if (newWorker) {
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                setNeedsUpdate(true)
              }
            })
          }
        })
      }
    })
  }, [])

  const update = () => {
    if (registration?.waiting) {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' })
      window.location.reload()
    }
  }

  return { isInstalled, needsUpdate, update }
}
