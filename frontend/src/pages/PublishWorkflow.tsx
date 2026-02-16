import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createWorkflow } from "../api/client";

const DEFAULT_SCHEMA = JSON.stringify(
  {
    tldr: "string",
    key_findings: ["string"],
    biomarkers: ["string"],
    trial_phase_signals: "Phase I|Phase II|Phase III|Preclinical|Unknown",
    patient_population: ["string"],
    follow_up_hypotheses: ["string"],
    supporting_quotes: ["string"],
    confidence: "low|medium|high",
  },
  null,
  2,
);

const DEFAULT_PROMPT = `You will be given extracted text from a scientific PDF.
Produce a structured analysis as JSON using the exact schema provided.

Rules:
- Return JSON only (no markdown).
- Keep key_findings concise and specific.
- biomarkers: include gene/protein markers, lab measures, and pathway names if relevant.
- trial_phase_signals: infer from text. If not explicit, use Unknown.
- supporting_quotes: include 3-6 short quotes from the input that justify the key findings/phase/biomarkers.
- confidence: low if ambiguous, medium if partial evidence, high if explicit.

SCHEMA:
{schema_json}

PDF_TEXT:
{text}`;

export default function PublishWorkflow() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [promptTemplate, setPromptTemplate] = useState(DEFAULT_PROMPT);
  const [schemaJson, setSchemaJson] = useState(DEFAULT_SCHEMA);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Please provide a workflow name.");
      return;
    }

    // Validate JSON schema
    try {
      JSON.parse(schemaJson);
    } catch {
      setError("Output schema must be valid JSON.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await createWorkflow({
        name: name.trim(),
        description: description.trim(),
        prompt_template: promptTemplate,
        output_schema_json: schemaJson,
      });
      navigate("/library");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to publish workflow";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Publish Workflow</h2>
        <p className="text-gray-500 mt-1">
          Create a reusable workflow and share it with your team.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-xl border border-gray-200 p-6 space-y-5"
      >
        {/* Name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Workflow Name *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Clinical Paper Triage → Summary, Biomarkers, Trial Phase"
            className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Description
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What does this workflow do?"
            className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        {/* Prompt Template */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Prompt Template
            <span className="text-xs text-gray-400 ml-2">
              Use {"{schema_json}"} and {"{text}"} as placeholders
            </span>
          </label>
          <textarea
            value={promptTemplate}
            onChange={(e) => setPromptTemplate(e.target.value)}
            rows={12}
            className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        {/* Output Schema */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Output Schema (JSON)
          </label>
          <textarea
            value={schemaJson}
            onChange={(e) => setSchemaJson(e.target.value)}
            rows={8}
            className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">
            ⚠️ {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-indigo-600 text-white py-3 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
        >
          {submitting ? "Publishing…" : "📤 Publish to Team Library"}
        </button>
      </form>
    </div>
  );
}
