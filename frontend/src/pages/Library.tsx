import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { listWorkflows, deleteWorkflow } from "../api/client";

interface Workflow {
  id: string;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  run_count: number;
}

export default function Library() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const loadWorkflows = () => {
    setLoading(true);
    listWorkflows()
      .then(setWorkflows)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadWorkflows();
  }, []);

  const handleDelete = async (wf: Workflow) => {
    if (!window.confirm(`Delete workflow "${wf.name}"? This cannot be undone.`))
      return;
    try {
      await deleteWorkflow(wf.id);
      loadWorkflows();
    } catch {
      alert("Failed to delete workflow.");
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="animate-spin h-8 w-8 border-4 border-indigo-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Team Library</h2>
        <p className="text-gray-500 mt-1">
          Browse shared workflows and run them on your own documents.
        </p>
      </div>

      {workflows.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-4xl mb-4">📭</p>
          <p>No workflows yet. Be the first to publish one!</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {workflows.map((wf) => (
            <div
              key={wf.id}
              className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 text-lg">
                    {wf.name}
                  </h3>
                  <p className="text-sm text-gray-500 mt-1">{wf.description}</p>
                  <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
                    <span>by {wf.created_by}</span>
                    <span>•</span>
                    <span>{new Date(wf.created_at).toLocaleDateString()}</span>
                    <span>•</span>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded-full font-medium">
                      ▶ {wf.run_count} run{wf.run_count !== 1 ? "s" : ""}
                    </span>
                  </div>
                </div>
                <div className="ml-4 flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleDelete(wf)}
                    className="px-3 py-2.5 text-sm font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100 transition-colors cursor-pointer"
                    title="Delete workflow"
                  >
                    🗑️
                  </button>
                  <button
                    onClick={() => navigate(`/run?workflow=${wf.id}`)}
                    className="px-5 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors cursor-pointer"
                  >
                    Run this workflow →
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
