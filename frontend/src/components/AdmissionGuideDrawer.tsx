import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { VERDICT_LABELS, VERDICT_STYLES } from "../lib/verdictDisplay";
import type { ProgramDetail, QueryResult } from "../types";

interface AdmissionGuideDrawerProps {
  programId: number | null;
  verdict: Pick<QueryResult, "eligibility_verdict" | "eligibility_reasoning"> | null;
  program: ProgramDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
}

export function AdmissionGuideDrawer({
  programId, verdict, program, isLoading, isError, onClose,
}: AdmissionGuideDrawerProps) {
  return (
    <Dialog.Root open={programId !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30" />
        <Dialog.Content className="fixed right-0 top-0 h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold">Admission guide</Dialog.Title>
            <Dialog.Close aria-label="Close" className="text-slate-400 hover:text-slate-700">
              <X size={18} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            Eligibility and admission requirements for this program.
          </Dialog.Description>

          {isError && <p className="text-sm text-red-600">Couldn't load this program's details.</p>}
          {isLoading && <p className="text-sm text-slate-500">Loading...</p>}

          {!isLoading && !isError && program && (
            <div className="space-y-4">
              <a
                href={program.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-blue-600 hover:underline"
              >
                View program page ↗
              </a>

              {verdict && (
                <div>
                  <h3 className="text-sm font-medium text-slate-900">Eligibility</h3>
                  <span
                    className={`mt-1 inline-flex rounded-full px-2 py-1 text-xs font-medium ${VERDICT_STYLES[verdict.eligibility_verdict]}`}
                  >
                    {VERDICT_LABELS[verdict.eligibility_verdict]}
                  </span>
                  <p className="mt-1 text-sm text-slate-600">{verdict.eligibility_reasoning ?? "No reasoning available."}</p>
                </div>
              )}

              {program.structured_eligibility && (
                <StructuredAdmissionGuide eligibility={program.structured_eligibility} />
              )}

              <div>
                <h3 className="text-sm font-medium text-slate-900">Original program details</h3>
                <div className="mt-1">
                  <RawAdmissionText rawSections={program.raw_sections} />
                </div>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function StructuredAdmissionGuide({
  eligibility,
}: {
  eligibility: NonNullable<ProgramDetail["structured_eligibility"]>;
}) {
  return (
    <div className="space-y-3">
      {eligibility.grade_requirement && (
        <RequirementRow
          label={`Grade requirement: ${eligibility.grade_requirement.value ?? "?"} (${eligibility.grade_requirement.scale ?? "scale not stated"})`}
          quote={eligibility.grade_requirement.source_quote}
        />
      )}
      {(eligibility.language_requirements ?? []).map((req, index) => (
        <RequirementRow
          key={`${req.language}-${index}`}
          label={`${req.language}: ${req.level ?? "No minimum level required"}`}
          quote={req.source_quote}
        />
      ))}
      {(eligibility.standardized_tests ?? []).map((test, index) => (
        <RequirementRow
          key={`${test.test}-${index}`}
          label={`${test.test}: ${test.required ? "required" : "not required"}${test.eligibility_condition ? ` (${test.eligibility_condition})` : ""}`}
          quote={test.source_quote}
        />
      ))}
      {eligibility.degree_prerequisite && (
        <RequirementRow label={eligibility.degree_prerequisite.description} quote={eligibility.degree_prerequisite.source_quote} />
      )}
    </div>
  );
}

function RequirementRow({ label, quote }: { label: string; quote: string | null }) {
  return (
    <div className="rounded-lg border border-slate-100 p-3">
      <p className="text-sm font-medium text-slate-900">{label}</p>
      {quote && <p className="mt-1 text-xs italic text-slate-500">"{quote}"</p>}
    </div>
  );
}

function RawAdmissionText({ rawSections }: { rawSections: Record<string, string> }) {
  const sections = Object.entries(rawSections).filter(([, text]) => text);
  if (sections.length === 0) {
    return <p className="text-sm text-slate-500">No admission text available for this program.</p>;
  }
  return (
    <div className="space-y-3">
      {sections.map(([key, text]) => (
        <div key={key}>
          <h4 className="text-xs font-medium uppercase text-slate-400">{key.replace(/_/g, " ")}</h4>
          <p className="text-sm text-slate-700">{text}</p>
        </div>
      ))}
    </div>
  );
}
