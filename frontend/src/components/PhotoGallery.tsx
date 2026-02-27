import { useState, useRef } from 'react'
import useAppStore from '../stores/appStore'
import { usePinPhotos, useUploadPinPhoto, useDeletePinPhoto } from '../hooks/usePinPhotos'

async function compressImage(file: File): Promise<File> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      const MAX_DIM = 2048
      let { width, height } = img
      if (width > MAX_DIM || height > MAX_DIM) {
        const scale = MAX_DIM / Math.max(width, height)
        width = Math.round(width * scale)
        height = Math.round(height * scale)
      }
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      canvas.getContext('2d')!.drawImage(img, 0, 0, width, height)
      canvas.toBlob(
        (blob) => {
          if (!blob) return reject(new Error('Compression failed'))
          resolve(new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' }))
        },
        'image/jpeg',
        0.8,
      )
    }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Failed to load image')) }
    img.src = url
  })
}

interface PhotoGalleryProps {
  pinId: string
  isOwner: boolean
}

export default function PhotoGallery({ pinId, isOwner }: PhotoGalleryProps) {
  const darkMode = useAppStore((s) => s.darkMode)
  const { data, isLoading } = usePinPhotos(pinId)
  const uploadMutation = useUploadPinPhoto()
  const deleteMutation = useDeletePinPhoto()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'

  const photos = data?.photos ?? []
  const count = photos.length

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = '' // reset so the same file can be re-selected if needed
    setUploadError(null)
    try {
      const compressed = await compressImage(file)
      await uploadMutation.mutateAsync({ pinId, file: compressed })
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    }
  }

  function handleDelete(photoId: string) {
    if (!confirm('Delete this photo?')) return
    deleteMutation.mutate(photoId)
  }

  return (
    <div style={{ marginBottom: 16 }}>
      {/* Header with count and add button */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: textSecondary }}>
          Photos {count > 0 && `(${count}/10)`}
        </span>
        {isOwner && count < 10 && (
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: `1px solid ${darkMode ? '#16a34a44' : '#16a34a33'}`,
              background: darkMode ? '#0c2d1f' : '#f0fdf4',
              color: darkMode ? '#4ade80' : '#16a34a',
              fontSize: 12,
              fontWeight: 600,
              cursor: uploadMutation.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {uploadMutation.isPending ? 'Uploading...' : '+ Photo'}
          </button>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png"
          capture="environment"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
      </div>

      {/* Upload error */}
      {uploadError && (
        <div style={{
          marginBottom: 8, padding: 8, borderRadius: 6,
          background: darkMode ? '#2d0c0c' : '#fef2f2',
          color: '#ef4444', fontSize: 12,
        }}>
          {uploadError}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div style={{ fontSize: 12, color: textSecondary, textAlign: 'center', padding: 8 }}>
          Loading photos...
        </div>
      )}

      {/* Photo grid */}
      {photos.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 6,
        }}>
          {photos.map((photo) => (
            <div
              key={photo.id}
              style={{
                position: 'relative',
                paddingBottom: '100%', // square aspect ratio
                borderRadius: 8,
                overflow: 'hidden',
                border: `1px solid ${borderColor}`,
                cursor: 'pointer',
              }}
              onClick={() => setLightboxUrl(photo.url)}
            >
              <img
                src={photo.url}
                alt={photo.original_filename}
                style={{
                  position: 'absolute',
                  top: 0, left: 0, width: '100%', height: '100%',
                  objectFit: 'cover',
                }}
              />
              {isOwner && (
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(photo.id) }}
                  style={{
                    position: 'absolute', top: 4, right: 4,
                    width: 22, height: 22, borderRadius: '50%',
                    background: 'rgba(0,0,0,0.6)', color: '#fff',
                    border: 'none', cursor: 'pointer',
                    fontSize: 12, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  {'×'}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && photos.length === 0 && (
        <div style={{ fontSize: 12, color: textSecondary, textAlign: 'center', padding: 8 }}>
          No photos yet
        </div>
      )}

      {/* Lightbox overlay */}
      {lightboxUrl && (
        <div
          onClick={() => setLightboxUrl(null)}
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.85)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 10000,
            cursor: 'pointer',
          }}
        >
          <img
            src={lightboxUrl}
            alt="Full size"
            style={{ maxWidth: '90%', maxHeight: '90%', borderRadius: 8 }}
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setLightboxUrl(null)}
            style={{
              position: 'absolute', top: 16, right: 16,
              width: 36, height: 36, borderRadius: '50%',
              background: 'rgba(255,255,255,0.2)', color: '#fff',
              border: 'none', cursor: 'pointer', fontSize: 20,
            }}
          >
            {'×'}
          </button>
        </div>
      )}
    </div>
  )
}
