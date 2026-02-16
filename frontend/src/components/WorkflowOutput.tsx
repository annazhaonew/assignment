import { getFigureImageUrl } from "../api/client";

interface FigureDescription {
  index: number;
  page: number;
  caption: string;
  description: string;
}

interface GroundingVerdict {
  claim?: string;
  grounded?: boolean | null;
  severity?: "ok" | "warning" | "error";
  reason?: string;
  score?: number;
  quote?: string;
  finding?: string;
  statistical_evidence?: string;
  found?: string[];
  missing?: string[];
  detail?: string;
}

interface GroundingResult {
  overall_score: number;
  overall_status: "grounded" | "partially_grounded" | "review_needed";
  total_claims: number;
  grounded_claims: number;
  warnings: number;
  errors: number;
  corrections_applied?: {
    type: string;
    action: string;
    original: string;
    corrected?: string | null;
  }[];
  correction_rounds?: number;
  details: {
    key_findings?: GroundingVerdict[];
    supporting_quotes?: GroundingVerdict[];
    safety_claims?: GroundingVerdict[];
    statistical_evidence?: GroundingVerdict[];
  };
}

interface WorkflowOutputProps {
  output: Record<string, unknown> | null;
  isLoading: boolean;
  figureDescriptions?: FigureDescription[];
  docId?: string | null;
  grounding?: Record<string, unknown> | null;
}

export default function WorkflowOutput({
  output,
  isLoading,
  figureDescriptions = [],
  docId = null,
  grounding = null,
}: WorkflowOutputProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin h-8 w-8 border-4 border-indigo-500 border-t-transparent rounded-full" />
          <p className="text-sm text-indigo-600 font-medium">
            Running workflow with Azure OpenAI…
          </p>
          <p className="text-xs text-gray-400">
            Full paper analysis may take 1–2 minutes
          </p>
        </div>
      </div>
    );
  }

  if (!output) return null;

  const o = output as Record<string, unknown>;

  // Detect schema: deep analysis has "paper_metadata" or "study_design"
  const isDeepAnalysis = "paper_metadata" in o || "study_design" in o;

  if (isDeepAnalysis) {
    return (
      <DeepAnalysisView
        o={o}
        figureDescriptions={figureDescriptions}
        docId={docId}
        grounding={grounding as GroundingResult | null}
      />
    );
  }
  return <TriageView o={o} grounding={grounding as GroundingResult | null} />;
}

/* ─── Clinical Paper Triage (flat schema) ─── */
function TriageView({
  o,
  grounding,
}: {
  o: Record<string, unknown>;
  grounding?: GroundingResult | null;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
      {/* Grounding Validation Banner */}
      {grounding && <GroundingBanner grounding={grounding} />}

      {o.tldr ? (
        <Section title="📋 TL;DR">
          <p className="text-gray-700">{String(o.tldr)}</p>
        </Section>
      ) : null}
      {renderStringList(o.key_findings, "🔬 Key Findings")}
      {renderPills(o.biomarkers, "🧬 Biomarkers")}

      <Section title="⚗️ Trial Phase & Confidence">
        <div className="flex gap-4">
          <Badge
            label="Phase"
            value={String(o.trial_phase_signals || "Unknown")}
            color="blue"
          />
          <Badge
            label="Confidence"
            value={String(o.confidence || "N/A")}
            color={
              o.confidence === "high"
                ? "green"
                : o.confidence === "medium"
                  ? "yellow"
                  : "red"
            }
          />
        </div>
      </Section>

      {renderStringList(o.patient_population, "👥 Patient Population")}
      {renderStringList(o.follow_up_hypotheses, "💡 Follow-up Hypotheses")}

      {Array.isArray(o.supporting_quotes) && o.supporting_quotes.length > 0 && (
        <Section title="📌 Supporting Quotes">
          <div className="space-y-2">
            {o.supporting_quotes.map((q: string, i: number) => (
              <blockquote
                key={i}
                className="border-l-3 border-indigo-300 pl-4 text-sm text-gray-600 italic"
              >
                &ldquo;{q}&rdquo;
              </blockquote>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

/* ─── Deep Paper Analysis (nested schema) ─── */
function DeepAnalysisView({
  o,
  figureDescriptions = [],
  docId,
  grounding,
}: {
  o: Record<string, unknown>;
  figureDescriptions?: FigureDescription[];
  docId?: string | null;
  grounding?: GroundingResult | null;
}) {
  const meta = o.paper_metadata as Record<string, unknown> | undefined;
  const design = o.study_design as Record<string, unknown> | undefined;
  const findings = o.key_findings as
    | Array<{
        finding: string;
        statistical_evidence: string;
        clinical_significance: string;
      }>
    | undefined;
  const bio = o.biomarkers_and_endpoints as
    | Array<{ name: string; type: string; result: string }>
    | undefined;
  const figs = o.figures_and_tables_summary as
    | Array<{ reference: string; description: string; key_data: string }>
    | undefined;
  const safety = o.safety_profile as Record<string, unknown> | undefined;

  return (
    <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
      {/* Grounding Validation Banner */}
      {grounding && <GroundingBanner grounding={grounding} />}

      {/* TL;DR */}
      {o.tldr ? (
        <Section title="📋 TL;DR">
          <p className="text-gray-700">{String(o.tldr)}</p>
        </Section>
      ) : null}

      {/* Paper Metadata */}
      {meta && (
        <Section title="📄 Paper Metadata">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <KV label="Title" value={meta.title} />
            <KV
              label="Authors"
              value={
                Array.isArray(meta.authors)
                  ? (meta.authors as string[]).join(", ")
                  : meta.authors
              }
            />
            <KV label="Journal" value={meta.journal} />
            <KV label="Year" value={meta.year} />
            <KV label="DOI" value={meta.doi} />
          </div>
        </Section>
      )}

      {/* Study Design */}
      {design && (
        <Section title="🧪 Study Design">
          <div className="space-y-2 text-sm text-gray-700">
            <KV label="Objective" value={design.objective} />
            <KV label="Methodology" value={design.methodology} />
            <KV label="Sample Size" value={design.sample_size} />
            <KV label="Duration" value={design.duration} />
            {renderStringList(
              design.inclusion_criteria,
              "Inclusion Criteria",
              true,
            )}
            {renderStringList(
              design.exclusion_criteria,
              "Exclusion Criteria",
              true,
            )}
          </div>
        </Section>
      )}

      {/* Key Findings */}
      {Array.isArray(findings) && findings.length > 0 && (
        <Section title="🔬 Key Findings">
          <div className="space-y-3">
            {findings.map((f, i) => {
              const findingVerdict = grounding?.details?.key_findings?.[i];
              const statVerdict = grounding?.details?.statistical_evidence?.[i];
              return (
                <div key={i} className="bg-gray-50 rounded-lg p-3 text-sm">
                  <div className="flex items-start gap-2">
                    {findingVerdict && (
                      <GroundingIndicator
                        severity={findingVerdict.severity}
                        reason={findingVerdict.reason}
                      />
                    )}
                    <div className="flex-1">
                      <p className="font-medium text-gray-800">{f.finding}</p>
                      {f.statistical_evidence && (
                        <div className="flex items-center gap-1.5 mt-1">
                          {statVerdict &&
                            statVerdict.grounded !== null &&
                            statVerdict.grounded !== undefined && (
                              <GroundingIndicator
                                severity={statVerdict.grounded ? "ok" : "error"}
                                reason={
                                  statVerdict.missing &&
                                  statVerdict.missing.length > 0
                                    ? `Not found in paper: ${statVerdict.missing.join(", ")}`
                                    : statVerdict.grounded
                                      ? `All stats verified (${statVerdict.found?.length || 0} matched)`
                                      : "Statistical values not found in source"
                                }
                              />
                            )}
                          <p className="text-indigo-600 text-xs font-mono">
                            📊 {f.statistical_evidence}
                          </p>
                        </div>
                      )}
                      {f.clinical_significance && (
                        <p className="text-gray-600 text-xs mt-1">
                          💡 {f.clinical_significance}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* Biomarkers & Endpoints */}
      {Array.isArray(bio) && bio.length > 0 && (
        <Section title="🧬 Biomarkers & Endpoints">
          <div className="space-y-2">
            {bio.map((b, i) => (
              <div key={i} className="flex items-start gap-3 text-sm">
                <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded text-xs font-medium whitespace-nowrap">
                  {b.type}
                </span>
                <div>
                  <span className="font-medium text-gray-800">{b.name}</span>
                  {b.result && (
                    <span className="text-gray-500 ml-2">— {b.result}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Figures & Tables Summary */}
      {figureDescriptions.length > 0 && docId && (
        <Section title="📊 Figures & Tables">
          <div className="space-y-4">
            {/* Extracted figure images with GPT-4o vision descriptions */}
            {figureDescriptions.map((fd, i) => {
              /* Find matching LLM summary by page/content to get the paper's own label */
              const matchedSummary = Array.isArray(figs)
                ? figs.find((f) => {
                    const ref = f.reference?.toLowerCase() || "";
                    const desc = fd.description?.toLowerCase() || "";
                    // Match by figure number or content keywords
                    return (
                      ref.includes("figure") &&
                      desc.length > 0 &&
                      ((ref.includes("prisma") && desc.includes("prisma")) ||
                        (ref.includes("forest") && desc.includes("forest")) ||
                        (ref.includes("survival") &&
                          desc.includes("survival")) ||
                        (ref.includes("bias") && desc.includes("bias")) ||
                        (ref.includes("toxicit") && desc.includes("toxicit")) ||
                        (ref.includes("hematol") && desc.includes("hematol")))
                    );
                  })
                : undefined;

              const label = matchedSummary?.reference || `Figure ${i + 1}`;

              return (
                <div
                  key={`fig-img-${fd.index}`}
                  className="bg-gradient-to-r from-indigo-50 to-white rounded-lg p-4 text-sm border border-indigo-100"
                >
                  <div className="flex items-center gap-2 mb-3">
                    <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded text-xs font-semibold">
                      {label}
                    </span>
                    <span className="text-xs text-gray-400">
                      Page {fd.page}
                    </span>
                  </div>
                  <img
                    src={getFigureImageUrl(docId, fd.index)}
                    alt={`${label} from page ${fd.page}`}
                    className="rounded-lg border border-gray-200 max-w-full mb-3"
                    loading="lazy"
                  />
                  {fd.caption && (
                    <p className="text-xs text-gray-500 italic mb-1">
                      {fd.caption}
                    </p>
                  )}
                  <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {fd.description}
                  </p>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* Safety Profile */}
      {safety ? (
        <Section title="⚠️ Safety Profile">
          {renderStringList(safety.adverse_events, "Adverse Events", true)}
          {renderStringList(
            safety.serious_adverse_events,
            "Serious Adverse Events",
            true,
          )}
          <KV
            label="Discontinuation Rate"
            value={safety.discontinuation_rate}
          />
        </Section>
      ) : null}

      {/* Limitations */}
      {renderStringList(o.limitations, "⚡ Limitations")}

      {/* Clinical Implications */}
      {typeof o.clinical_implications === "string" && (
        <Section title="🏥 Clinical Implications">
          <p className="text-gray-700">{o.clinical_implications}</p>
        </Section>
      )}
      {Array.isArray(o.clinical_implications) && (
        <>
          {renderStringList(
            o.clinical_implications,
            "🏥 Clinical Implications",
          )}
        </>
      )}

      {/* Follow-up Hypotheses */}
      {renderStringList(o.follow_up_hypotheses, "💡 Follow-up Hypotheses")}

      {/* Supporting Quotes */}
      {Array.isArray(o.supporting_quotes) && o.supporting_quotes.length > 0 && (
        <Section title="📌 Supporting Quotes">
          <div className="space-y-2">
            {(o.supporting_quotes as string[]).map((q, i) => {
              const quoteVerdict = grounding?.details?.supporting_quotes?.[i];
              return (
                <div key={i} className="flex items-start gap-2">
                  {quoteVerdict && (
                    <div className="mt-1">
                      <GroundingIndicator
                        severity={
                          quoteVerdict.grounded === true
                            ? "ok"
                            : quoteVerdict.grounded === false
                              ? "error"
                              : "warning"
                        }
                        reason={
                          quoteVerdict.grounded === true
                            ? `Quote found in paper (${Math.round((quoteVerdict.score || 0) * 100)}% match)`
                            : quoteVerdict.grounded === false
                              ? "Quote not found in source paper"
                              : "Could not verify"
                        }
                      />
                    </div>
                  )}
                  <blockquote className="border-l-3 border-indigo-300 pl-4 text-sm text-gray-600 italic flex-1">
                    &ldquo;{q}&rdquo;
                  </blockquote>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* Confidence */}
      {o.confidence ? (
        <Section title="🎯 Confidence">
          <Badge
            label="Confidence"
            value={String(o.confidence)}
            color={
              o.confidence === "high"
                ? "green"
                : o.confidence === "medium"
                  ? "yellow"
                  : "red"
            }
          />
        </Section>
      ) : null}
    </div>
  );
}

/* ─── Reusable rendering helpers ─── */

function renderStringList(
  data: unknown,
  title: string,
  inline = false,
): React.ReactNode | null {
  if (!Array.isArray(data) || data.length === 0) return null;
  if (inline) {
    return (
      <div className="mb-2">
        <span className="text-xs font-semibold text-gray-500 uppercase">
          {title}
        </span>
        <ul className="list-disc list-inside space-y-1 text-gray-700 mt-1">
          {data.map((item: string, i: number) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </div>
    );
  }
  return (
    <Section title={title}>
      <ul className="list-disc list-inside space-y-1 text-gray-700">
        {data.map((item: string, i: number) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </Section>
  );
}

function renderPills(
  data: unknown,
  title: string,
  inline = false,
): React.ReactNode | null {
  if (!Array.isArray(data) || data.length === 0) return null;
  const content = (
    <div className="flex flex-wrap gap-2">
      {data.map((item: string, i: number) => (
        <span
          key={i}
          className="px-3 py-1 bg-emerald-50 text-emerald-700 rounded-full text-sm font-medium"
        >
          {item}
        </span>
      ))}
    </div>
  );
  if (inline) {
    return (
      <div className="mb-2">
        <span className="text-xs font-semibold text-gray-500 uppercase">
          {title}
        </span>
        <div className="mt-1">{content}</div>
      </div>
    );
  }
  return <Section title={title}>{content}</Section>;
}

function KV({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div>
      <span className="text-xs font-semibold text-gray-500">{label}</span>
      <p className="text-gray-700">{String(value)}</p>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="px-6 py-4">
      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
        {title}
      </h3>
      {children}
    </div>
  );
}

function Badge({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  const colors: Record<string, string> = {
    blue: "bg-blue-50 text-blue-700",
    green: "bg-green-50 text-green-700",
    yellow: "bg-yellow-50 text-yellow-700",
    red: "bg-red-50 text-red-700",
  };
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-400">{label}:</span>
      <span
        className={`px-3 py-1 rounded-full text-sm font-medium ${colors[color] || colors.blue}`}
      >
        {value}
      </span>
    </div>
  );
}

/* ─── Grounding Validation Components ─── */

function GroundingBanner({ grounding }: { grounding: GroundingResult }) {
  const statusConfig = {
    grounded: {
      icon: "✅",
      label: "Grounded",
      bg: "bg-green-50 border-green-200",
      text: "text-green-800",
      subtext: "text-green-600",
      barColor: "bg-green-500",
      description: "All claims verified against source paper",
    },
    partially_grounded: {
      icon: "⚠️",
      label: "Partially Grounded",
      bg: "bg-amber-50 border-amber-200",
      text: "text-amber-800",
      subtext: "text-amber-600",
      barColor: "bg-amber-500",
      description: "Some claims could not be fully verified",
    },
    review_needed: {
      icon: "❌",
      label: "Review Needed",
      bg: "bg-red-50 border-red-200",
      text: "text-red-800",
      subtext: "text-red-600",
      barColor: "bg-red-500",
      description:
        "Multiple claims could not be verified — manual review required",
    },
  };

  const config =
    statusConfig[grounding.overall_status] || statusConfig.review_needed;
  const scorePercent = Math.round(grounding.overall_score * 100);

  return (
    <div className={`px-6 py-4 ${config.bg} border-b`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{config.icon}</span>
          <div>
            <h3 className={`text-sm font-bold ${config.text}`}>
              Grounding Validation: {config.label}
            </h3>
            <p className={`text-xs ${config.subtext}`}>{config.description}</p>
          </div>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold ${config.text}`}>
            {scorePercent}%
          </div>
          <div className={`text-xs ${config.subtext}`}>grounding score</div>
        </div>
      </div>

      {/* Score bar */}
      <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
        <div
          className={`${config.barColor} h-2 rounded-full transition-all duration-500`}
          style={{ width: `${scorePercent}%` }}
        />
      </div>

      {/* Stats row */}
      <div className="flex gap-4 text-xs">
        <span className={config.subtext}>
          <strong>{grounding.grounded_claims}</strong>/{grounding.total_claims}{" "}
          claims grounded
        </span>
        {grounding.warnings > 0 && (
          <span className="text-amber-600">
            ⚠ {grounding.warnings} warning{grounding.warnings !== 1 ? "s" : ""}
          </span>
        )}
        {grounding.errors > 0 && (
          <span className="text-red-600">
            ✗ {grounding.errors} error{grounding.errors !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Self-correction summary */}
      {grounding.corrections_applied &&
        grounding.corrections_applied.length > 0 && (
          <div className="mt-2 px-3 py-2 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-center gap-2 text-xs font-semibold text-blue-800">
              <span>🔧</span>
              <span>
                Self-correction applied: {grounding.corrections_applied.length}{" "}
                claim{grounding.corrections_applied.length !== 1 ? "s" : ""}{" "}
                auto-fixed
                {grounding.correction_rounds
                  ? ` (${grounding.correction_rounds} round${grounding.correction_rounds !== 1 ? "s" : ""})`
                  : ""}
              </span>
            </div>
            <details className="mt-1 group">
              <summary className="text-xs text-blue-600 cursor-pointer hover:underline">
                View corrections…
              </summary>
              <div className="mt-1 space-y-1 text-xs">
                {grounding.corrections_applied.map(
                  (
                    c: {
                      action: string;
                      original: string;
                      corrected?: string | null;
                      type: string;
                    },
                    i: number,
                  ) => (
                    <div key={i} className="ml-4 flex items-start gap-1.5">
                      <span>{c.action === "corrected" ? "✏️" : "🗑️"}</span>
                      <div>
                        <span className="text-red-600 line-through">
                          {c.original}
                        </span>
                        {c.action === "corrected" && c.corrected && (
                          <>
                            <span className="text-gray-400 mx-1">→</span>
                            <span className="text-green-700">
                              {c.corrected}
                            </span>
                          </>
                        )}
                        {c.action === "removed" && (
                          <span className="text-gray-500 italic ml-1">
                            (removed — unsupported by source)
                          </span>
                        )}
                      </div>
                    </div>
                  ),
                )}
              </div>
            </details>
          </div>
        )}

      {/* Expandable details */}
      <details className="mt-2 group">
        <summary
          className={`text-xs ${config.subtext} cursor-pointer hover:underline`}
        >
          View detailed verification report…
        </summary>
        <div className="mt-2 space-y-3 text-xs">
          {/* Statistical evidence */}
          {grounding.details.statistical_evidence &&
            grounding.details.statistical_evidence.length > 0 && (
              <div>
                <h4 className="font-semibold text-gray-700 mb-1">
                  📊 Statistical Evidence Verification
                </h4>
                {grounding.details.statistical_evidence.map((s, i) => (
                  <div key={i} className="ml-4 mb-1 flex items-start gap-1.5">
                    <span>
                      {s.grounded === true
                        ? "✅"
                        : s.grounded === false
                          ? "❌"
                          : "➖"}
                    </span>
                    <div>
                      <span className="text-gray-700">
                        {s.finding || s.statistical_evidence}
                      </span>
                      {s.found && s.found.length > 0 && (
                        <span className="text-green-600 ml-1">
                          Found: {s.found.join(", ")}
                        </span>
                      )}
                      {s.missing && s.missing.length > 0 && (
                        <span className="text-red-600 ml-1">
                          Missing: {s.missing.join(", ")}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

          {/* Semantic claim verdicts */}
          {grounding.details.key_findings &&
            grounding.details.key_findings.length > 0 && (
              <div>
                <h4 className="font-semibold text-gray-700 mb-1">
                  🔬 Claim Verification (LLM-as-Judge)
                </h4>
                {grounding.details.key_findings.map((v, i) => (
                  <div key={i} className="ml-4 mb-1 flex items-start gap-1.5">
                    <span>
                      {v.severity === "ok"
                        ? "✅"
                        : v.severity === "error"
                          ? "❌"
                          : "⚠️"}
                    </span>
                    <div>
                      <span className="text-gray-700">{v.claim}</span>
                      {v.reason && (
                        <span className="text-gray-500 ml-1 italic">
                          — {v.reason}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

          {/* Quote verification */}
          {grounding.details.supporting_quotes &&
            grounding.details.supporting_quotes.length > 0 && (
              <div>
                <h4 className="font-semibold text-gray-700 mb-1">
                  📌 Quote Verification
                </h4>
                {grounding.details.supporting_quotes.map((q, i) => (
                  <div key={i} className="ml-4 mb-1 flex items-start gap-1.5">
                    <span>
                      {q.grounded === true
                        ? "✅"
                        : q.grounded === false
                          ? "❌"
                          : "⚠️"}
                    </span>
                    <span className="text-gray-600 italic">
                      &ldquo;{q.quote}&rdquo;
                    </span>
                    <span className="text-gray-400">
                      ({Math.round((q.score || 0) * 100)}% match)
                    </span>
                  </div>
                ))}
              </div>
            )}

          {/* Safety claims */}
          {grounding.details.safety_claims &&
            grounding.details.safety_claims.length > 0 && (
              <div>
                <h4 className="font-semibold text-gray-700 mb-1">
                  ⚠️ Safety Claim Verification
                </h4>
                {grounding.details.safety_claims.map((s, i) => (
                  <div key={i} className="ml-4 mb-1 flex items-start gap-1.5">
                    <span>
                      {s.severity === "ok"
                        ? "✅"
                        : s.severity === "error"
                          ? "❌"
                          : "⚠️"}
                    </span>
                    <span className="text-gray-700">{s.claim}</span>
                    {s.reason && (
                      <span className="text-gray-500 ml-1 italic">
                        — {s.reason}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
        </div>
      </details>
    </div>
  );
}

function GroundingIndicator({
  severity,
  reason,
}: {
  severity?: "ok" | "warning" | "error";
  reason?: string;
}) {
  if (!severity) return null;

  const config = {
    ok: {
      icon: "✓",
      color: "text-green-600",
      bg: "bg-green-100",
      title: "Grounded",
    },
    warning: {
      icon: "?",
      color: "text-amber-600",
      bg: "bg-amber-100",
      title: "Unverified",
    },
    error: {
      icon: "✗",
      color: "text-red-600",
      bg: "bg-red-100",
      title: "Not found",
    },
  };

  const c = config[severity] || config.warning;

  return (
    <span
      className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold ${c.color} ${c.bg} shrink-0 cursor-help`}
      title={reason || c.title}
    >
      {c.icon}
    </span>
  );
}
