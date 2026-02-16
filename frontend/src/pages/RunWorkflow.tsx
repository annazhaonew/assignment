import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import {
  parseDocument,
  listWorkflows,
  executeRun,
  getRunDownloadUrl,
  getRunEnrichedMdUrl,
} from "../api/client";
import UploadPanel from "../components/UploadPanel";
import WorkflowOutput from "../components/WorkflowOutput";

interface Workflow {
  id: string;
  name: string;
  description: string;
  run_count: number;
}

export default function RunWorkflow() {
  const [searchParams] = useSearchParams();
  const preselectedWorkflow = searchParams.get("workflow") || "";

  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState(preselectedWorkflow);
  const [file, setFile] = useState<File | null>(null);
  const [docId, setDocId] = useState<string | null>(null);
  const [extractedText, setExtractedText] = useState<string | null>(null);
  const [parseStats, setParseStats] = useState<{
    pages: number;
    figures: number;
    tables: number;
    sections: number;
  } | null>(null);
  const [parsing, setParsing] = useState(false);
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<Record<string, unknown> | null>(null);
  const [figureDescriptions, setFigureDescriptions] = useState<
    Array<{ index: number; page: number; caption: string; description: string }>
  >([]);
  const [grounding, setGrounding] = useState<Record<string, unknown> | null>(
    null,
  );
  const [runId, setRunId] = useState<string | null>(null);
  const [hasEnrichedMd, setHasEnrichedMd] = useState(false);
  const [runCount, setRunCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load workflows on mount
  useEffect(() => {
    listWorkflows().then((data) => {
      setWorkflows(data);
      if (!selectedWorkflow && data.length > 0) {
        setSelectedWorkflow(data[0].id);
      }
    });
  }, []);

  // If preselected workflow changes (from Library page)
  useEffect(() => {
    if (preselectedWorkflow) setSelectedWorkflow(preselectedWorkflow);
  }, [preselectedWorkflow]);

  // Handle PDF upload → parse
  const handleFileSelected = async (f: File) => {
    setFile(f);
    setOutput(null);
    setRunId(null);
    setError(null);
    setParsing(true);
    try {
      const result = await parseDocument(f);
      setDocId(result.doc_id);
      setExtractedText(result.text);
      setParseStats({
        pages: result.pages,
        figures: result.figures_detected || 0,
        tables: result.tables_detected || 0,
        sections: result.sections_detected || 0,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to parse PDF";
      setError(msg);
    } finally {
      setParsing(false);
    }
  };

  // Run workflow
  const handleRun = async () => {
    if (!selectedWorkflow || !docId) return;
    setRunning(true);
    setOutput(null);
    setRunId(null);
    setError(null);
    try {
      const result = await executeRun({
        workflow_id: selectedWorkflow,
        doc_id: docId,
      });
      setOutput(result.output);
      setFigureDescriptions(result.figure_descriptions || []);
      setGrounding(result.grounding || null);
      setRunId(result.run_id);
      setHasEnrichedMd(result.has_enriched_md || false);
      setRunCount(result.usage?.workflow_run_count ?? null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Workflow execution failed";
      setError(msg);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Run Workflow</h2>
        <p className="text-gray-500 mt-1">
          Upload a PDF and run an AI workflow to extract structured insights.
        </p>
      </div>

      {/* Step 1: Upload */}
      <UploadPanel
        onFileSelected={handleFileSelected}
        isLoading={parsing}
        fileName={file?.name}
      />

      {/* Parse results summary */}
      {parseStats && docId && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-500">
              📝 Parsed Document
            </h3>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-3">
            <Stat label="Pages" value={parseStats.pages} />
            <Stat
              label="Characters"
              value={extractedText?.length.toLocaleString() || "0"}
            />
            <Stat label="Sections" value={parseStats.sections} />
            <Stat label="Tables" value={parseStats.tables} />
            <Stat label="Figures" value={parseStats.figures} />
          </div>
          <details className="group">
            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
              Show text preview…
            </summary>
            <pre className="mt-2 text-xs text-gray-600 max-h-32 overflow-y-auto whitespace-pre-wrap bg-gray-50 rounded-lg p-3">
              {extractedText?.slice(0, 2000)}…
            </pre>
          </details>
        </div>
      )}

      {/* Step 2: Select workflow + Run */}
      {docId && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select Workflow
            </label>
            <select
              value={selectedWorkflow}
              onChange={(e) => setSelectedWorkflow(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            >
              {workflows.map((wf) => (
                <option key={wf.id} value={wf.id}>
                  {wf.name}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleRun}
            disabled={running || !selectedWorkflow}
            className="w-full bg-indigo-600 text-white py-3 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            {running
              ? "Running… (this may take 1-2 min for full paper)"
              : "▶ Run Workflow"}
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
          ⚠️ {error}
        </div>
      )}

      {/* Output */}
      <WorkflowOutput
        output={output}
        isLoading={running}
        figureDescriptions={figureDescriptions}
        docId={docId}
        grounding={grounding}
      />

      {/* Download + Usage */}
      {output && (
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            {runId && hasEnrichedMd && (
              <a
                href={getRunEnrichedMdUrl(runId)}
                download
                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
              >
                ⬇ Download Enriched Document (.md)
              </a>
            )}
            {runId && (
              <a
                href={getRunDownloadUrl(runId)}
                download
                className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                ⬇ Download Analysis (JSON)
              </a>
            )}
          </div>
          {runCount !== null && (
            <div className="text-sm text-gray-400">
              This workflow has been run{" "}
              <span className="font-semibold text-gray-600">{runCount}</span>{" "}
              time{runCount !== 1 ? "s" : ""}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2 text-center">
      <div className="text-lg font-semibold text-gray-800">{value}</div>
      <div className="text-xs text-gray-400">{label}</div>
    </div>
  );
}
