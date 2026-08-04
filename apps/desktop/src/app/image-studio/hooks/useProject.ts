/**
 * TchueKAM Image Studio v2 — useProject Hook
 */

import { useStore } from '@nanostores/react'
import { $activeProject, $isDirty, $isSaving, $recentProjects } from '../stores/project.store'
import { projectService } from '../application/services/ProjectService'

export function useProject() {
  const activeProject = useStore($activeProject)
  const recentProjects = useStore($recentProjects)
  const isSaving = useStore($isSaving)
  const isDirty = useStore($isDirty)

  return {
    activeProject,
    recentProjects,
    isSaving,
    isDirty,
    saveProject: (isAuto?: boolean) => projectService.saveProject(isAuto),
    createNewProject: (name?: string) => projectService.createNewProject(name),
    loadProject: (jsonStr: string) => projectService.loadProject(jsonStr)
  }
}
