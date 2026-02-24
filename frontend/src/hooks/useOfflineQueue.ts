import { useState, useEffect, useRef, useCallback } from 'react'

const DB_NAME = 'roofiq_offline'
const STORE_NAME = 'pending_actions'
const DB_VERSION = 1

interface PendingAction {
  id: string
  type: string
  zoneId: string
  payload: unknown
  synced: boolean
  createdAt: number
}

type Executor = (action: PendingAction) => Promise<void>

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('synced', 'synced', { unique: false })
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function getPendingCount(db: IDBDatabase): Promise<number> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const index = store.index('synced')
    const request = index.count(IDBKeyRange.only(0))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export function useOfflineQueue() {
  const [isOnline, setIsOnline] = useState<boolean>(navigator.onLine)
  const [pendingCount, setPendingCount] = useState<number>(0)
  const dbRef = useRef<IDBDatabase | null>(null)
  const flushingRef = useRef<boolean>(false)

  // Initialize IndexedDB and load pending count
  useEffect(() => {
    openDB().then((db) => {
      dbRef.current = db
      return getPendingCount(db)
    }).then((count) => {
      setPendingCount(count)
    }).catch((err) => {
      console.warn('useOfflineQueue: failed to open IndexedDB:', err)
    })

    return () => {
      dbRef.current?.close()
      dbRef.current = null
    }
  }, [])

  // Track online/offline status
  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  const refreshCount = useCallback(async () => {
    if (!dbRef.current) return
    try {
      const count = await getPendingCount(dbRef.current)
      setPendingCount(count)
    } catch (err) {
      console.warn('useOfflineQueue: failed to refresh count:', err)
    }
  }, [])

  const enqueue = useCallback(async (type: string, zoneId: string, payload: unknown): Promise<void> => {
    const db = dbRef.current
    if (!db) {
      console.warn('useOfflineQueue: database not ready')
      return
    }

    const action: PendingAction = {
      id: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
      type,
      zoneId,
      payload,
      synced: false,
      createdAt: Date.now(),
    }

    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      const store = tx.objectStore(STORE_NAME)
      const request = store.add(action)
      request.onsuccess = () => {
        refreshCount()
        resolve()
      }
      request.onerror = () => reject(request.error)
    })
  }, [refreshCount])

  const flush = useCallback(async (executor: Executor): Promise<void> => {
    if (flushingRef.current) return
    const db = dbRef.current
    if (!db) return

    flushingRef.current = true

    try {
      // Fetch all unsynced actions
      const actions = await new Promise<PendingAction[]>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly')
        const store = tx.objectStore(STORE_NAME)
        const index = store.index('synced')
        const request = index.getAll(IDBKeyRange.only(0))
        request.onsuccess = () => resolve(request.result as PendingAction[])
        request.onerror = () => reject(request.error)
      })

      // Process each action
      for (const action of actions) {
        try {
          await executor(action)

          // Mark as synced
          await new Promise<void>((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readwrite')
            const store = tx.objectStore(STORE_NAME)
            const updated: PendingAction = { ...action, synced: true }
            const request = store.put(updated)
            request.onsuccess = () => resolve()
            request.onerror = () => reject(request.error)
          })
        } catch (err) {
          console.warn(`useOfflineQueue: failed to flush action ${action.id}:`, err)
          // Continue to next action rather than aborting the whole flush
        }
      }

      // Delete all synced records
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite')
        const store = tx.objectStore(STORE_NAME)
        const index = store.index('synced')
        const request = index.openCursor(IDBKeyRange.only(1))
        request.onsuccess = () => {
          const cursor = request.result
          if (cursor) {
            cursor.delete()
            cursor.continue()
          } else {
            resolve()
          }
        }
        request.onerror = () => reject(request.error)
      })
    } finally {
      flushingRef.current = false
      await refreshCount()
    }
  }, [refreshCount])

  return { isOnline, pendingCount, enqueue, flush }
}
