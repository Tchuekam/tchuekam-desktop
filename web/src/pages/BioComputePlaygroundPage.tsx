import React, { useEffect, useState } from "react";
import { HERMES_BASE_PATH } from "@/lib/api";
import { getStoredSupabaseAccessToken } from "@/lib/supabaseAuth";
import {
  Activity,
  Brain,
  Layers,
  Play,
  RotateCcw,
  Sparkles,
  Upload,
} from "lucide-react";

interface RasterSpike {
  channel: number;
  time_ms: number;
}

interface BenchmarkItem {
  model: string;
  accuracy: string;
  samples: string;
  latency: string;
  power_est: string;
}

export default function BioComputePlaygroundPage() {
  const [selectedBackend, setSelectedBackend] = useState<string>("biocompute_simulator");
  const [selectedTask, setSelectedTask] = useState<string>("Image Classification");
  const [selectedDataset, setSelectedDataset] = useState<string>("MNIST");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const handleFileDrop = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
    }
  };

  const runExperiment = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("backend", selectedBackend);
      formData.append("dataset", selectedDataset);
      formData.append("task", selectedTask);
      if (selectedFile) {
        formData.append("file", selectedFile);
      }

      const headers = new Headers();
      const sessionToken = window.__HERMES_SESSION_TOKEN__;
      if (sessionToken) {
        headers.set("X-Hermes-Session-Token", sessionToken);
      }
      const sbToken = getStoredSupabaseAccessToken();
      if (sbToken) {
        headers.set("Authorization", `Bearer ${sbToken}`);
      }

      const res = await fetch(`${HERMES_BASE_PATH}/api/v1/biocompute/experiment/run`, {
        method: "POST",
        headers,
        credentials: "include",
        body: formData,
      });

      if (!res.ok) {
        const msg = await res.text().catch(() => res.statusText);
        throw new Error(`Experiment execution failed (HTTP ${res.status}): ${msg}`);
      }
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(
        err instanceof Error
          ? err.message
          : "Failed to run BioCompute experiment against backend.",
      );
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="min-h-dvh bg-[#08080c] text-white p-3 sm:p-6 space-y-6 sm:space-y-8 font-sans">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center border-b border-white/10 pb-4 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Brain className="w-8 h-8 text-emerald-400 animate-pulse" />
            <h1 className="text-2xl font-bold tracking-tight">TCHUEKAM / BIOCOMPUTE PLAYGROUND</h1>
          </div>
          <p className="text-sm text-gray-400 mt-1">
            Visual Laboratory for Biological Computing, Spiking Neural Networks & Reservoir Benchmarks
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs rounded-full flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            BIO-ENGINE ONLINE
          </span>
          <span className="px-3 py-1 bg-blue-500/10 border border-blue-500/30 text-blue-400 text-xs rounded-full">
            READ-ONLY SAFETY ACTIVE
          </span>
        </div>
      </div>

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Input & Controls */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-6 backdrop-blur-sm">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-white">
            <Upload className="w-5 h-5 text-emerald-400" /> INPUT EXPERIMENT
          </h2>

          {/* Image Dropzone */}
          <div className="border-2 border-dashed border-white/20 hover:border-emerald-400/50 transition-colors rounded-lg p-6 text-center cursor-pointer relative bg-black/30">
            <input
              type="file"
              accept="image/png, image/jpeg, image/jpg"
              onChange={handleFileDrop}
              className="absolute inset-0 opacity-0 cursor-pointer"
            />
            {previewUrl ? (
              <div className="flex flex-col items-center gap-2">
                <img src={previewUrl} alt="Input" className="w-24 h-24 object-contain rounded border border-white/20" />
                <span className="text-xs text-gray-300">{selectedFile?.name}</span>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-gray-400">
                <Upload className="w-8 h-8 text-gray-400" />
                <span className="text-sm font-medium">Drop Image Here (PNG, JPG)</span>
                <span className="text-xs text-gray-500">Or use default synthetic dataset</span>
              </div>
            )}
          </div>

          {/* Task & Dataset Selectors */}
          <div className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider block mb-1">Task</label>
              <select
                value={selectedTask}
                onChange={(e) => setSelectedTask(e.target.value)}
                className="w-full bg-black/40 border border-white/15 rounded-lg p-2.5 text-sm text-white focus:border-emerald-400 outline-none"
              >
                <option value="Image Classification">Image Classification</option>
                <option value="Time Series Anomaly Detection">Time Series Anomaly Detection</option>
                <option value="Pattern Recognition">Pattern Recognition</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider block mb-1">Dataset</label>
              <select
                value={selectedDataset}
                onChange={(e) => setSelectedDataset(e.target.value)}
                className="w-full bg-black/40 border border-white/15 rounded-lg p-2.5 text-sm text-white focus:border-emerald-400 outline-none"
              >
                <option value="MNIST">MNIST Digits</option>
                <option value="Fashion-MNIST">Fashion-MNIST</option>
                <option value="CIFAR-10">CIFAR-10 (Encoded)</option>
              </select>
            </div>

            {/* Backend Options */}
            <div>
              <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider block mb-2">Computational Backend</label>
              <div className="space-y-2">
                {[
                  { id: "tiny_cnn", label: "Tiny CNN (PyTorch Baseline)", tag: "SILICON" },
                  { id: "digital_reservoir", label: "Digital Reservoir (Echo-State Net)", tag: "ESN" },
                  { id: "biocompute_simulator", label: "BioCompute Simulator (Brian2 SNN)", tag: "SIMULATED" },
                  { id: "finalspark", label: "FinalSpark (Live Organoid MEA)", tag: "LIVE BIOLOGICAL" },
                ].map((b) => (
                  <label
                    key={b.id}
                    className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all ${
                      selectedBackend === b.id
                        ? "bg-emerald-500/10 border-emerald-400 text-white"
