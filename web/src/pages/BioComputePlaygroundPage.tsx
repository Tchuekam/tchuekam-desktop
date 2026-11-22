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
                        : "bg-black/20 border-white/10 text-gray-400 hover:border-white/25"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="backend"
                        value={b.id}
                        checked={selectedBackend === b.id}
                        onChange={() => setSelectedBackend(b.id)}
                        className="accent-emerald-400"
                      />
                      <span className="text-sm font-medium">{b.label}</span>
                    </div>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-mono ${
                        b.id === "finalspark"
                          ? "bg-emerald-400/20 text-emerald-300"
                          : b.id === "biocompute_simulator"
                          ? "bg-blue-400/20 text-blue-300"
                          : "bg-gray-700 text-gray-300"
                      }`}
                    >
                      {b.tag}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <button
            onClick={runExperiment}
            disabled={isRunning}
            className="w-full bg-emerald-500 hover:bg-emerald-400 text-black font-bold py-3 px-4 rounded-lg flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 transition-all disabled:opacity-50"
          >
            {isRunning ? (
              <>
                <RotateCcw className="w-5 h-5 animate-spin" /> RUNNING BIO-EXPERIMENT...
              </>
            ) : (
              <>
                <Play className="w-5 h-5 fill-current" /> RUN EXPERIMENT
              </>
            )}
          </button>
        </div>

        {/* Right 2 Columns: Pipeline & Activity Visualizer */}
        <div className="lg:col-span-2 space-y-6">
          {/* Computation Pipeline Diagram */}
          <div className="bg-white/5 border border-white/10 rounded-xl p-5 backdrop-blur-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-4 flex items-center gap-2">
              <Layers className="w-4 h-4 text-emerald-400" /> COMPUTATION PIPELINE
            </h2>
            <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-black/40 rounded-lg text-xs font-mono text-gray-300 border border-white/10">
              <span className="px-2.5 py-1 bg-white/10 rounded text-emerald-400 font-bold">IMAGE</span>
              <span>→</span>
              <span className="px-2.5 py-1 bg-white/10 rounded">ENCODER</span>
              <span>→</span>
              <span className="px-2.5 py-1 bg-emerald-500/20 border border-emerald-500/40 rounded text-emerald-300 font-bold">
                {selectedBackend.toUpperCase()}
              </span>
              <span>→</span>
              <span className="px-2.5 py-1 bg-white/10 rounded">NEURAL STATE</span>
              <span>→</span>
              <span className="px-2.5 py-1 bg-white/10 rounded">FEATURE EXTRACTION</span>
              <span>→</span>
              <span className="px-2.5 py-1 bg-white/10 rounded">READOUT</span>
              <span>→</span>
              <span className="px-2.5 py-1 bg-emerald-400 text-black rounded font-bold">PREDICTION</span>
            </div>
          </div>

          {/* Live Neural Activity Raster Plot */}
          <div className="bg-white/5 border border-white/10 rounded-xl p-5 backdrop-blur-sm space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400 flex items-center gap-2">
                <Activity className="w-4 h-4 text-emerald-400" /> NEURAL ACTIVITY (SPIKE RASTER & DYNAMICS)
              </h2>
              <span className="text-xs text-emerald-400 font-mono">
                {selectedBackend === "finalspark" ? "● LIVE BIOLOGICAL DATA" : "● SIMULATED NEURAL DATA"}
              </span>
            </div>

            {/* Neural Raster Grid */}
            <div className="bg-black/60 border border-white/10 rounded-lg p-4 h-48 flex flex-col justify-between relative overflow-hidden">
              <div className="absolute inset-0 opacity-10 bg-[radial-gradient(#10b981_1px,transparent_1px)] [background-size:16px_16px]" />

              {Array.from({ length: 8 }, (_, ch) => (
                <div key={ch} className="flex items-center gap-3 relative z-10">
                  <span className="text-[10px] font-mono text-gray-400 w-12">CH {ch.toString().padStart(2, "0")}</span>
                  <div className="flex-1 h-3 bg-white/5 rounded relative overflow-hidden">
                    {/* Render Spikes */}
                    {result?.neural_raster
                      ?.filter((s: RasterSpike) => s.channel === ch || s.channel % 8 === ch)
                      ?.map((spk: RasterSpike, idx: number) => (
                        <div
                          key={idx}
                          className="absolute top-0 bottom-0 w-1 bg-emerald-400 shadow-[0_0_8px_#10b981] animate-pulse"
                          style={{ left: `${(spk.time_ms % 400) / 4}%` }}
                        />
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Results & TchueKAM Analysis */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-xs text-red-300">
              {error}
            </div>
          )}

          {result && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4 text-center">
                <span className="text-xs text-gray-400 uppercase font-semibold">Prediction</span>
                <div className="text-2xl font-extrabold text-emerald-400 mt-1">{result.prediction}</div>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-center">
                <span className="text-xs text-gray-400 uppercase font-semibold">Confidence</span>
                <div className="text-2xl font-extrabold text-white mt-1">{result.confidence}%</div>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-center">
                <span className="text-xs text-gray-400 uppercase font-semibold">Processing Time</span>
                <div className="text-2xl font-extrabold text-white mt-1">{result.processing_time_s}s</div>
              </div>
            </div>
          )}

          {/* Benchmark Table */}
          {result?.benchmark && (
            <div className="bg-white/5 border border-white/10 rounded-xl p-5 backdrop-blur-sm space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-emerald-400" /> BENCHMARK COMPARISON
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-white/10 text-gray-400">
                    <tr>
                      <th className="py-2">Model</th>
                      <th className="py-2">Accuracy</th>
                      <th className="py-2">Samples</th>
                      <th className="py-2">Latency</th>
                      <th className="py-2">Power / Cost Est.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-gray-300 font-mono">
                    {result.benchmark.map((b: BenchmarkItem, idx: number) => (
                      <tr key={idx} className={b.model.includes("BioCompute") ? "text-emerald-400 bg-emerald-500/5 font-bold" : ""}>
                        <td className="py-2.5 flex items-center gap-2">
                          {b.model.includes("BioCompute") && <Sparkles className="w-3.5 h-3.5 text-emerald-400" />}
                          {b.model}
                        </td>
                        <td className="py-2.5">{b.accuracy}</td>
                        <td className="py-2.5">{b.samples}</td>
                        <td className="py-2.5">{b.latency}</td>
                        <td className="py-2.5">{b.power_est}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TchueKAM Agent Analysis Explanation */}
          {result?.tchuekam_analysis && (
            <div className="bg-gradient-to-r from-emerald-950/40 to-black border border-emerald-500/30 rounded-xl p-5 backdrop-blur-sm">
              <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm mb-2">
                <Sparkles className="w-4 h-4" /> TCHUEKAM BIO AGENT EXPLANATION
              </div>
              <p className="text-xs text-gray-300 leading-relaxed font-sans">{result.tchuekam_analysis}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Icon helper
function BarChart3(props: any) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
      <path d="M3 3v18h18" />
      <path d="M18 17V9" />
      <path d="M13 17V5" />
      <path d="M8 17v-3" />
    </svg>
  );
}
