"use client";

import React, { useState, useEffect, useRef, useCallback, Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import axios from "axios";
import {
  FiSend, FiImage, FiTerminal, FiSearch,
  FiZap, FiLayout, FiUpload,
  FiPlus, FiSun, FiMoon, FiCheck, FiX, FiEdit2,
  FiArrowLeft, FiAlertCircle, FiCopy,
} from "react-icons/fi";
import { CgTerminal } from "react-icons/cg";
import { BiLoaderAlt } from "react-icons/bi";
import { RiRobot2Line, RiSparklingLine } from "react-icons/ri";
// import { useUser } from "@/context/UserContext";
import { useTheme } from "next-themes";
import dynamic from "next/dynamic";
import toast, { Toaster } from "react-hot-toast";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import PlanVisualizer from "./components/PlanVisualizer";
import Link from "next/link";
import { GoBook } from "react-icons/go";
import { VscLayoutSidebarLeftOff } from "react-icons/vsc";

const CanvasArea = dynamic(() => import("./CanvasArea"), { ssr: false });
const SyntaxHighlighter = dynamic(
  () => import('react-syntax-highlighter').then((mod) => mod.Prism),
  { ssr: false }
);
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { HiOutlineArrowUpTray, HiOutlineTrash } from "react-icons/hi2";
import Image from "next/image";
import { rewriteMuapiProxyUrl } from "@/app/image-studio/proxyUrl";


// Mirrors the convention in packages/studio/src/muapi.js: under an http(s)
// origin we go through the host app's /api/muapi-proxy endpoint so api.muapi.ai
// CORS never applies without colliding with /api/v1/* SaaS routes.
const DIRECT_UPSTREAM =
  typeof window === "undefined" || !window.location?.protocol?.startsWith("http");
const UPSTREAM_ORIGIN = "https://api.muapi.ai";
const API = DIRECT_UPSTREAM
  ? `${UPSTREAM_ORIGIN}/api/v1/creative-agent`
  : rewriteMuapiProxyUrl("/api/v1/creative-agent");

const formatTime = (dateStr) => {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const formatDateHeader = (dateStr) => {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return "Today";
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });
};

const TypingDots = () => (
  <div className="typing-dots py-1.5 px-1">
    <span></span>
    <span></span>
    <span></span>
  </div>
);

export default function CreativeCanvas({
  user,
  theme: forcedTheme,
  setTheme: forcedSetTheme,
  creditConversionRate = 200,
  // Embed-mode props (set by the /embed/agent/[id] page).
  // When embedCode is truthy, the component:
  //   1. Sends `x-agent-embed-code: <code>` instead of a Bearer token.
  //   2. Tracks session_id in localStorage instead of the URL query string
  //      (the iframe URL stays at /embed/agent/<code>).
  //   3. Hides owner-only UI (sessions sidebar, profile menu, / links).
  embedCode = null,
  isEmbed = false,
  // Platform customization props:
  // navLinks: array of { icon, label, path } to show in the user dropdown menu.
  // If not provided, defaults to the muapiapp links (Explore, Top Up, etc.).
  navLinks = null,
  // userBalanceLabel: string like "$ 5.00" or "1200 credits" to show in the dropdown.
  // If not provided, falls back to "$ {user.balance}".
  userBalanceLabel = null,
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inEmbedMode = isEmbed && !!embedCode;
  const embedStorageKey = inEmbedMode ? `muapi_agent_session_${embedCode}` : null;
  const [embedSessionId, setEmbedSessionId] = useState(() => {
    if (typeof window === "undefined" || !embedStorageKey) return null;
    return window.localStorage.getItem(embedStorageKey) || null;
  });
  const sessionId = inEmbedMode ? embedSessionId : searchParams.get("session");

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [assets, setAssets] = useState([]);
  const [activeTasks, setActiveTasks] = useState([]);
  const [busy, setBusy] = useState(false);
  const [openProfile, setOpenProfile] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  const [sessions, setSessions] = useState([]);
  const [currentSessionName, setCurrentSessionName] = useState("Creative Canvas");
  const [isEditingName, setIsEditingName] = useState(false);
  const [newName, setNewName] = useState("");
  const [showSessions, setShowSessions] = useState(false);
  const [skills, setSkills] = useState([]);
  const [activeSkill, setActiveSkill] = useState(null);
  const [showSkillsMenu, setShowSkillsMenu] = useState(false);
  const [showAssetsMenu, setShowAssetsMenu] = useState(false);
  const [showMentionPopup, setShowMentionPopup] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionCursorPos, setMentionCursorPos] = useState(0);
  const [hoveredAsset, setHoveredAsset] = useState(null);

  // Left Sidebar and Session Management
  const [showLeftSidebar, setShowLeftSidebar] = useState(true);
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editingSessionName, setEditingSessionName] = useState("");
  const [hoveredSessionId, setHoveredSessionId] = useState(null);

  // Layout resizing
  const [sidebarWidth, setSidebarWidth] = useState(350);
  const [showChat, setShowChat] = useState(true);
  const [prevWidth, setPrevWidth] = useState(350);
  const isResizing = useRef(false);

  const handleToggleSidebar = () => {
    if (showChat) {
      setPrevWidth(sidebarWidth);
      setSidebarWidth(0);
      setShowChat(false);
    } else {
      setSidebarWidth(prevWidth || 350);
      setShowChat(true);
    }
  };

  // Theme handling: Use props if provided, otherwise fallback to useTheme hook
  const { setTheme: nextSetTheme, resolvedTheme: nextResolvedTheme } = useTheme();
  const resolvedTheme = forcedTheme || nextResolvedTheme;
  const setTheme = forcedSetTheme || nextSetTheme;
  const [mounted, setMounted] = useState(false);

  const canvasRef = useRef(null);
  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const syncedUrlsRef = useRef(new Set());
  const justCreatedSessionRef = useRef(false);
  const initialHandoffProcessed = useRef(false);

  const getHeaders = useCallback(() => {
    if (inEmbedMode) {
      return { "x-agent-embed-code": embedCode };
    }
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (!token) return {};
    // The /api proxy route reads the Bearer token and re-sends it upstream as
    // `x-api-key`. Calling api.muapi.ai directly (file:// renderer) skips that
    // translation, so send the header muapi actually authenticates on.
    return DIRECT_UPSTREAM
      ? { "x-api-key": token }
      : { Authorization: `Bearer ${token}` };
  }, [inEmbedMode, embedCode]);

  // Persist embed session_id across page reloads so the conversation resumes.
  const setActiveEmbedSession = useCallback((id) => {
    setEmbedSessionId(id);
    if (typeof window !== "undefined" && embedStorageKey) {
      if (id) window.localStorage.setItem(embedStorageKey, id);
      else window.localStorage.removeItem(embedStorageKey);
    }
  }, [embedStorageKey]);

  // Initialize
  useEffect(() => {
    setMounted(true);
    // In embed mode there's no concept of "switch to another session" — the
    // visitor only ever sees the one keyed by their localStorage. Skip the
    // sessions list fetch (which would also 403-on-allowed-origins or surface
    // sessions from other embeds spawned by the same owner).
    if (!inEmbedMode) fetchSessions();
    fetchSkills();
  }, []);

  // Handle initial query and skill from URL (Fallback only)
  useEffect(() => {
    if (!mounted || busy || initialHandoffProcessed.current) return;
    // Embed pages never have a / handoff URL — skip.
    if (inEmbedMode) {
      initialHandoffProcessed.current = true;
      return;
    }

    const q = searchParams.get("q");
    const skillName = searchParams.get("skill");
    const a = searchParams.get("a");

    if (!q && !skillName && !a) {
      initialHandoffProcessed.current = true;
      return;
    }

    // We only process URL parameters if the session is brand new AND history has loaded as empty or default.
    // Since the Dashboard now sends the message, this useEffect will typically see the user message in history
    // and correctly skip sending q again.
    const isNewSession = messages.length === 1 && messages[0].role === "assistant";
    
    if (isNewSession) {
      initialHandoffProcessed.current = true;

      let initialAtts = null;
      if (a) {
        initialAtts = a.split(",").map(label => ({ asset_label: label, kind: "image" }));
      }

      if (skillName && !activeSkill) {
        const found = skills.find(s => s.name === skillName);
        if (found) {
          setActiveSkill(found);
          if (q) {
            setTimeout(() => sendMessage(q, found, initialAtts), 10);
          }
        }
      } else if (q) {
        sendMessage(q, null, initialAtts);
      }

      // Cleanup URL once processed
      const newParams = new URLSearchParams(searchParams.toString());
      newParams.delete("q");
      newParams.delete("skill");
      newParams.delete("a");
      router.replace(`?${newParams.toString()}`, { scroll: false });
    } else if (messages.length > 1 || (messages.length === 1 && messages[0].role === "user")) {
      // If history already has messages, we consider the handoff "processed" by the backend.
      initialHandoffProcessed.current = true;
      
      const newParams = new URLSearchParams(searchParams.toString());
      newParams.delete("q");
      newParams.delete("skill");
      newParams.delete("a");
      router.replace(`?${newParams.toString()}`, { scroll: false });
    }
  }, [mounted, busy, messages, skills.length, searchParams]);

  useEffect(() => {
    if (justCreatedSessionRef.current) {
      justCreatedSessionRef.current = false;
      return;
    }
    // Clear the sync-tracking set whenever the session changes so assets from
    // the new session are always painted to canvas (prevents stale URL leakage).
    syncedUrlsRef.current.clear();
    if (sessionId) {
      loadHistory();
      loadAssets();
      // Sync name if sessions are already loaded
      const current = sessions.find(s => s.id === sessionId);
      if (current) {
        setCurrentSessionName(current.name);
      } else {
        fetchSessions(); // Re-fetch to find the name if not in list
      }
    } else {
      setMessages([{ role: "assistant", content: `Hello ${user?.username || "User"} — what shall we create today?`, timestamp: new Date().toISOString() }]);
      setAssets([]);
      setCurrentSessionName("New Session");
    }
  }, [sessionId]); // Removed sessions from deps to avoid infinite loop if fetchSessions updates sessions

  const fetchSessions = async () => {
    try {
      const { data } = await axios.get(`${API}/sessions`, { headers: getHeaders() });
      setSessions(data);
      if (sessionId) {
        const current = data.find(s => s.id === sessionId);
        if (current) setCurrentSessionName(current.name);
      }
    } catch {}
  };

  const fetchSkills = async () => {
    try {
      const { data } = await axios.get(`${API}/agent-skills`, { headers: getHeaders() });
      setSkills(data);
    } catch (err) {
      console.error("Failed to fetch skills:", err);
    }
  };

  const processEvent = (ev, msgIdx) => {
    const p = ev.payload || {};

    // Canvas mutation events — apply directly to the live canvas, don't push
    // them into the chat transcript.
    if (ev.type === "canvas_op") {
      const op = p.op;
      const args = p.args || {};
      const c = canvasRef.current;
      if (!c) return;
      if (op === "move" && typeof c.moveNode === "function") {
        c.moveNode(args.asset_id, args.x, args.y);
      } else if (op === "arrange" && typeof c.arrangeNodes === "function") {
        c.arrangeNodes(args.moves || []);
      }
      return;
    }

    const flat = (() => {
      switch (ev.type) {
        case "text":         return { type: "text", content: p.content };
        case "info":         return { type: "info", content: p.content };
        case "error":        return { type: "error", message: p.message };
        case "tool_call":    return { type: "tool_call", name: p.name, args: p.args };
        case "tool_result":  return { type: "tool_result", name: p.name, result: p.result, asset: p.asset };
        case "plan_propose": return { type: "plan_propose", title: p.title, nodes: p.nodes, total_credits: p.total_credits };
        default:             return { type: ev.type, ...p };
      }
    })();
    if (!flat) return;
    flat.job_id = ev.job_id || p.job_id;

    // If the job has already been approved or rejected, mark approval events as handled.
    if (ev.approved !== undefined && ev.approved !== null) {
      const isApproval = flat.type === "plan_propose" || (flat.type === "info" && (flat.content?.includes("approval") || flat.content?.includes("confirmation")));
      if (isApproval) {
        flat.handled = true;
      }
    }

    setMessages(prev => {
      const arr = [...prev];
      if (msgIdx < 0 || msgIdx >= arr.length) return arr;
      const m = { ...arr[msgIdx], events: [...(arr[msgIdx].events || [])] };
      if (m.events.find(e => e.id === ev.id)) return arr;
      
      // Update event and mark previous ones as handled if this is a result
      m.events.push({ ...flat, id: ev.id });
      if (flat.type === "text") m.content = (m.content || "") + (flat.content || "");
      
      // If this is an info-approval pill, hide it if we already have a plan for this job
      if (flat.type === "info" && (flat.content?.includes("approval") || flat.content?.includes("confirmation"))) {
        const hasPlan = m.events.some(e => e.job_id === flat.job_id && e.type === "plan_propose");
        if (hasPlan) flat.handled = true;
      }

      if (flat.type === "tool_result" || flat.type === "error") {
        m.events = m.events.map(e => 
          e.job_id === flat.job_id && (
            (e.type === "info" && (e.content?.includes("approval") || e.content?.includes("confirmation"))) ||
            (e.type === "plan_propose")
          )
            ? { ...e, handled: true }
            : e
        );
      }
      
      // If we just got a plan, hide any loose "Waiting for approval" pills for this job
      if (flat.type === "plan_propose") {
        m.events = m.events.map(e => 
          e.job_id === flat.job_id && e.type === "info" && (e.content?.includes("approval") || e.content?.includes("confirmation"))
            ? { ...e, handled: true }
            : e
        );
      }
      
      arr[msgIdx] = m;
      return arr;
    });

    if (flat.type === "tool_call" && ["generate_image", "generate_video", "image_to_video", "edit_image", "edit_video", "enhance_image"].includes(flat.name)) {
      // For edit-style tools, spawn the loader at the same spot the result
      // will land at — beside the source asset (32px to its right). The
      // source stays visible throughout. Keeps the loader and the final
      // asset position in sync — no visual jump on completion.
      //
      // generate_* (no source) keeps the default centre placement.
      let x, y;
      const a = flat.args || {};
      const srcLabel = a.image || a.video || a.audio;
      if (srcLabel && typeof srcLabel === "string" && srcLabel.startsWith("asset_")) {
        try {
          const cs = canvasRef.current?.getCanvasState?.();
          const srcNode = cs?.nodes?.find(n => n.asset_id === srcLabel);
          if (srcNode) {
            x = srcNode.x + (srcNode.w || 200) + 32;
            y = srcNode.y;
          }
        } catch {}
      }
      setActiveTasks(prev => [...prev, {
        taskId: `task-${Date.now()}-${Math.random()}`,
        modelName: flat.name,
        status: "processing",
        x, y,
      }]);
    }
    
    if (flat.type === "tool_result" || flat.type === "error") {
      setActiveTasks(prev => {
        const idx = prev.findIndex(t => t.modelName === flat.name);
        if (idx !== -1) {
          const next = [...prev];
          next.splice(idx, 1);
          return next;
        }
        return prev;
      });
      
      if (flat.asset) {
        setAssets(pa => {
          // Use a combination of label and url for reliable identification
          const idx = pa.findIndex(a =>
            (flat.asset.asset_label && a.asset_label === flat.asset.asset_label) ||
            (a.url === flat.asset.url)
          );
          if (idx !== -1) {
            const next = [...pa];
            next[idx] = { ...next[idx], ...flat.asset };
            return next;
          }
          return [...pa, flat.asset];
        });

        // Side-by-side placement: when a tool result carries source_asset_id,
        // drop the new asset just to the right of the source so both stay
        // visible. Source is preserved (the user can still see / branch
        // from it). Mark the new label-url as synced so the auto-sync
        // effect doesn't also drop it at canvas centre.
        const srcLabel = flat.result?.source_asset_id;
        const newLabel = flat.asset.asset_label;
        const newUrl = flat.asset.url;
        const newKind = flat.asset.kind || "image";
        const place = canvasRef.current?.placeNextToSource || canvasRef.current?.replaceAt;
        if (srcLabel && newLabel && newUrl && place) {
          place(srcLabel, newUrl, newKind, newLabel);
          syncedUrlsRef.current?.add?.(`${newLabel}-${newUrl}`);
        }
      }
    }
  };

  const resumePolling = async (jobId, assistantIdx) => {
    let cursor = 0;
    const POLL_INTERVAL = 1200;
    const MAX_DEAD_AIR = 6 * 60 * 1000;
    let lastProgress = Date.now();
    
    setBusy(true);
    while (true) {
      try {
        const { data } = await axios.get(`${API}/jobs/${jobId}/events`, {
          params: { since: cursor },
          headers: getHeaders(),
        });
        if (data.events?.length) {
          data.events.forEach(ev => processEvent({ ...ev, approved: data.approved }, assistantIdx));
          cursor = data.cursor || cursor;
          lastProgress = Date.now();
        }
        if (data.done) break;
        if (Date.now() - lastProgress > MAX_DEAD_AIR) throw new Error("Stalled");
      } catch (err) {
        if (Date.now() - lastProgress > MAX_DEAD_AIR) break;
      }
      await new Promise(r => setTimeout(r, POLL_INTERVAL));
    }
    setBusy(false);
    loadAssets();
    // Persist final state
    setMessages(prev => {
      const next = [...prev];
      axios.patch(`${API}/sessions/${sessionId}/messages`, { messages: next }, { headers: getHeaders() }).catch(() => {});
      return next;
    });
  };

  const handleJobAction = async (jobId, action) => {
    try {
      await axios.post(`${API}/jobs/${jobId}/${action}`, {}, { headers: getHeaders() });
      toast.success(`Job ${action}ed`);
      
      // Hide the approval card in the UI
      setMessages(prev => prev.map(m => ({
        ...m,
        events: (m.events || []).map(e => 
          e.job_id === jobId && (
            (e.type === "info" && (e.content?.includes("approval") || e.content?.includes("confirmation"))) ||
            (e.type === "plan_propose")
          )
            ? { ...e, handled: true }
            : e
        )
      })));
    } catch (err) {
      toast.error(err.response?.data?.detail || `Failed to ${action} job`);
    }
  };

  const loadHistory = async () => {
    try {
      const { data } = await axios.get(`${API}/sessions/${sessionId}/messages`, { headers: getHeaders() });
      if (data && data.length > 0) {
        // Cleanup: Hide approval cards that already have results or are for inactive jobs
        const cleaned = data.map(m => ({
          ...m,
          events: (m.events || []).map((e, idx, arr) => {
            if ((e.type === "info" && (e.content?.includes("approval") || e.content?.includes("confirmation"))) || e.type === "plan_propose") {
              const hasResult = arr.slice(idx + 1).some(next => 
                next.job_id === e.job_id && (next.type === "tool_result" || next.type === "error")
              );
              if (hasResult) return { ...e, handled: true };
            }
            return e;
          })
        }));
        setMessages(cleaned);
        checkActiveJobs(cleaned);
      } else {
        setMessages([{ role: "assistant", content: `Session ready — what shall we create?`, timestamp: new Date().toISOString() }]);
      }
    } catch {
      setMessages([{ role: "assistant", content: `Session ready — what shall we create?`, timestamp: new Date().toISOString() }]);
    }
  };

  const checkActiveJobs = async (currentMessages) => {
    if (!sessionId) return;
    try {
      const { data } = await axios.get(`${API}/sessions/${sessionId}/jobs`, { headers: getHeaders() });
      const active = data.find(j => (j.status === "pending" || j.status === "processing") && j.id);
      if (active) {
        // If the last message is assistant but empty/no events, it might be the one for this job.
        let aIdx = currentMessages.length - 1;
        if (aIdx < 0 || currentMessages[aIdx].role !== "assistant") {
          // No assistant bubble to resume into, create a new one.
          setMessages(prev => {
            const next = [...prev, { role: "assistant", content: "", events: [], timestamp: new Date().toISOString() }];
            resumePolling(active.id, next.length - 1);
            return next;
          });
        } else {
          resumePolling(active.id, aIdx);
        }
      }
    } catch {}
  };

  const loadAssets = async () => {
    if (!sessionId) return;
    try {
      const { data } = await axios.get(`${API}/sessions/${sessionId}/assets`, { headers: getHeaders() });
      setAssets(data);
    } catch {}
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);
  
  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const { data } = await axios.post(`${API}/sessions`, {}, { headers: getHeaders() });
    justCreatedSessionRef.current = true;
    if (inEmbedMode) {
      setActiveEmbedSession(data.id);
    } else {
      router.replace(`?session=${data.id}`, { scroll: false });
      fetchSessions();
    }
    return data.id;
  };

  const processFile = async (file) => {
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);

    try {
      // 0. Make sure we have a session — uploaded assets must belong to one.
      const activeSessionId = await ensureSession();

      // 1. Get signed URL. On file:// there is no /api route to hit, so call the
      // same upstream endpoint the Next proxy forwards to.
      const { data: signData } = await axios.get(
        DIRECT_UPSTREAM
          ? `${UPSTREAM_ORIGIN}/app/get_file_upload_url`
          : rewriteMuapiProxyUrl("/api/app/get_file_upload_url"),
        {
          params: { filename: file.name },
          headers: getHeaders()
        }
      );

      const { url, fields } = signData;

      const formData = new FormData();
      Object.entries(fields).forEach(([key, value]) => {
        formData.append(key, value);
      });
      formData.append("file", file);

      // 2. Upload the binary directly to the signed upload URL.
      await axios.post(url, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (pe) => {
          setUploadProgress(Math.round((pe.loaded * 100) / pe.total));
        }
      });

      // 3. Final URL
      const uploadedUrl = `https://cdn.muapi.ai/${fields.key}`;

      // 4. Register as a real session asset so the agent can address it as asset_N.
      const kind = file.type?.startsWith("video/") ? "video"
                 : file.type?.startsWith("audio/") ? "audio"
                 : "image";
      const { data: registered } = await axios.post(
        `${API}/sessions/${activeSessionId}/assets`,
        { url: uploadedUrl, kind, source_tool: "upload" },
        { headers: getHeaders() },
      );

      const att = { asset_label: registered.asset_label, url: uploadedUrl, kind };
      setAttachments(prev => [...prev, att]);
      // Reflect on the canvas immediately.
      setAssets(prev => [...prev, {
        asset_label: registered.asset_label, url: uploadedUrl, kind,
        source_tool: "upload", model: null, prompt: null,
      }]);
      toast.success(`Uploaded as ${registered.asset_label}`);
    } catch (err) {
      console.error("Upload failed", err);
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleFileUpload = (e) => {
    processFile(e.target.files?.[0]);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    if (busy || uploading) return;
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (busy || uploading) return;
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  };

  const removeAttachment = (label) => {
    setAttachments(prev => prev.filter(a => a.asset_label !== label));
  };

  const sendMessage = async (textOverride = null, skillOverride = null, attachmentsOverride = null) => {
    const typed = (typeof textOverride === 'string' ? textOverride : input).trim();
    const currentAttachments = attachmentsOverride || attachments;
    if ((!typed && currentAttachments.length === 0) || busy) return;
    
    const currentSkill = skillOverride || activeSkill;

    
    let activeSessionId;
    try {
      activeSessionId = await ensureSession();
    } catch (err) {
      toast.error("Failed to establish session");
      return;
    }

    // Tell the LLM about any uploaded assets so it can call edit_image / image_to_video / etc.
    // by asset_label without us having to expose URLs in the user-visible bubble.
    const attachmentNote = currentAttachments.length
      ? "\n\n[Attached " + currentAttachments.map(a => `${a.asset_label} (${a.kind || "image"})`).join(", ") + "]"
      : "";
    const msg = typed + attachmentNote;
    const msgAttachments = [...currentAttachments];
    
    if (!attachmentsOverride) setAttachments([]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "24px";
    
    const userMsg = { 
      role: "user", 
      content: msg, 
      attachments: msgAttachments,
      timestamp: new Date().toISOString(),
      skill_name: currentSkill?.name
    };
    const updatedMessages = [...messages, userMsg];
    
    setMessages([...updatedMessages, { role: "assistant", content: "", events: [], timestamp: new Date().toISOString() }]);
    setBusy(true);

    const aIdx = updatedMessages.length; 
    
    try {
      let canvasState = null;
      try {
        canvasState = canvasRef.current?.getCanvasState?.() || null;
      } catch {}

      let endpoint = `${API}/sessions/${activeSessionId}/chat`;
      let payload = {
        message: typed,
        model: "gpt-5-mini",
        messages_snapshot: updatedMessages,
        canvas_state: canvasState,
      };

      // If a skill is pinned, use the run-skill endpoint
      if (currentSkill) {
        endpoint = `${API}/sessions/${activeSessionId}/run-skill`;
        // Map the user input to the first required input of the skill
        const primaryInputKey = currentSkill.inputs?.[0] || "premise";
        payload = {
          skill_name: currentSkill.name,
          inputs: { [primaryInputKey]: typed },
          messages_snapshot: updatedMessages,
          model: "gpt-5-mini"
        };
        if (!skillOverride) setActiveSkill(null); // Clear skill after sending if not override
      }

      const enqueueRes = await axios.post(endpoint, payload, { headers: getHeaders() });
      await resumePolling(enqueueRes.data.job_id, aIdx);
    } catch (err) {
      setMessages(prev => {
        const arr = [...prev];
        if (aIdx >= 0) arr[aIdx] = { ...arr[aIdx], content: `❌ ${err.message || err}` };
        return arr;
      });
    } finally {
      setBusy(false);
      await loadAssets();
      if (activeSessionId) {
        setMessages(prev => {
          const newMsgs = [...prev];
          axios.patch(`${API}/sessions/${activeSessionId}/messages`, { messages: newMsgs }, { headers: getHeaders() }).catch(() => {});
          return newMsgs;
        });
      }
    }
  };

  const markdownComponents = useMemo(() => ({
    a: ({ node, ...props }) => {
      const isMedia = props.href?.match(/\.(jpeg|jpg|gif|png|webp|avif)$/i);
      const isVideo = props.href?.match(/\.(mp4|webm|mov)$/i);
      if (isMedia) {
        return (
          <span className="block mt-2 mb-1">
            <a href={props.href} target="_blank" rel="noreferrer" className="block relative group overflow-hidden rounded border border-divider shadow-sm">
              <img src={props.href} alt="Generated Asset" className="w-full h-auto object-cover transition-transform group-hover:scale-105" />
              <span className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
            </a>
          </span>
        );
      }
      if (isVideo) {
        return (
          <span className="block mt-2 mb-1">
            <video src={props.href} controls className="w-full rounded border border-divider shadow-sm" />
          </span>
        );
      }
      return <a {...props} className="text-primary hover:underline underline-offset-4 font-bold" target="_blank" rel="noreferrer" />;
    },
    div: ({ node, ...props }) => <div {...props} />, 
    p: ({ node, ...props }) => <div className="mb-2 last:mb-0" {...props} />,
    pre: ({ node, ...props }) => <div className="my-3 overflow-x-auto rounded border border-divider" {...props} />,
    code: ({ node, inline, className, children, ...props }) => {
      const match = /language-(\w+)/.exec(className || '');
      return !inline && match ? (
        <SyntaxHighlighter
          style={resolvedTheme === 'dark' ? oneDark : oneLight}
          language={match[1]}
          showLineNumbers
          PreTag="div"
          className="scrollbar-subtle !m-0 !p-3 text-[12px]"
          {...props}
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code className="bg-primary/10 text-primary px-1.5 py-0.5 rounded text-[12px] font-mono" {...props}>
          {children}
        </code>
      );
    }
  }), [resolvedTheme]);


  // Sync assets to canvas once ref is ready — only push URLs not yet synced
  useEffect(() => {
    if (!sessionId || assets.length === 0) return;

    const newAssets = assets.filter(a => {
      const syncKey = `${a.asset_label || "no-label"}-${a.url}`;
      return !syncedUrlsRef.current.has(syncKey);
    });
    if (newAssets.length === 0) return;

    let attempts = 0;
    const sync = () => {
      if (canvasRef.current) {
        newAssets.forEach(a => {
          const syncKey = `${a.asset_label || "no-label"}-${a.url}`;
          if (!a.url || syncedUrlsRef.current.has(syncKey)) return;
          syncedUrlsRef.current.add(syncKey);
          
          const kind = a.kind || (a.url.match(/\.(mp4|webm|mov)$/i) ? "video" : a.url.match(/\.(mp3|wav|ogg|m4a)$/i) ? "audio" : "image");
          const label = a.asset_label || null;
          if (kind === "image") canvasRef.current.addImage(a.url, undefined, undefined, undefined, undefined, undefined, label);
          else if (kind === "video") canvasRef.current.addVideo(a.url, undefined, undefined, undefined, undefined, undefined, label);
          else if (kind === "audio") canvasRef.current.addAudio(a.url, undefined, undefined, undefined, label);
        });
        return true;
      }
      return false;
    };

    if (!sync()) {
      const timer = setInterval(() => {
        attempts++;
        if (sync() || attempts > 20) clearInterval(timer);
      }, 500);
      return () => clearInterval(timer);
    }
  }, [assets, sessionId]);

  const renameSession = async (id = null, name = null) => {
    const targetId = id || sessionId;
    const targetName = name || newName;
    const currentName = id ? (sessions.find(s => s.id === id)?.name) : currentSessionName;

    if (!targetId || !targetName.trim() || targetName.trim() === currentName) {
      setIsEditingName(false);
      setEditingSessionId(null);
      return;
    }
    try {
      await axios.patch(`${API}/sessions/${targetId}`, { name: targetName.trim() }, { headers: getHeaders() });
      if (targetId === sessionId) setCurrentSessionName(targetName.trim());
      setIsEditingName(false);
      setEditingSessionId(null);
      fetchSessions();
      toast.success("Session renamed");
    } catch {
      toast.error("Failed to rename session");
      setIsEditingName(false);
      setEditingSessionId(null);
    }
  };

  const deleteSession = async (id) => {
    toast((t) => (
      <div className="flex flex-col gap-2 p-1 min-w-[220px]">
        <div className="text-xs font-semibold text-white/90">Delete this session? This cannot be undone.</div>
        <div className="flex justify-end gap-2 mt-1">
          <button
            type="button"
            onClick={() => toast.dismiss(t.id)}
            className="px-2.5 py-1 text-[11px] rounded bg-white/10 hover:bg-white/20 text-white/70 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={async () => {
              toast.dismiss(t.id);
              try {
                await axios.delete(`${API}/sessions/${id}`, { headers: getHeaders() });
                toast.success("Session deleted");
                if (inEmbedMode) {
                  if (id === sessionId) setActiveEmbedSession(null);
                } else {
                  fetchSessions();
                  if (id === sessionId) {
                    router.push("/canvas");
                  }
                }
              } catch (err) {
                toast.error("Failed to delete session");
              }
            }}
            className="px-2.5 py-1 text-[11px] rounded bg-red-600 hover:bg-red-500 text-white font-semibold transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    ), {
      duration: 6000,
      style: {
        background: '#18181b',
        color: '#ffffff',
        border: '1px solid rgba(255, 255, 255, 0.15)',
        borderRadius: '12px',
      },
    });
  };

  const handleMouseMove = useCallback((e) => {
    if (!isResizing.current) return;
    const newWidth = window.innerWidth - e.clientX;
    if (newWidth > 300 && newWidth < 800) {
      setSidebarWidth(newWidth);
    }
  }, []);

  const stopResizing = useCallback(() => {
    isResizing.current = false;
    document.removeEventListener("mousemove", handleMouseMove);
    document.removeEventListener("mouseup", stopResizing);
    document.body.style.cursor = "default";
    document.body.style.userSelect = "auto";
  }, [handleMouseMove]);

  const startResizing = useCallback((e) => {
    isResizing.current = true;
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", stopResizing);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [handleMouseMove, stopResizing]);

  const selectMention = (item, type) => {
    const before = input.substring(0, mentionCursorPos);
    // mentionCursorPos is where @ is. query is after @.
    const after = input.substring(textareaRef.current.selectionStart);
    
