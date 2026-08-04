/**
 * TchueKAM Image Studio v2 — Project Store
 */

import { atom } from 'nanostores'
import { createDefaultProject } from '../core/models'
import type { StudioProjectData, StudioProjectMetadata } from '../core/types'

export const $activeProject = atom<StudioProjectData>(createDefaultProject())
export const $recentProjects = atom<StudioProjectMetadata[]>([])
export const $isSaving = atom<boolean>(false)
export const $isDirty = atom<boolean>(false)

export function updateProject(updater: (prev: StudioProjectData) => StudioProjectData) {
  const current = $activeProject.get()
  const updated = updater(current)
  $activeProject.set(updated)
  $isDirty.set(true)
}

export function setProject(project: StudioProjectData) {
  $activeProject.set(project)
  $isDirty.set(false)
}
