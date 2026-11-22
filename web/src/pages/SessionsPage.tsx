import {
  useEffect,
  useLayoutEffect,
  useState,
  useCallback,
  useRef,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Database,
  MessageSquare,
  Search,
  Trash2,
  Clock,
  Terminal,
  Globe,
  MessageCircle,
  Hash,
  X,
  Play,
  Eraser,
  Download,
  Pencil,
  Check,
  Archive,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  SessionInfo,
  SessionMessage,
  SessionSearchResult,
  SessionStoreStats,
  StatusResponse,
} from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { PlatformsCard } from "@/components/PlatformsCard";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { Button } from "@nous-research/ui/ui/components/button";
import { Checkbox } from "@nous-research/ui/ui/components/checkbox";
import { ListItem } from "@nous-research/ui/ui/components/list-item";
import { Segmented } from "@nous-research/ui/ui/components/segmented";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { useConfirmDelete } from "@nous-research/ui/hooks/use-confirm-delete";
import { Input } from "@nous-research/ui/ui/components/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@nous-research/ui/ui/components/dialog";
import { useSystemActions } from "@/contexts/useSystemActions";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";
import { isDashboardEmbeddedChatEnabled } from "@/lib/dashboard-flags";

const SOURCE_CONFIG: Record<string, { icon: typeof Terminal; color: string }> =
  {
    cli: { icon: Terminal, color: "text-primary" },
    telegram: { icon: MessageCircle, color: "text-[oklch(0.65_0.15_250)]" },
    discord: { icon: Hash, color: "text-[oklch(0.65_0.15_280)]" },
    slack: { icon: MessageSquare, color: "text-[oklch(0.7_0.15_155)]" },
    whatsapp: { icon: Globe, color: "text-success" },
    cron: { icon: Clock, color: "text-warning" },
  };

/** Render an FTS5 snippet with highlighted matches.
 *  The backend wraps matches in >>> and <<< delimiters. */
function SnippetHighlight({ snippet }: { snippet: string }) {
  const parts: React.ReactNode[] = [];
  const regex = />>>(.*?)<<</g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = regex.exec(snippet)) !== null) {
    if (match.index > last) {
      parts.push(snippet.slice(last, match.index));
    }
    parts.push(
      <mark key={i++} className="bg-warning/30 text-warning px-0.5">
        {match[1]}
      </mark>,
    );
    last = regex.lastIndex;
  }
  if (last < snippet.length) {
    parts.push(snippet.slice(last));
  }
  return (
    <p className="font-mondwest normal-case mt-0.5 min-w-0 max-w-full truncate text-xs text-text-secondary">
      {parts}
    </p>
  );
}

function ToolCallBlock({
  toolCall,
}: {
  toolCall: { id: string; function: { name: string; arguments: string } };
}) {
  const [open, setOpen] = useState(false);
  const { t } = useI18n();

  let args = toolCall.function.arguments;
  try {
    args = JSON.stringify(JSON.parse(args), null, 2);
  } catch {
    // keep as-is
  }

  return (
    <div className="mt-2 border border-warning/20 bg-warning/5">
      <ListItem
        onClick={() => setOpen(!open)}
        aria-label={`${open ? t.common.collapse : t.common.expand} tool call ${toolCall.function.name}`}
        aria-expanded={open}
        className="px-3 py-2 text-xs text-warning hover:bg-warning/10 hover:text-warning"
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <span className="font-mono-ui font-medium">
          {toolCall.function.name}
        </span>
        <span className="text-warning/50 ml-auto">{toolCall.id}</span>
      </ListItem>
      {open && (
        <pre className="border-t border-warning/20 px-3 py-2 text-xs text-warning/80 overflow-x-auto whitespace-pre-wrap font-mono">
          {args}
        </pre>
      )}
    </div>
  );
}

function MessageBubble({
  msg,
  highlight,
}: {
  msg: SessionMessage;
  highlight?: string;
}) {
  const { t } = useI18n();

  const ROLE_STYLES: Record<
    string,
    { bg: string; text: string; label: string }
  > = {
    user: {
      bg: "bg-primary/10",
      text: "text-primary",
      label: t.sessions.roles.user,
    },
    assistant: {
      bg: "bg-success/10",
      text: "text-success",
      label: t.sessions.roles.assistant,
    },
    system: {
      bg: "bg-muted",
      text: "text-muted-foreground",
      label: t.sessions.roles.system,
    },
    tool: {
      bg: "bg-warning/10",
      text: "text-warning",
      label: t.sessions.roles.tool,
    },
  };

  const style = ROLE_STYLES[msg.role] ?? ROLE_STYLES.system;
  const label = msg.tool_name
    ? `${t.sessions.roles.tool}: ${msg.tool_name}`
    : style.label;

  // Check if any search term appears as a prefix of any word in content
  const isHit = (() => {
    if (!highlight || !msg.content) return false;
    const content = msg.content.toLowerCase();
    const terms = highlight.toLowerCase().split(/\s+/).filter(Boolean);
    return terms.some((term) => content.includes(term));
  })();

  // Split search query into terms for inline highlighting
  const highlightTerms =
    isHit && highlight ? highlight.split(/\s+/).filter(Boolean) : undefined;

  return (
    <div
      className={`${style.bg} p-3 ${isHit ? "ring-1 ring-warning/40" : ""}`}
      data-search-hit={isHit || undefined}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs font-semibold ${style.text}`}>{label}</span>
        {isHit && (
          <Badge tone="warning" className="text-xs py-0 px-1.5">
            {t.common.match}
          </Badge>
        )}
        {msg.timestamp && (
          <span className="text-xs text-text-tertiary">
            {timeAgo(msg.timestamp)}
          </span>
        )}
      </div>
      {msg.content &&
        (msg.role === "system" ? (
          <div className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
            {msg.content}
          </div>
        ) : (
          <Markdown content={msg.content} highlightTerms={highlightTerms} />
        ))}
      {msg.tool_calls && msg.tool_calls.length > 0 && (
        <div className="mt-1">
          {msg.tool_calls.map((tc) => (
            <ToolCallBlock key={tc.id} toolCall={tc} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Message list with auto-scroll to first search hit. */
function MessageList({
  messages,
  highlight,
}: {
  messages: SessionMessage[];
  highlight?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!highlight || !containerRef.current) return;
    // Scroll to first hit after render
    const timer = setTimeout(() => {
      const hit = containerRef.current?.querySelector("[data-search-hit]");
      if (hit) {
        hit.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 50);
    return () => clearTimeout(timer);
  }, [messages, highlight]);

  return (
    <div
      ref={containerRef}
      className="flex flex-col gap-3 max-h-[600px] overflow-y-auto pr-2"
    >
      {messages.map((msg, i) => (
        <MessageBubble key={i} msg={msg} highlight={highlight} />
      ))}
    </div>
  );
}

function SessionRow({
  session,
  snippet,
  searchQuery,
  isExpanded,
  isSelected,
  onToggle,
  onSelectClick,
  onDelete,
  onRename,
  onExport,
  resumeInChatEnabled,
}: SessionRowProps) {
  const [messages, setMessages] = useState<SessionMessage[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(session.title ?? "");
  const [renameSaving, setRenameSaving] = useState(false);
  const { t } = useI18n();
  const navigate = useNavigate();

  useEffect(() => {
    if (isExpanded && messages === null && !loading) {
      setLoading(true);
      api
        .getSessionMessages(session.id)
        .then((resp) => setMessages(resp.messages))
        .catch((err) => setError(String(err)))
        .finally(() => setLoading(false));
    }
  }, [isExpanded, session.id, messages, loading]);

  const sourceInfo = (session.source
    ? SOURCE_CONFIG[session.source]
    : null) ?? { icon: Globe, color: "text-muted-foreground" };
  const SourceIcon = sourceInfo.icon;
  const hasTitle = session.title && session.title !== "Untitled";

  const submitRename = async () => {
    const value = renameValue.trim();
    if (!value || value === session.title) {
      setRenaming(false);
      return;
    }
    setRenameSaving(true);
    try {
      await onRename(session.id, value);
      setRenaming(false);
    } finally {
      setRenameSaving(false);
    }
  };

  const actionButtons = (
    <>
      <Badge tone="outline" className="text-xs">
        {session.source ?? "local"}
      </Badge>

      {resumeInChatEnabled && (
        <Button
          ghost
          size="icon"
          className="text-muted-foreground hover:text-success"
          aria-label={t.sessions.resumeInChat}
          title={t.sessions.resumeInChat}
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/chat?resume=${encodeURIComponent(session.id)}`);
          }}
        >
          <Play />
        </Button>
      )}

      <Button
        ghost
        size="icon"
        className="text-muted-foreground hover:text-foreground"
        aria-label="Rename session"
        title="Rename session"
        onClick={(e) => {
          e.stopPropagation();
          setRenameValue(
            session.title && session.title !== "Untitled"
              ? session.title
              : "",
          );
          setRenaming(true);
        }}
      >
        <Pencil />
      </Button>

      <Button
        ghost
        size="icon"
        className="text-muted-foreground hover:text-foreground"
        aria-label="Export session"
        title="Export session JSON"
        onClick={(e) => {
          e.stopPropagation();
          onExport(session.id);
        }}
      >
        <Download />
      </Button>

      <Button
        ghost
        destructive
        size="icon"
        aria-label={t.sessions.deleteSession}
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
      >
        <Trash2 />
      </Button>
    </>
  );

  // Selected rows get a stronger left-edge accent + tinted background so the
  // selection state is unambiguous even when scrolling past the bulk-action
  // bar at the top. Beat the is_active styling — explicit user selection
  // takes priority over "this session is live".
  const containerClasses = isSelected
    ? "border-primary/40 bg-primary/[0.06]"
    : session.is_active
      ? "border-success/30 bg-success/[0.03]"
      : "border-border";

  // Clicking the checkbox must NOT toggle row expansion; selection and
  // expansion are independent gestures. We bind ``onClick`` directly on
  // the Checkbox (which Radix forwards to its underlying ``<button
  // role=checkbox>``) so the event carries the real ``shiftKey`` state
  // for range-select AND so keyboard activation (Space on the focused
  // checkbox) toggles selection via the same code path — the browser
  // synthesises a click on <button> for Space, so one handler covers
  // mouse + keyboard cleanly.
  const handleSelectClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelectClick(e);
  };

  return (
    <div
      className={`max-w-full min-w-0 overflow-hidden border transition-colors ${containerClasses}`}
    >
      <div
        className="flex cursor-pointer items-start gap-3 p-3 transition-colors hover:bg-secondary/30"
        onClick={onToggle}
      >
        <span className="flex shrink-0 items-center pt-0.5">
          <Checkbox
            checked={isSelected}
            onClick={handleSelectClick}
            aria-label={t.sessions.selectSession}
          />
        </span>
        <div className={`shrink-0 pt-0.5 ${sourceInfo.color}`}>
          <SourceIcon className="h-4 w-4" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <div className="flex min-w-0 items-center gap-2">
                {renaming ? (
                  <div
                    className="flex min-w-0 flex-1 items-center gap-1.5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void submitRename();
                        else if (e.key === "Escape") setRenaming(false);
                      }}
                      placeholder="Session title"
                      className="h-7 min-w-0 flex-1 py-0 text-sm"
                      disabled={renameSaving}
                    />
                    <Button
                      ghost
                      size="icon"
                      className="text-muted-foreground hover:text-success"
                      aria-label="Save title"
                      title="Save title"
                      disabled={renameSaving}
                      onClick={() => void submitRename()}
                    >
                      {renameSaving ? (
                        <Spinner className="text-sm" />
                      ) : (
                        <Check />
                      )}
                    </Button>
                    <Button
                      ghost
                      size="icon"
                      className="text-muted-foreground hover:text-foreground"
                      aria-label="Cancel rename"
                      title="Cancel rename"
                      disabled={renameSaving}
                      onClick={() => setRenaming(false)}
                    >
                      <X />
                    </Button>
                  </div>
                ) : (
                  <span
                    className={`font-mondwest normal-case min-w-0 flex-1 truncate text-sm ${hasTitle ? "font-medium" : "text-muted-foreground italic"}`}
                  >
                    {hasTitle
                      ? session.title
                      : session.preview
                        ? session.preview.slice(0, 60)
                        : t.sessions.untitledSession}
                  </span>
                )}
                {session.is_active && (
                  <Badge tone="success" className="shrink-0 text-xs">
                    <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                    {t.common.live}
                  </Badge>
                )}
              </div>
              <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
                <span className="max-w-[min(100%,12rem)] truncate sm:max-w-[180px]">
                  {(session.model ?? t.common.unknown).split("/").pop()}
                </span>
                <span className="text-border">&#183;</span>
                <span className="shrink-0">
                  {session.message_count} {t.common.msgs}
                </span>
                {session.tool_call_count > 0 && (
                  <>
                    <span className="text-border">&#183;</span>
                    <span className="shrink-0">
                      {session.tool_call_count} {t.common.tools}
                    </span>
                  </>
                )}
                <span className="text-border">&#183;</span>
                <span className="shrink-0">{timeAgo(session.last_active)}</span>
              </div>
              {snippet && <SnippetHighlight snippet={snippet} />}
            </div>

            <div className="hidden shrink-0 items-center gap-2 sm:flex">
              {actionButtons}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:hidden">
            {actionButtons}
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="min-w-0 border-t border-border bg-background/50 p-4">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <Spinner className="text-xl text-primary" />
            </div>
          )}
          {error && (
            <p className="text-sm text-destructive py-4 text-center">{error}</p>
          )}
          {messages && messages.length === 0 && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              {t.sessions.noMessages}
            </p>
          )}
          {messages && messages.length > 0 && (
            <MessageList messages={messages} highlight={searchQuery} />
          )}
        </div>
      )}
    </div>
  );
}

type SessionsView = "list" | "overview";

const PAGE_SIZE = 20;

function SessionsPagination({
  className,
  compact = false,
  onPageChange,
  page,
  total,
}: SessionsPaginationProps) {
  const { t } = useI18n();
  const pageCount = Math.ceil(total / PAGE_SIZE);

  return (
    <div
      className={`flex items-center ${compact ? "gap-1" : "justify-between pt-2"}${className ? ` ${className}` : ""}`}
    >
      {!compact && (
        <span className="text-xs text-muted-foreground">
          {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)}{" "}
          {t.common.of} {total}
        </span>
      )}

      <div className="flex items-center gap-1">
        <Button
          outlined
          size="icon"
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
          aria-label={t.sessions.previousPage}
        >
          <ChevronLeft />
        </Button>
        <span className="px-2 text-xs text-muted-foreground">
          {t.common.page} {page + 1} {t.common.of} {pageCount}
        </span>
        <Button
          outlined
          size="icon"
          disabled={(page + 1) * PAGE_SIZE >= total}
          onClick={() => onPageChange(page + 1)}
          aria-label={t.sessions.nextPage}
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<
    SessionSearchResult[] | null
  >(null);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const logScrollRef = useRef<HTMLPreElement | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [overviewSessions, setOverviewSessions] = useState<SessionInfo[]>([]);
  const [view, setView] = useState<SessionsView>("overview");
  // Count of empty (no-message, ended, non-archived) sessions across the
  // entire DB, populated by /api/sessions/empty/count. Used to:
  //   • hide the "Delete empty" button when there's nothing to clean up
  //   • show "(N)" alongside the label
  //   • surface the count in the confirm dialog body
  // Refreshed on mount, after single-session deletes, and after the bulk
  // delete itself — none of those code paths can update the global empty
  // count from local state alone (per-page list != global DB count).
  const [emptyCount, setEmptyCount] = useState(0);
  const [deleteEmptyOpen, setDeleteEmptyOpen] = useState(false);
  const [deletingEmpty, setDeletingEmpty] = useState(false);
  // Bulk-select-then-delete state. ``selectedIds`` is a Set so per-row
  // checkbox toggles and ``has()`` lookups are O(1); we wrap mutations
  // in a fresh Set so React notices the change (mutating in place
  // wouldn't trigger a re-render).
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  // Index of the last row whose checkbox was clicked WITHOUT shift,
  // resolved against the currently visible (post-search) ``filtered``
  // list. Used as the anchor for shift-click range select — matches the
  // Gmail / Notion / file-explorer convention. ``null`` means "no
  // anchor yet", in which case shift-click degrades to a plain toggle.
  const lastClickedIndexRef = useRef<number | null>(null);
  const [deleteSelectedOpen, setDeleteSelectedOpen] = useState(false);
  const [deletingSelected, setDeletingSelected] = useState(false);
  const [stats, setStats] = useState<SessionStoreStats | null>(null);
  const [pruneOpen, setPruneOpen] = useState(false);
  const [pruneDays, setPruneDays] = useState("90");
  const [pruning, setPruning] = useState(false);
  const { toast, showToast } = useToast();
  const { t } = useI18n();
  const { setAfterTitle, setEnd } = usePageHeader();
  const { activeAction, actionStatus, dismissLog } = useSystemActions();
  const resumeInChatEnabled = isDashboardEmbeddedChatEnabled();

  const refreshEmptyCount = useCallback(() => {
    api
      .getEmptySessionsCount()
      .then((r) => setEmptyCount(r.count))
      .catch(() => {});
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
    lastClickedIndexRef.current = null;
  }, []);

  useLayoutEffect(() => {
    if (loading) {
      setAfterTitle(null);
      return;
    }
    setAfterTitle(
      <Badge tone="secondary" className="text-xs tabular-nums">
        {total}
      </Badge>,
    );
    return () => {
      setAfterTitle(null);
    };
  }, [loading, setAfterTitle, total]);

  useEffect(() => {
    setEnd(
      <Button
        outlined
        size="sm"
        className="gap-1.5"
        onClick={() => setPruneOpen(true)}
      >
        <Archive className="h-3.5 w-3.5" />
        Prune old sessions
      </Button>,
    );
    return () => {
      setEnd(null);
    };
  }, [setEnd]);

  const loadSessions = useCallback((p: number) => {
    setLoading(true);
    api
      .getSessions(PAGE_SIZE, p * PAGE_SIZE)
      .then((resp) => {
        setSessions(resp.sessions);
        setTotal(resp.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const loadStats = useCallback(() => {
    api
      .getSessionStats()
      .then(setStats)
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadSessions(page);
    refreshEmptyCount();
  }, [loadSessions, page, refreshEmptyCount]);

  useEffect(() => {
    const loadOverview = () => {
      api
        .getStatus()
        .then(setStatus)
        .catch(() => {});
      api
        .getSessions(50)
        .then((r) => setOverviewSessions(r.sessions))
        .catch(() => {});
    };
    loadOverview();
    const id = setInterval(loadOverview, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const el = logScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [actionStatus?.lines]);

  // Wrapped setters that ALSO clear the bulk selection. The user's
  // mental model is "I'm selecting what I can see" — carrying a
  // selection across a page change, search input, or view switch
  // would arm invisible rows for deletion, which is the exact footgun
  // the confirm dialog can't catch. Doing this at the call sites
  // instead of in a ``useEffect`` keeps us out of the
  // react-hooks/set-state-in-effect lint trap and the cascading
  // re-render it warns about.
  const goToPage = useCallback(
    (p: number) => {
      setPage(p);
      clearSelection();
    },
    [clearSelection],
  );
  const updateSearch = useCallback(
    (value: string) => {
      setSearch(value);
      clearSelection();
    },
    [clearSelection],
  );
  const switchView = useCallback(
    (next: SessionsView) => {
      setView(next);
      clearSelection();
    },
    [clearSelection],
  );

  // Debounced FTS search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!search.trim()) {
      setSearchResults(null);
      setSearching(false);
      return;
    }

    setSearching(true);
    debounceRef.current = setTimeout(() => {
      api
        .searchSessions(search.trim())
        .then((resp) => setSearchResults(resp.results))
        .catch(() => setSearchResults(null))
        .finally(() => setSearching(false));
    }, 300);

