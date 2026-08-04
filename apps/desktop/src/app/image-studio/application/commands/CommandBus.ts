/**
 * TchueKAM Image Studio v2 — Command Interface & Bus
 */

import { updateHistoryStatus } from '../../stores/history.store'
import { eventBus } from '../events/EventBus'

export interface ICommand<TResult = any> {
  readonly name: string
  readonly supportsUndo: boolean
  validate(): Promise<boolean> | boolean
  execute(): Promise<TResult> | TResult
  undo?(): Promise<void> | void
}

class CommandBus {
  private undoStack: ICommand[] = []
  private redoStack: ICommand[] = []
  private maxHistory: number = 30

  public async dispatch<T = any>(command: ICommand<T>): Promise<T> {
    const isValid = await command.validate()
    if (!isValid) {
      throw new Error(`Command validation failed: ${command.name}`)
    }

    const result = await command.execute()

    if (command.supportsUndo) {
      this.undoStack.push(command)
      if (this.undoStack.length > this.maxHistory) {
        this.undoStack.shift()
      }
      this.redoStack = []
      this.syncHistoryState()
    }

    eventBus.emit('CanvasUpdated', { command: command.name })
    return result
  }

  public async undo(): Promise<boolean> {
    const command = this.undoStack.pop()
    if (!command || !command.undo) {
      return false
    }

    await command.undo()
    this.redoStack.push(command)
    this.syncHistoryState()
    eventBus.emit('HistoryChanged', { action: 'undo', command: command.name })
    eventBus.emit('CanvasUpdated', { command: `Undo ${command.name}` })
    return true
  }

  public async redo(): Promise<boolean> {
    const command = this.redoStack.pop()
    if (!command) {
      return false
    }

    await command.execute()
    this.undoStack.push(command)
    this.syncHistoryState()
    eventBus.emit('HistoryChanged', { action: 'redo', command: command.name })
    eventBus.emit('CanvasUpdated', { command: `Redo ${command.name}` })
    return true
  }

  public clearHistory(): void {
    this.undoStack = []
    this.redoStack = []
    this.syncHistoryState()
  }

  private syncHistoryState(): void {
    updateHistoryStatus(this.undoStack.length, this.redoStack.length)
  }
}

export const commandBus = new CommandBus()
