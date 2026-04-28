"use client";

import { CascadeStep, WIZARD_STEPS } from "@/lib/wizard-types";

export function WizardStepDots({
  completedSteps,
  currentStep,
}: {
  completedSteps: CascadeStep[];
  currentStep: CascadeStep | null;
}) {
  return (
    <div className="flex gap-2.5 items-center mb-1.5">
      {WIZARD_STEPS.map((step) => {
        const done = completedSteps.includes(step);
        const current = currentStep === step;
        return (
          <div
            key={step}
            className={[
              "w-2.5 h-2.5 rounded-full border transition-colors",
              done
                ? "bg-accent border-accent"
                : current
                ? "bg-accent-bright border-accent-bright shadow-[0_0_0_3px_rgba(58,122,184,0.25)]"
                : "bg-transparent border-border2",
            ].join(" ")}
          />
        );
      })}
    </div>
  );
}
