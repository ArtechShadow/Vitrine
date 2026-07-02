export const WIZARD_STEPS = [
  { id: 1, key: "media", label: "Add Media" },
  { id: 2, key: "review", label: "Review Files" },
  { id: 3, key: "quality", label: "Quality Check" },
  { id: 4, key: "build", label: "Create Archive" },
  { id: 5, key: "alignment", label: "Alignment" },
  { id: 6, key: "view", label: "View Scene" },
  { id: 7, key: "export", label: "Export" },
] as const;

export type WizardStepKey = (typeof WIZARD_STEPS)[number]["key"];

interface WizardProgressProps {
  currentStep: number;
}

export default function WizardProgress({ currentStep }: WizardProgressProps) {
  return (
    <nav className="wizard-progress" aria-label="Archive creation steps">
      <ol>
        {WIZARD_STEPS.map((step) => {
          const state =
            step.id < currentStep ? "done" : step.id === currentStep ? "current" : "upcoming";
          return (
            <li key={step.key} className={`wizard-step wizard-step--${state}`}>
              <span className="wizard-step-num" aria-hidden>
                {step.id < currentStep ? "✓" : step.id}
              </span>
              <span className="wizard-step-label">{step.label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
