import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPinPhotos, uploadPinPhoto, deletePinPhoto } from '../api/client'

export function usePinPhotos(pinId: string | null) {
  return useQuery({
    queryKey: ['pin-photos', pinId],
    queryFn: () => getPinPhotos(pinId!),
    enabled: !!pinId,
    staleTime: 30_000,
  })
}

export function useUploadPinPhoto() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ pinId, file }: { pinId: string; file: File }) =>
      uploadPinPhoto(pinId, file),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['pin-photos', variables.pinId] })
    },
  })
}

export function useDeletePinPhoto() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (photoId: string) => deletePinPhoto(photoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pin-photos'] })
    },
  })
}
