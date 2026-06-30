import { atom } from 'nanostores'

export interface ComparisonRequest {
  messageText: string
  messageId: string
}

export const $comparisonRequest = atom<ComparisonRequest | null>(null)

export function openComparison(request: ComparisonRequest): void {
  $comparisonRequest.set(request)
}

export function closeComparison(): void {
  $comparisonRequest.set(null)
}
