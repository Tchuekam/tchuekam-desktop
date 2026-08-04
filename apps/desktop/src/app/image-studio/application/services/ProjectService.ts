/**
 * TchueKAM Image Studio v2 — Project Service
 */

import { createDefaultProject, deserializeProject, serializeProject } from '../../core/models'
import type { StudioProjectData } from '../../core/types'
import { $layers, setLayers } from '../../stores/layer.store'

import {
  $activeProject,
  $isDirty,
  $isSaving,
  $recentProjects,
  setProject
} from '../../stores/project.store'
import { showToast } from '../../stores/ui.store'
import { eventBus } from '../events/EventBus'

export class ProjectService {
  private autoSaveTimer: any = null

  public initAutoSave(intervalMs: number = 30000): void {
    if (this.autoSaveTimer) {
      clearInterval(this.autoSaveTimer)
    }

    this.autoSaveTimer = setInterval(() => {
      if ($isDirty.get() && $activeProject.get().settings.autoSave) {
        this.saveProject(true)
      }
    }, intervalMs)
  }

  public stopAutoSave(): void {
    if (this.autoSaveTimer) {
      clearInterval(this.autoSaveTimer)
      this.autoSaveTimer = null
    }
  }

  public createNewProject(name: string = 'Untitled Project'): StudioProjectData {
    const project = createDefaultProject(name)
    setProject(project)
    setLayers(project.layers)
    eventBus.emit('ProjectLoaded', { projectId: project.metadata.id })
    showToast('New project created')
    return project
  }

  public async saveProject(isAuto: boolean = false): Promise<boolean> {
    $isSaving.set(true)

    try {
      const current = $activeProject.get()
      const updatedProject: StudioProjectData = {
        ...current,
        layers: $layers.get(),
        metadata: {
          ...current.metadata,
          updatedAt: Date.now()
        }
      }

      const jsonStr = serializeProject(updatedProject)
      localStorage.setItem(`tchuekam_studio_project_${updatedProject.metadata.id}`, jsonStr)
      localStorage.setItem('tchuekam_studio_active_project_id', updatedProject.metadata.id)

      // Update recent projects list
      const recents = $recentProjects.get().filter(p => p.id !== updatedProject.metadata.id)
      $recentProjects.set([updatedProject.metadata, ...recents].slice(0, 10))

      $activeProject.set(updatedProject)
      $isDirty.set(false)
      eventBus.emit('ProjectSaved', { projectId: updatedProject.metadata.id, isAuto })

      if (!isAuto) {
        showToast('Project saved successfully!')
      }
      return true
    } catch (err: any) {
      showToast('Failed to save project', 'error')
      return false
    } finally {
      $isSaving.set(false)
    }
  }

  public loadProject(jsonStr: string): boolean {
    try {
      const project = deserializeProject(jsonStr)
      setProject(project)
      setLayers(project.layers)
      eventBus.emit('ProjectLoaded', { projectId: project.metadata.id })
      showToast(`Loaded project: ${project.metadata.name}`)
      return true
    } catch (err) {
      showToast('Invalid project format', 'error')
      return false
    }
  }
}

export const projectService = new ProjectService()
