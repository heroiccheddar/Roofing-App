import { useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchRoofData } from '../api/client'

export function useFetchRoofData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (propertyId: string) => fetchRoofData(propertyId),
    onSuccess: (_data, propertyId) => {
      queryClient.invalidateQueries({ queryKey: ['property', propertyId] })
    },
  })
}
