"use client";

import React, { useState, useCallback, useEffect, useRef, useMemo, useLayoutEffect } from "react";
import { useParams } from "next/navigation";
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  useReactFlow,
} from "reactflow";
import { applyMuapiProxyRequest } from "@/app/image-studio/proxyUrl";
// import "reactflow/dist/style.css";
import { BsArrowUpCircleFill } from "react-icons/bs";
import { FiZoomIn, FiZoomOut } from "react-icons/fi";
import { TfiText } from "react-icons/tfi";
import { MdLockOutline, MdOutlineZoomOutMap, MdSave } from "react-icons/md";
import { LuLayoutTemplate, LuMousePointer2 } from "react-icons/lu";
import { FaAngleDown, FaAngleLeft, FaCheck, FaPlay, FaPlus, FaRegHand, FaToolbox, FaUpload } from "react-icons/fa6";
import { FaRegEdit, FaTelegramPlane } from "react-icons/fa";
import { IoDuplicateOutline, IoImageOutline, IoVideocamOutline } from "react-icons/io5";
import { Toaster, toast } from "react-hot-toast";
import { FiSun, FiMoon } from "react-icons/fi";
import axios from "axios";
import TextGeneration from "./TextNode";
import ImageGeneration from "./ImageNode";
import VideoGeneration from "./VideoNode";
import { setWorkflowIds } from "./WorkflowStore";
import { apiNodeModels, audioModels, concatModels, imageModels, textModels, videoModels, videoCombinerModels, presets } from "./utility";
import Link from "next/link";
import RenderField from "./RenderField";
import PromptConcate from "./PromptConcate";
import { TbArrowMerge } from "react-icons/tb";
import { RiInputMethodLine } from "react-icons/ri";
import ApiNode from "./ApiNode";
import RenderApiField from "./RenderApiField";
import AudioGeneration from "./AudioNode";
import NodesNavbar from "./NodesNavbar"
import ChatWidget from "./ChatWidget";
import { AiOutlineAudio } from "react-icons/ai";
import VideoCombiner from "./VideoCombiner";
import { useGenerationCost } from "./useGenerationCost";

const nodeTypes = {
  textNode: TextGeneration,
  imageNode: ImageGeneration,
  videoNode: VideoGeneration,
  audioNode: AudioGeneration,
  concatNode: PromptConcate,
  vidConcatNode: VideoCombiner,
  apiNode: ApiNode
}

const initialNodes = [
  { id: "text1", position: { x: 0, y: 100 }, data: {}, type: "textNode" },
  { id: "image1", position: { x: 300, y: 100 }, data: {}, type: "imageNode" },
];

const initialEdges = [];

const edgeStyles = {
  blue: {
    stroke: '#3b82f6', // blue-500
    strokeWidth: 2,
    // animated: true,
  },
  green: {
    stroke: '#22c55e', // green-500
    strokeWidth: 2,
    // animated: true,
  },
  orange: {
    stroke: '#f97316', // orange-500
    strokeWidth: 2,
    // animated: true,
  },
  gray: {
    stroke: '#6b7280', // gray-500
    strokeWidth: 2,
  },
  yellow: {
    stroke: '#eab308', // yellow-500
    strokeWidth: 2,
  },
  white: {
    stroke: '#ffffff',
    strokeWidth: 2,
  }
};

const getEdgeColor = (sourceHandle, targetHandle, sourceNode = null, targetNode = null) => {
  if (sourceHandle === "apiOutput" && sourceNode) {
    const output = sourceNode.data.outputs?.[0];
    const modelType = sourceNode.data.formValues?.model_type;

    if (output?.type === 'text' || modelType === 'chat') return "blue";
    if (output?.type === 'video_url' || modelType === 'video') return "orange";
    if (output?.type === 'audio_url' || modelType === 'audio') return "yellow";
    return "green";
  }

  if (["textOutput", "concatOutput"].includes(sourceHandle)) return "blue";
  if (["imageOutput"].includes(sourceHandle)) return "green";
  if (["videoOutput"].includes(sourceHandle)) return "orange";
  if (["audioOutput"].includes(sourceHandle)) return "yellow";

  if (["textInput", "textInput4", "imageInput", "videoInput", "audioInput2", "concatInput", "apiInput"].includes(targetHandle)) return "blue";
  if (["textInput2", "textInput3", "imageInput2", "imageInput3", "videoInput2", "videoInput3", "videoInput6", "audioInput3", "apiInput2", "apiInput3"].includes(targetHandle)) return "green";
  if (["videoInput4", "audioInput4", "videoInput7"].includes(targetHandle)) return "orange";
  if (["audioInput", "videoInput5", "videoInput8"].includes(targetHandle)) return "yellow";

  if (sourceNode) {
    const type = sourceNode.type;
    if (type === 'textNode' || type === 'concatNode') return "blue";
    if (type === 'imageNode') return "green";
    if (type === 'videoNode' || type === 'vidConcatNode') return "orange";
    if (type === 'audioNode') return "yellow";
  }

  return "white";
};

const iconMap = {
  "plus": <FaPlus size={20} />,
  "image": <IoImageOutline size={20} />,
  "video": <IoVideocamOutline size={20} />,
  "audio": <AiOutlineAudio size={20} />,
  "text": <TfiText size={20} />,
};

const SPECIAL_MODEL_NAMES = {
  "text-passthrough": "Input Text",
  "image-passthrough": "Input Image",
  "video-passthrough": "Input Video",
  "audio-passthrough": "Input Audio",
};

const formatName = (id) => id.replace(/-/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

const getModelObjStatic = (category, modelId, nodeSchemas) => {
  if (category === "api") {
    // We can't easily access filteredApiNodeModels statically without passing it, 
    // but we can compute it on the fly or just return null and let useEffect handle it if needed.
    // For now, let's just use the shared logic.
    const apiModelsFromBackend = nodeSchemas?.categories?.api?.models ? Object.keys(nodeSchemas.categories.api.models) : [];
    const filtered = apiNodeModels.filter(model => apiModelsFromBackend.includes(model.id));
    return filtered.find(m => m.id === modelId) || null;
  }
  if (!modelId || !nodeSchemas?.categories) return null;
  const rawModel = nodeSchemas.categories[category]?.models?.[modelId];
  if (!rawModel) return null;

  return {
    ...rawModel,
    id: modelId,
    name: SPECIAL_MODEL_NAMES[modelId] || formatName(modelId)
  };
};

const processWorkflowData = (workflowData, nodeSchemas, id) => {
  if (!workflowData || !nodeSchemas?.categories) return null;

  const workflow = workflowData?.data;
  if (!workflow?.nodes) return null;

  const restoredNodes = workflow.nodes.map(n => ({
    id: n.id,
    type: n.category === "utility" 
      ? (n.model === "video-combiner" ? "vidConcatNode" : "concatNode") 
      : `${n.category}Node`,
    position: {
      x: n.position?.x ?? 350,
      y: n.position?.y ?? 0
    },
    data: {
      nodeSchemas,
      modelId: n.model,
      selectedModel: getModelObjStatic(n.category, n.model, nodeSchemas),
      outputs: n.output_params?.outputs || [],
      resultUrl: n.output_params?.resultUrl || null,
      formValues: n.input_params || {},
      outputHistory: (workflowData.run_history?.[n.id] || [])
        .sort((a, b) => new Date(a.started_at) - new Date(b.started_at)),
    }
  }));

  const restoredEdges = (workflowData.edges || []).map((e) => {
    const sourceNode = restoredNodes.find(n => n.id === e.source);
    const targetNode = restoredNodes.find(n => n.id === e.target);
    let edgeColor = getEdgeColor(e.sourceHandle, e.targetHandle, sourceNode, targetNode);

    return {
      id: e.id || `${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle || null,
      targetHandle: e.targetHandle || null,
      style: edgeStyles[edgeColor],
    }
  });

  return {
    nodes: restoredNodes,
    edges: restoredEdges,
    metadata: {
      workflowId: id,
      runId: workflowData?.run_id,
      workflowName: workflowData.name,
      interactionMode: workflowData.is_owner,
      publishWorkflow: workflowData.is_published,
      template: {
        showTemplateBtn: workflowData.show_temp_button,
        isPublishedTemplate: workflowData.is_template,
      },
      category: workflowData?.category || "General"
    }
  };
};

const NodeFlow = ({ apiKey, initialNodeSchemas, initialWorkflowData }) => {
  const params = useParams();
  const { id } = params;

  // The npm resolution for this package pulls in its own, separate `axios` module
  // instance from Open-Higgsfield-ai/node_modules (different version than the one
  // WhiteLabelShell.js/muapi.js use), so the ambient global axios interceptor those
  // register to inject the white-label bearer token never applies to requests made
  // from here — every call below went out with no credentials at all. Attach the
  // token explicitly per-request instead of relying on that ambient interceptor.
  const api = useMemo(() => {
    const instance = axios.create();
    instance.interceptors.request.use((config) => {
      applyMuapiProxyRequest(config);
      if (apiKey && apiKey !== "server-configured") {
        config.headers = config.headers || {};
        config.headers["Authorization"] = `Bearer ${apiKey}`;
        config.headers["x-api-key"] = apiKey;
      }
      return config;
    });
    return instance;
  }, [apiKey]);

  // Pre-calculate initial state if data is provided
  const initialState = useMemo(() => {
    return processWorkflowData(initialWorkflowData, initialNodeSchemas, id);
  }, [initialWorkflowData, initialNodeSchemas, id]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialState?.nodes || []);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialState?.edges || initialEdges);
  const [activeHandleColor, setActiveHandleColor] = useState(null);
  const [loadingNodes, setLoadingNodes] = useState({});
  const [isRunning, setIsRunning] = useState(0);
  const [dropDown, setDropDown] = useState(0);
  const [workflowName, setWorkflowName] = useState(initialState?.metadata?.workflowName || "Untitled");
  const [workflowId, setWorkflowId] = useState(id);
  const [runId, setRunId] = useState(initialState?.metadata?.runId || null);
  const [hasFit, setHasFit] = useState(false);
  const [nodeSchemas, setNodeSchemas] = useState(initialNodeSchemas || {});
  const [contextMenu, setContextMenu] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [draggedEdgeInfo, setDraggedEdgeInfo] = useState(null);
  const [edgePicker, setEdgePicker] = useState(null);
  const connectionMadeRef = useRef(false);
  const onConnectRef = useRef(null);
  const [interactionMode, setInteractionMode] = useState(initialState?.metadata?.interactionMode || false);
  const [publishWorkflow, setPublishWorkflow] = useState(initialState?.metadata?.publishWorkflow || false);
  const [template, setTemplate] = useState(initialState?.metadata?.template || {
    showTemplateBtn: false,
    isPublishedTemplate: false
  });
  const [isDragging, setIsDragging] = useState(true);
  const [modelSearch, setModelSearch] = useState("");
  const [isPresetsDismissed, setIsPresetsDismissed] = useState(true);
  const [isRestoring, setIsRestoring] = useState(!initialState);
  const [totalWorkflowCost, setTotalWorkflowCost] = useState(0);

  useEffect(() => {
    const total = nodes.reduce((sum, node) => {
      const cost = parseFloat(node.data?.cost) || 0;
      return sum + cost;
    }, 0);
    setTotalWorkflowCost(total.toFixed(3));
  }, [nodes]);

  // Sync global store with initial data if provided
  useEffect(() => {
    if (initialState?.metadata) {
      setWorkflowIds(id, initialState.metadata.runId);
    }
  }, [id, initialState]);

  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [workflowCategory, setWorkflowCategory] = useState(initialState?.metadata?.category || "General");
  const [categoryInput, setCategoryInput] = useState(initialState?.metadata?.category || "General");
  const [isCategoryPopupOpen, setIsCategoryPopupOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isModelDropdownUp, setIsModelDropdownUp] = useState(false);
  const modelDropdownTriggerRef = useRef(null);

  const { zoomIn, zoomOut, fitView, getNodes, screenToFlowPosition } = useReactFlow();

  const apiModelsFromBackend =
    nodeSchemas?.categories?.api?.models
      ? Object.keys(nodeSchemas.categories.api.models)
      : [];

  const filteredApiNodeModels = apiNodeModels.filter(model =>
    apiModelsFromBackend.includes(model.id)
  );

  const loadPreset = (preset) => {
    setIsPresetsDismissed(true);
    setNodes(preset.nodes);
    setEdges(preset.edges);
    setTimeout(() => fitView({ padding: 0.4, duration: 500 }), 100);
  };

  // Moved SPECIAL_MODEL_NAMES, formatName and getModelObj logic to static helpers above

  useEffect(() => {
    if (!initialNodeSchemas) {
      api.get(`/api/workflow/${id}/node-schemas`)
        .then(res => setNodeSchemas(res.data || {}))
        .catch(err => console.error("Failed to load node schemas", err));
    }

    const handleMouseMove = (e) => {
      setMousePos({ x: e.clientX, y: e.clientY });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useLayoutEffect(() => {
    if (dropDown === 3 && modelDropdownTriggerRef.current) {
      const rect = modelDropdownTriggerRef.current.getBoundingClientRect();
      const windowHeight = window.innerHeight;
      const spaceBelow = windowHeight - rect.bottom;
      setIsModelDropdownUp(spaceBelow < 250);
    }
  }, [dropDown]);

  useEffect(() => {
    if (!nodeSchemas?.categories) return;
    setNodes((prev) => {
      const needsUpdate = prev.some((n) => n.data.nodeSchemas !== nodeSchemas);
      if (!needsUpdate) return prev;

      return prev.map((n) => ({
        ...n,
        data: {
          ...n.data,
          nodeSchemas,
        },
      }));
    });
  }, [nodeSchemas]);
  const getModelObj = useCallback((category, modelId) => {
    return getModelObjStatic(category, modelId, nodeSchemas);
  }, [nodeSchemas]);

  const restoreWorkflow = useCallback((workflowData) => {
    const workflow = workflowData?.data;
    if (!workflow?.nodes) return;

    const restoredNodes = workflow.nodes.map(n => ({
      id: n.id,
      type: n.category === "utility" 
        ? (n.model === "video-combiner" ? "vidConcatNode" : "concatNode") 
        : `${n.category}Node`,
      position: {
        x: n.position?.x ?? 350,
        y: n.position?.y ?? 0
      },
      data: {
        nodeSchemas,
        modelId: n.model,
        selectedModel: getModelObj(n.category, n.model),
        outputs: n.output_params?.outputs || [],
        resultUrl: n.output_params?.resultUrl || null,
        formValues: n.input_params || {},
        outputHistory: (workflowData.run_history?.[n.id] || [])
          .sort((a, b) => new Date(a.started_at) - new Date(b.started_at)),
      }
    }));

    const restoredEdges = (workflowData.edges || []).map((e) => {
      const sourceNode = restoredNodes.find(n => n.id === e.source);
      const targetNode = restoredNodes.find(n => n.id === e.target);
      let edgeColor = getEdgeColor(e.sourceHandle, e.targetHandle, sourceNode, targetNode);

      return {
        id: e.id || `${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle || null,
        targetHandle: e.targetHandle || null,
        style: edgeStyles[edgeColor],
      }
    });

    setNodes(restoredNodes);
    setEdges(restoredEdges);
    setWorkflowId(id);
    setRunId(workflowData?.run_id);
    setWorkflowName(workflowData.name);
    setWorkflowCategory(workflowData?.category || "General");
    setWorkflowIds(workflowData.workflow_id, workflowData?.run_id);
    setInteractionMode(workflowData.is_owner);
    setPublishWorkflow(workflowData.is_published);
    setTemplate(prev => ({
      ...prev,
      showTemplateBtn: workflowData.show_temp_button,
      isPublishedTemplate: workflowData.is_template,
    }));
    setIsRestoring(false);
  }, [id, nodeSchemas, getModelObj, setNodes, setEdges]);

  useEffect(() => {
    if (initialWorkflowData && nodeSchemas?.categories) {
      return;
    }

    if (!id || !nodeSchemas?.categories) return;

    api.get(`/api/workflow/get-workflow-def/${id}`)
      .then(res => {
        restoreWorkflow(res.data);
      })
      .catch((error) => {
        console.log(error);
        setInteractionMode(false);
        setIsRestoring(false);
      });
  }, [id, nodeSchemas, initialWorkflowData, restoreWorkflow]);

  useEffect(() => {
    if (isRestoring) return;

    if (nodes.length > 0 && !hasFit) {
      const timeout = setTimeout(() => {
        fitView({ padding: 0.4, duration: 500, minZoom: 0.2 });
        setHasFit(true);
      }, 100);
      return () => clearTimeout(timeout);
    } else if (nodes.length === 0) {
      setIsPresetsDismissed(false);
    };
  }, [nodes, hasFit, fitView, isRestoring]);

  const arrangeNodesInRow = useCallback(() => {
    const spacing = 350;
    const y = 100;
    setNodes((nds) =>
      nds.map((node, index) => ({
        ...node,
        position: { x: index * spacing, y },
      }))
    );
  }, [setNodes]);

  useEffect(() => {
    if (workflowId) return;
    arrangeNodesInRow();
  }, [arrangeNodesInRow]);

  useEffect(() => {
    setNodes((prevNodes) => {
      const edgesBySource = {};
      edges.forEach((edge) => {
        if (!edgesBySource[edge.source]) edgesBySource[edge.source] = [];
        edgesBySource[edge.source].push(edge);
      });

      const needsUpdate = prevNodes.some((node) => {
        const currentEdges = node.data.connectedEdges || [];
        const newEdges = edgesBySource[node.id] || [];
        if (currentEdges.length !== newEdges.length) return true;
        const currentIds = currentEdges.map(e => e.id).sort().join(',');
        const newIds = newEdges.map(e => e.id).sort().join(',');
        return currentIds !== newIds;
      });

      if (!needsUpdate) return prevNodes;

      return prevNodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          connectedEdges: edgesBySource[node.id] || [],
        },
      }));
    });
  }, [edges, setNodes]);

  const onDataChange = (id, newData, targetNodeId = null) => {
    setNodes((prevNodes) => {
      let updatedNodes = prevNodes.map((node) => {
        const match = node.id.toLowerCase().replace(/\s+/g, '') === id.toLowerCase().replace(/\s+/g, '');
        return match
          ? { ...node, data: { ...node.data, ...newData } }
          : node;
      });

      if (newData.errorMsg && newData.errorMsg !== null) {
        updatedNodes = updatedNodes.map((node) =>
          node.id === id
            ? { ...node, data: { ...node.data, errorMsg: newData.errorMsg } }
            : node
        );
        return updatedNodes;
      }

      let connectedEdges = edges.filter((e) => e.source === id);
      if (targetNodeId) {
        connectedEdges = connectedEdges.filter((e) => e.target === targetNodeId);
      }

      if (!connectedEdges.length) return updatedNodes;

      const resultValue = newData.resultUrl || newData.outputs?.[0]?.value;
      // if (!resultValue) return updatedNodes;

      updatedNodes = updatedNodes.map((node) => {
        const edge = connectedEdges.find((e) => e.target === node.id);
        if (!edge) return node;

        const targetHandle = edge.targetHandle;
        let updatedFormValues = { ...node.data.formValues };

        const sourceNode = updatedNodes.find((n) => n.id === edge.source);
        const sourceValue = sourceNode?.type === "concatNode"
          ? sourceNode?.data?.formValues?.prompt
          : resultValue;

        if (["textInput", "imageInput", "videoInput", "audioInput2", "apiInput"].includes(targetHandle)) {
          updatedFormValues.prompt = sourceValue;
        }

        else if (targetHandle === "textInput4") {
          updatedFormValues.system_prompt = sourceValue;
        }

        else if (["textInput3", "imageInput2", "videoInput6"].includes(targetHandle)) {
          const list = Array.isArray(updatedFormValues.images_list)
            ? [...updatedFormValues.images_list]
            : [];
          if (!list.includes(resultValue) && resultValue && resultValue.trim() !== "") list.push(resultValue);
          updatedFormValues.images_list = list;
        }

        else if (targetHandle === "apiInput2") {
          const list = Array.isArray(updatedFormValues.images)
            ? [...updatedFormValues.images]
            : [];
          if (!list.includes(resultValue) && resultValue && resultValue.trim() !== "") list.push(resultValue);
          updatedFormValues.images = list;
        }

        else if (["textInput2", "videoInput2", "imageInput3", "audioInput3"].includes(targetHandle)) {
          updatedFormValues.image_url = resultValue;
        }

        else if (targetHandle === "apiInput3") {
          updatedFormValues.image = resultValue;
        }

        else if (targetHandle === "videoInput3") {
          updatedFormValues.last_image = resultValue;
        }

        else if (["videoInput4", "audioInput4"].includes(targetHandle)) {
          updatedFormValues.video_url = resultValue;
        }

        else if (targetHandle === "videoInput7") {
          const key = updatedFormValues.video_files ? "video_files" : "videos_list";
          const list = Array.isArray(updatedFormValues[key])
            ? [...updatedFormValues[key]]
            : [];
          if (!list.includes(resultValue) && resultValue && resultValue.trim() !== "") list.push(resultValue);
          updatedFormValues[key] = list;
        }

        else if (targetHandle === "videoInput8") {
          const key = updatedFormValues.audio_files ? "audio_files" : "audios_list";
          const list = Array.isArray(updatedFormValues[key])
            ? [...updatedFormValues[key]]
            : [];
          if (!list.includes(resultValue) && resultValue && resultValue.trim() !== "") list.push(resultValue);
          updatedFormValues[key] = list;
        }

        else if (["videoInput5", "audioInput"].includes(targetHandle)) {
          updatedFormValues.audio_url = resultValue;
        }

        else if (node.type === "apiNode") {
          const listFields = ["images", "image_urls", "images_list"];
          const isList = listFields.includes(targetHandle) || node.data.taskData?.[targetHandle]?.type === "array";

          if (isList) {
            const list = Array.isArray(updatedFormValues[targetHandle])
              ? [...updatedFormValues[targetHandle]]
              : [];
            if (sourceValue && sourceValue.trim() !== "" && !list.includes(sourceValue)) {
              list.push(sourceValue);
            }
            updatedFormValues[targetHandle] = list;
          } else {
            updatedFormValues[targetHandle] = sourceValue;
          }
        }

        return {
          ...node,
          data: {
            ...node.data,
            formValues: updatedFormValues,
          },
        };
      });

      updatedNodes = updatedNodes.map((node) => {
        if (node.type !== "concatNode") return node;

        const allConcatEdges = edges.filter((e) =>
          e.target === node.id && e.targetHandle === "concatInput"
        );

        if (allConcatEdges.length === 0) {
          return {
            ...node,
            data: {
              ...node.data,
              formValues: {
                ...node.data.formValues,
                prompt: "",
              },
            },
          };
        }

        const concatValues = allConcatEdges.map((e) => {
          const sourceNode = updatedNodes.find((n) => n.id === e.source);
          return sourceNode?.data?.resultUrl || sourceNode?.data?.outputs?.[0]?.value || "";
        }).filter((v) => typeof v === "string" && v.trim() !== "");

        return {
          ...node,
          data: {
            ...node.data,
            formValues: {
              ...node.data.formValues,
              prompt: concatValues.length > 0 ? concatValues.join(" ").trim() : "",
            },
          },
        };
      });

      return updatedNodes;
    });

    if (newData.hasOwnProperty('isLoading')) {
      setLoadingNodes(prev => {
        const newLoadingNodes = { ...prev };
        if (newData.isLoading) {
          newLoadingNodes[id] = true;
        } else {
          delete newLoadingNodes[id];
        }
        return newLoadingNodes;
      });
    }
  };

  const onConnect = useCallback(
    (params) => {
      const targetNodeExists = nodes.some(n => n.id === params.target);
      if (targetNodeExists) {
        connectionMadeRef.current = true;
      }
      setEdges((eds) => {
        const sourceNode = nodes.find((n) => n.id === params.source) || {};
        const targetNode = nodes.find((n) => n.id === params.target) || {};
        let color = getEdgeColor(params.sourceHandle, params.targetHandle, sourceNode, targetNode);

        if (color === "blue" && targetNode?.type !== "concatNode" && targetNode.type !== "apiNode") {
          const hasExistingBlueConnection = eds.some(edge => {
            if (edge.target !== params.target) return false;
            // // Allow different handles to coexist even if they are both blue
            if (edge.targetHandle !== params.targetHandle) return false;

            const edgeColor =
              ["textInput", "imageInput", "videoInput", "audioInput2", "concatInput", "textInput4"].includes(edge.targetHandle) ||
                ["textOutput", "concatOutput"].includes(edge.sourceHandle)
                ? "blue"
                : "other";

            return edgeColor === "blue";
          });

          if (hasExistingBlueConnection) {
            return eds;
          }
        }

        const newEdges = addEdge({ ...params, style: edgeStyles[color] }, eds);
        if (!sourceNode || !targetNode || !sourceNode.data) return newEdges;

        const sourceData = sourceNode.data;
        const resultValue = sourceData.viewingOutput !== undefined
          ? sourceData.viewingOutput
          : (sourceData.resultUrl || sourceData.outputs?.[0]?.value || null);
        // if (!resultValue || resultValue.trim() === "") return newEdges;

        const sourceValue = sourceNode?.type === "concatNode"
          ? sourceNode?.data?.formValues?.prompt
          : resultValue;

        setNodes((prev) =>
          prev.map((n) => {
            if (n.id !== targetNode.id) return n;

            let updatedFormValues = { ...n.data.formValues };

            if (n.id === params.target && n.type === "apiNode") {
              const listFields = ["images", "image_urls", "images_list"];
              const isList = listFields.includes(params.targetHandle) || n.data.taskData?.[params.targetHandle]?.type === "array";

              if (isList) {
                const list = Array.isArray(updatedFormValues[params.targetHandle]) ? [...updatedFormValues[params.targetHandle]] : [];
                if (sourceValue && sourceValue.trim() !== "" && !list.includes(sourceValue)) {
                  list.push(sourceValue);
                }
                updatedFormValues[params.targetHandle] = list;
              } else {
                updatedFormValues[params.targetHandle] = sourceValue;
              }
            }

            if (color === "blue") {
              if (targetNode.type === "concatNode" && params.targetHandle === "concatInput") {
                const allConcatEdges = newEdges.filter((e) =>
                  e.target === targetNode.id && e.targetHandle === "concatInput"
                );

                const concatValues = allConcatEdges.map((e) => {
                  if (e.source === params.source) return resultValue;
                  const sourceNode = prev.find((node) => node.id === e.source);
                  return sourceNode?.data?.resultUrl || sourceNode?.data?.outputs?.[0]?.value || "";
                }).filter(v => v);

                updatedFormValues.prompt = concatValues.join(" ");
              }

              else if (["textInput", "imageInput", "videoInput", "audioInput2", "apiInput"].includes(params.targetHandle)) {
                updatedFormValues.prompt = sourceValue || "";
              }
              else if (params.targetHandle === "textInput4") {
                updatedFormValues.system_prompt = sourceValue || "";
              }
            }

            if (color === "green") {
              if (["textInput2", "videoInput2", "imageInput3", "audioInput3"].includes(params.targetHandle)) {
                updatedFormValues.image_url = resultValue || null;
              } else if (["textInput3", "imageInput2", "videoInput6"].includes(params.targetHandle)) {
                const list = Array.isArray(updatedFormValues.images_list) ? [...updatedFormValues.images_list] : [];
                if (!list.includes(resultValue) && resultValue && resultValue.trim() !== "") {
                  list.push(resultValue);
                }
                updatedFormValues.images_list = list;
              } else if (params.targetHandle === "apiInput2") {
                const list = Array.isArray(updatedFormValues.images) ? [...updatedFormValues.images] : [];
                if (!list.includes(resultValue) && resultValue && resultValue.trim() !== "") {
                  list.push(resultValue);
                }
                updatedFormValues.images = list;
              } else if (params.targetHandle === "videoInput3") {
                updatedFormValues.last_image = resultValue || null;
              } else if (params.targetHandle === "apiInput3") {
                updatedFormValues.image = resultValue || null;
              }
            }

            if (color === "orange") {
              if (["videoInput4", "audioInput4"].includes(params.targetHandle)) {
                updatedFormValues.video_url = resultValue || null;
              } else if (params.targetHandle === "videoInput7") {
                const key = updatedFormValues.video_files ? "video_files" : "videos_list";
                const list = Array.isArray(updatedFormValues[key]) ? [...updatedFormValues[key]] : [];
                if (!list.includes(resultValue) && resultValue && resultValue.trim() !== "") {
                  list.push(resultValue);
                }
                updatedFormValues[key] = list;
              }
            }

            if (color === "yellow") {
              if (["audioInput", "videoInput5"].includes(params.targetHandle)) {
                updatedFormValues.audio_url = resultValue !== undefined ? resultValue : null;
              }
              if (params.targetHandle === "videoInput8") {
                const key = updatedFormValues.audio_files ? "audio_files" : "audios_list";
                const list = Array.isArray(updatedFormValues[key]) ? [...updatedFormValues[key]] : [];
                if (!list.includes(resultValue) && resultValue && resultValue.trim() !== "") {
                  list.push(resultValue);
                }
                updatedFormValues[key] = list;
              }
            }

            return {
              ...n,
              data: {
                ...n.data,
                formValues: updatedFormValues,
              },
            };
          })
        );

        return newEdges;
      });
    },
    [nodes]
  );

  const pollArchitectStatus = (request_id) => {
    const interval = setInterval(async () => {
      try {
        const response = await api.get(`/api/workflow/poll-architect/${request_id}/result`);
        const finalData = response.data;
        const status = finalData.status;

        if (status === "completed") {
          clearInterval(interval);
          const { message, suggestions, workflow } = finalData;

          const newAgentMessage = {
            role: "agent",
            content: message || "Tasks complete. Your workflow has been updated.",
            suggestions: suggestions || [],
            timestamp: new Date().toISOString()
          };
          setChatMessages((prev) => [...prev, newAgentMessage]);

          if (workflow && workflow.nodes) {
            const idMapping = {};
            const counts = { text: 0, image: 0, video: 0, audio: 0 };

            const newNodes = workflow.nodes.map((n) => {
              let newId = n.id;
              const category = n.category;

              if (["user_text", "prompt_gen"].includes(n.id) || category === "text") {
                counts.text++;
                newId = `text${counts.text}`;
              } else if (n.id === "image_gen" || category === "image") {
                counts.image++;
                newId = `image${counts.image}`;
              } else if (category === "video") {
                counts.video++;
                newId = `video${counts.video}`;
              } else if (category === "audio") {
                counts.audio++;
                newId = `audio${counts.audio}`;
              }

              idMapping[n.id] = newId;
              const existingNode = nodes.find((en) => en.id === newId);

              return {
                id: newId,
                type: n.category === "utility" ? (n.model === "video-combiner" ? "vidConcatNode" : "concatNode") : `${n.category}Node`,
                position: existingNode?.position || {
                  x: n.position?.x ?? 350,
                  y: n.position?.y ?? 0
                },
                data: {
                  ...existingNode?.data,
                  nodeSchemas,
                  modelId: n.model,
                  selectedModel: getModelObj(n.category, n.model),
                  outputs: n.output_params?.outputs || [],
                  resultUrl: n.output_params?.resultUrl || null,
                  formValues: n.input_params || n.params || {},
                  outputHistory: existingNode?.data?.outputHistory || [],
                }
              };
            });

            setNodes(newNodes);

            if (workflow.edges && workflow.edges.length > 0) {
              const newEdges = workflow.edges.map((e) => {
                const source = idMapping[e.source] || e.source;
                const target = idMapping[e.target] || e.target;

                const sourceNode = newNodes.find(n => n.id === source);
                const targetNode = newNodes.find(n => n.id === target);

                let sourceHandle = e.sourceHandle;
                let targetHandle = e.targetHandle;

                if ((!sourceHandle || sourceHandle === 'output') && sourceNode) {
                  if (sourceNode.type === 'textNode') sourceHandle = 'textOutput';
                  else if (sourceNode.type === 'imageNode') sourceHandle = 'imageOutput';
                  else if (sourceNode.type === 'videoNode') sourceHandle = 'videoOutput';
                  else if (sourceNode.type === 'audioNode') sourceHandle = 'audioOutput';
                  else if (sourceNode.type === 'concatNode') sourceHandle = 'concatOutput';
                }

                if ((!targetHandle || targetHandle === 'prompt') && targetNode) {
                  if (targetNode.type === 'textNode') targetHandle = 'textInput';
                  else if (targetNode.type === 'imageNode') targetHandle = 'imageInput';
                  else if (targetNode.type === 'videoNode') targetHandle = 'videoInput';
                  else if (targetNode.type === 'audioNode') targetHandle = 'audioInput2';
                  else if (targetNode.type === 'concatNode') targetHandle = 'concatInput';
                }

                let edgeColor = getEdgeColor(sourceHandle, targetHandle, sourceNode, targetNode);

                return {
                  id: `e-${source}-${target}`,
                  source,
                  target,
                  sourceHandle,
                  targetHandle,
                  style: edgeStyles[edgeColor],
                };
              });

              setEdges(newEdges);
            }
          }
          setIsChatLoading(false);
        } else if (status === "failed") {
          clearInterval(interval);
          throw new Error("Architect processing failed");
        }
      } catch (error) {
        clearInterval(interval);
        console.error("Polling error:", error);
        const errorMessage = {
          role: "agent",
          content: "Sorry, I encountered an error while updating your workflow.",
          timestamp: new Date().toISOString()
        };
        setChatMessages((prev) => [...prev, errorMessage]);
        setIsChatLoading(false);
      }
    }, 3000);
  };

  const handleSendMessage = async (content) => {
    const newMessage = {
      role: "user",
      content,
      timestamp: new Date().toISOString()
    };
    setChatMessages((prev) => [...prev, newMessage]);

    setIsChatLoading(true);
    try {
      const savedWorkflowId = await handleSaveWorkFlow();

      const history = chatMessages.map(msg => ({
        role: msg.role === "agent" ? "assistant" : msg.role,
        content: msg.content
      }));

      const response = await api.post("/api/workflow/architect", {
        prompt: content,
        workflow_id: savedWorkflowId,
        history: history,
      });

      const { request_id, status } = response.data;
      pollArchitectStatus(request_id);
    } catch (error) {
      console.error("Error sending message:", error);
      const errorMessage = {
        role: "agent",
        content: "Sorry, I encountered an error processing your request.",
        timestamp: new Date().toISOString()
      };
      setChatMessages((prev) => [...prev, errorMessage]);
      setIsChatLoading(false);
    }
  };

  useEffect(() => {
    onConnectRef.current = onConnect;
  }, [onConnect]);

  const onEdgeClick = (event, edge) => {
    event.stopPropagation();
    setEdges((eds) => {
      const updatedEdges = eds.filter((e) => e.id !== edge.id);

      const targetNode = nodes.find((n) => n.id === edge.target);
      if (targetNode?.type === "concatNode" && edge.targetHandle === "concatInput") {
        setNodes((prev) =>
          prev.map((n) => {
            if (n.id !== targetNode.id) return n;
            const remainingConcatEdges = updatedEdges.filter((e) =>
              e.target === targetNode.id && e.targetHandle === "concatInput"
            );

            let updatedFormValues = { ...n.data.formValues };

            if (remainingConcatEdges.length > 0) {
              const concatValues = remainingConcatEdges.map((e) => {
                const sourceNode = prev.find((node) => node.id === e.source);
                return sourceNode?.data?.resultUrl || sourceNode?.data?.outputs?.[0]?.value || "";
              }).filter(v => v);

              updatedFormValues.prompt = concatValues.join(" ");
            } else {
              updatedFormValues.prompt = "";
            }

            return {
              ...n,
              data: {
                ...n.data,
                formValues: updatedFormValues,
              },
            };
          })
        );
      }

      if (targetNode?.type === "vidConcatNode" && edge.targetHandle === "videoInput7") {
        setNodes((prev) =>
          prev.map((n) => {
            if (n.id !== targetNode.id) return n;
            const removedSourceNode = prev.find((node) => node.id === edge.source);
            const removedUrl = removedSourceNode?.data?.resultUrl || removedSourceNode?.data?.outputs?.[0]?.value;
            const remainingVideoEdges = updatedEdges.filter((e) =>
              e.target === targetNode.id && e.targetHandle === "videoInput7"
            );
            const remainingUrls = remainingVideoEdges.map((e) => {
              const src = prev.find((node) => node.id === e.source);
              return src?.data?.resultUrl || src?.data?.outputs?.[0]?.value || "";
            }).filter(v => v);

            let updatedFormValues = { ...n.data.formValues };
            if (remainingUrls.length > 0) {
              const key = updatedFormValues.video_files ? "video_files" : "videos_list";
              updatedFormValues[key] = remainingUrls;
            } else {
              const key = updatedFormValues.video_files ? "video_files" : "videos_list";
              const currentList = Array.isArray(updatedFormValues[key])
                ? updatedFormValues[key].filter(v => v !== removedUrl)
                : [];
              updatedFormValues[key] = currentList;
            }

            return {
              ...n,
              data: { ...n.data, formValues: updatedFormValues },
            };
          })
        );
      }

      return updatedEdges;
    });
  };

  const buildWorkflowPayload = () => {
    const nodeData = nodes.map((node) => {

      const connectedEdges = edges.filter((e) => e.target === node.id);
      const inputNodes = connectedEdges.map((e) => e.source);
      const category = node.type === "textNode" ? "text" : node.type === "imageNode" ? "image" : node.type === "videoNode" ? "video" : node.type === "apiNode" ? "api" : node.type === "audioNode" ? "audio" : "utility";
      const isVideoCombiner = node.type === "vidConcatNode";
      const model = node.data?.selectedModel?.id ? node.data?.selectedModel?.id : category === "utility" ? (isVideoCombiner ? "video-combiner" : "prompt-concatenator") : `${category}-passthrough`;
      const modelSchema = nodeSchemas?.categories?.[category]?.models?.[model]?.input_schema?.schemas?.input_data;
      const inputSchema = modelSchema?.properties || {};
      const wavespeedSchema = nodeSchemas?.categories?.api?.models?.[model]?.input_schema;
      const concatSchema = nodeSchemas?.categories?.utility?.models?.["prompt-concatenator"]?.input_schema;
      const videoCombinerSchema = nodeSchemas?.categories?.utility?.models?.["video-combiner"]?.input_schema?.schemas?.input_data?.properties;
      const formValues = node.data?.formValues || {};

      let dynamicPrompt = "";

      if (node.type === "concatNode") {
        const promptConnections = connectedEdges.filter((e) =>
          ["concatInput"].includes(e.targetHandle)
        );
        dynamicPrompt = promptConnections.length > 0
          ? promptConnections.map((conn) => `{{ ${conn.source}.outputs[0].value }}`)
          : [];
      } else {
        const promptConnections = connectedEdges.filter((e) =>
          ["textInput", "imageInput", "videoInput", "audioInput2", "apiInput"].includes(e.targetHandle)
        );
        dynamicPrompt = promptConnections.length > 0
          ? `{{ ${promptConnections[0].source}.outputs[0].value }}`
          : "";
      }

      const systemPromptConnections = connectedEdges.filter((e) =>
        e.targetHandle === "textInput4"
      );
      const dynamicSystemPrompt =
        systemPromptConnections.length > 0
          ? `{{ ${systemPromptConnections[0].source}.outputs[0].value }}`
          : formValues?.system_prompt || null;

      const imageListConnections = connectedEdges.filter((e) =>
        ["textInput3", "imageInput2", "videoInput6", "apiInput2"].includes(e.targetHandle)
      );

      const dynamicImagesList =
        imageListConnections.length > 0
          ? imageListConnections.map(
            (conn) => `{{ ${conn.source}.outputs[0].value }}`
          )
          : formValues?.images_list || []; // || [node.data?.outputs?.[0]?.value] 

      const imageUrlConnections = connectedEdges.filter((e) =>
        ["textInput2", "videoInput2", "imageInput3", "audioInput3", "apiInput3"].includes(e.targetHandle)
      );

      const videoUrlConnections = connectedEdges.filter((e) =>
        ["videoInput4", "audioInput4"].includes(e.targetHandle)
      );

      const videoListConnections = connectedEdges.filter((e) =>
        e.targetHandle === "videoInput7"
      );

      const audioListConnections = connectedEdges.filter((e) =>
        e.targetHandle === "videoInput8"
      );

      const dynamicVideosKey = formValues?.video_files ? "video_files" : "videos_list";
      const dynamicVideosList =
        videoListConnections.length > 0
          ? videoListConnections.map((conn) => `{{ ${conn.source}.outputs[0].value }}`)
          : formValues[dynamicVideosKey] || [];

      const dynamicAudiosKey = formValues?.audio_files ? "audio_files" : "audios_list";
      const dynamicAudiosList =
        audioListConnections.length > 0
          ? audioListConnections.map((conn) => `{{ ${conn.source}.outputs[0].value }}`)
          : formValues[dynamicAudiosKey] || [];

      const audioUrlConnections = connectedEdges.filter((e) =>
        ["audioInput", "videoInput5"].includes(e.targetHandle)
      );

      const dynamicImageUrl =
        imageUrlConnections.length > 0
          ? `{{ ${imageUrlConnections[0].source}.outputs[0].value }}`
          : formValues?.image_url || null;

      const lastImageConnections = connectedEdges.filter(
        (e) => e.targetHandle === "videoInput3"
      );

      const dynamicVideoUrl =
        videoUrlConnections.length > 0
          ? `{{ ${videoUrlConnections[0].source}.outputs[0].value }}`
          : formValues?.video_url || null;

      const dynamicAudioUrl =
        audioUrlConnections.length > 0
          ? `{{ ${audioUrlConnections[0].source}.outputs[0].value }}`
          : formValues?.audio_url || null;

      const dynamicLastImage =
        lastImageConnections.length > 0
          ? `{{ ${lastImageConnections[0].source}.outputs[0].value }}`
          : formValues?.last_image || null; // || node.data?.outputs?.[0]?.value 

      const localSources = {
        ...formValues,
        prompt: dynamicPrompt ? dynamicPrompt : formValues?.prompt,
        system_prompt: dynamicSystemPrompt,
        images_list: dynamicImagesList,
        images: dynamicImagesList,
        image_urls: dynamicImagesList,
        image_url: dynamicImageUrl,
        video_url: dynamicVideoUrl,
        audio_url: dynamicAudioUrl,
        image: dynamicImageUrl,
        last_image: dynamicLastImage,
        videos_list: dynamicVideosList,
        video_files: dynamicVideosList,
        audios_list: dynamicAudiosList,
        audio_files: dynamicAudiosList,
      };

      if (node.type === "apiNode") {
        const listFields = ["images", "image_urls", "images_list"];
        connectedEdges.forEach((edge) => {
          if (edge.target === node.id) {
            const val = `{{ ${edge.source}.outputs[0].value }}`;
            const isList = listFields.includes(edge.targetHandle) || wavespeedSchema?.[edge.targetHandle]?.type === "array";

            if (isList) {
              if (!Array.isArray(localSources[edge.targetHandle])) {
                localSources[edge.targetHandle] = [];
              }
              if (!localSources[edge.targetHandle].includes(val)) {
                localSources[edge.targetHandle].push(val);
              }
            } else {
              localSources[edge.targetHandle] = val;
            }
          }
        });
      }

      let params = {};
      const input_params = formValues || {};
      let output_params = {};

      if (node.type === "apiNode") {
        for (const [key, meta] of Object.entries(wavespeedSchema)) {
          if (localSources[key] !== undefined && localSources[key] !== null) {
            params[key] = localSources[key];
          } else {
            params[key] = meta.default ?? null;
          }
        }

        const filteredInputParams = Object.fromEntries(
          Object.entries(input_params).filter(([key]) =>
            key !== "model_url" && key !== "api_key" && key !== "model_name" && key !== "model_type"
          )
        );

        params["params"] = filteredInputParams;

        for (const [key, meta] of Object.entries(filteredInputParams)) {
          if (localSources[key] !== undefined && localSources[key] !== null) {
            params.params[key] = localSources[key];
          } else {
            params.params[key] = meta?.default ?? null;
          }
        }
      } else if (node.type === "vidConcatNode") {
        const vcSchema = videoCombinerSchema || { videos_list: { default: [] }, aspect_ratio: { default: "auto" } };
        for (const [key, meta] of Object.entries(vcSchema)) {
          if (localSources[key] !== undefined && localSources[key] !== null) {
            params[key] = localSources[key];
          } else {
            params[key] = meta.default ?? null;
          }
        }
      } else if (node.type === "concatNode") {
        for (const [key, meta] of Object.entries(concatSchema)) {
          if (localSources[key] !== undefined && localSources[key] !== null) {
            params[key] = localSources[key];
          } else {
            params[key] = meta.default ?? null;
          }
        }
      } else {
        for (const [key, meta] of Object.entries(inputSchema)) {
          if (localSources[key] !== undefined && localSources[key] !== null) {
            params[key] = localSources[key];
          } else {
            params[key] = meta.default ?? null;
          }
        }
      }

      if (node.type === "textNode") {
        output_params = {
          resultUrl: node.data?.resultUrl || "",
          outputs: node.data?.outputs || [],
        }
      } else if (["imageNode", "videoNode", "audioNode", "apiNode", "concatNode", "vidConcatNode"].includes(node.type)) {
        output_params = {
          resultUrl: node.data?.resultUrl || null,
          outputs: node.data?.outputs || [],
        }
      }

      return {
        id: node.id,
        category,
        model,
        input_params,
        output_params,
        params,
        position: node.position,
        ...(inputNodes.length > 0 ? { inputs: inputNodes } : {}),
      };
    });

    return {
      workflow_id: interactionMode ? workflowId || null : null,
      source_workflow_id: !interactionMode ? workflowId : null,
      name: workflowName || "Untitled",
      edges: edges,
      data: {
        nodes: nodeData
      },
      is_vadoo: false,
      category: workflowCategory,
    };
  };

  const handleSaveWorkFlow = async () => {
    if (!interactionMode) return;
    const workflowPayload = buildWorkflowPayload();

    try {
      const response = await api.post("/api/workflow/create", workflowPayload);
      console.log("Workflow created:", response.data);
      setDropDown(0);
      setWorkflowIds(response.data.workflow_id, runId);
      setWorkflowId(response.data.workflow_id);
      return response.data.workflow_id;
    } catch (error) {
      console.log(error);
      if (error.response) {
        toast.error(`Failed: ${error.response.data.detail || "Server error"}`);
      } else {
        toast.error(`Error: ${error.message}`);
      }
    }
  };

  const handleDuplicateWorkflow = async () => {
    if (interactionMode) return;
    setIsRunning(3);
    const workflowPayload = buildWorkflowPayload();

    try {
      const response = await api.post("/api/workflow/create", workflowPayload);
      console.log("Workflow created:", response.data);
      const wfId = response.data.workflow_id;
      if (typeof window !== 'undefined' && window.location.hash.startsWith('#/image-studio')) {
        window.location.hash = `#/image-studio?tab=workflows&workflowId=${wfId}`;
      } else {
        window.location.href = `/workflow/${wfId}`;
      }
    } catch (error) {
      console.log(error);
      setIsRunning(0);
      if (error.response) {
        toast.error(`Failed: ${error.response.data.detail || "Server error"}`);
      } else {
        toast.error(`Error: ${error.message}`);
      }
    }
  };

  useEffect(() => {
    const handleBeforeUnload = (e) => {
      handleSaveWorkFlow();
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [handleSaveWorkFlow]);

  const pollRunIdStatus = (runId) => {
    const interval = setInterval(() => {
      api.get(`/api/workflow/run/${runId}/status`)
        .then((response) => {
          const runData = response.data;
          const nodesStatus = runData?.nodes || {};
          setWorkflowIds(workflowId, runId);

          Object.entries(nodesStatus).forEach(([id, runs]) => {
            if (!runs || runs.length === 0) return;

            const latestRun = runs[runs.length - 1];
            const status = latestRun?.status;
            const result = latestRun?.result;
            const outputs = result?.outputs || [];
            const first = outputs?.[0]?.value || "";

            if (status === "processing" || status === "running") {
              setLoadingNodes((prev) => ({ ...prev, [id]: true }));
              return;
            } else {
              setLoadingNodes((prev) => {
                const copy = { ...prev };
                delete copy[id];
                return copy;
              });
            }

            if (status === "succeeded" || status === "completed") {
              setLoadingNodes((prev) => {
                const copy = { ...prev };
                delete copy[id];
                return copy;
              });

              setNodes((prevNodes) => {
                let updatedNodes = prevNodes.map((node) => {
                  const nodeIdMatch = id.toLowerCase().replace(/\s+/g, '') === node.id.toLowerCase().replace(/\s+/g, '');
                  if (!nodeIdMatch || !result) return node;

                  if (["textNode", "imageNode", "videoNode", "audioNode", "concatNode", "apiNode", "vidConcatNode"].includes(node.type)) {
                    const currentHistory = node.data.outputHistory || [];
                    const isAlreadyInHistory = currentHistory.some(h => h.result?.id === result.id);
                    const newHistory = isAlreadyInHistory
                      ? currentHistory.map(h => h.result?.id === result.id ? latestRun : h)
                      : [...currentHistory, latestRun];

                    return {
                      ...node,
                      data: {
                        ...node.data,
                        outputs,
                        resultUrl: first,
                        isLoading: false,
                        errorMsg: null,
                        outputHistory: newHistory,
                      },
                    };
                  }

                  return node;
                });

                updatedNodes = updatedNodes.map((node) => {
                  if (node.id === id) {
                    return node;
                  }
                  return node;
                });

                return updatedNodes;
              });

              onDataChange(id, { outputs, resultUrl: first, isLoading: false });
            } else if (status === "failed") {
