import React from 'react';
import { Check } from 'lucide-react';

export interface SetupProgressProps {
  currentStep: number;
  totalSteps: number;
  requiredSteps: number;
  stepLabels: string[];
}

const REQUIRED_LABELS = ['Administrator', 'Benutzer', 'RAID', 'Dateizugriff'];

const OPTIONAL_LABELS = ['Freigabe', 'VPN', 'Benachrichtigungen', 'Cloud', 'Pi-hole', 'Desktop', 'Mobile'];
const OPTIONAL_START = 5;
const OPTIONAL_END = 11;
const OPTIONAL_COUNT = OPTIONAL_END - OPTIONAL_START + 1;

export function SetupProgress({
  currentStep,
}: SetupProgressProps) {
  // Required phase: steps 0–3
  if (currentStep >= 0 && currentStep <= 3) {
    return (
      <div className="mb-6">
        <p className="text-xs font-medium uppercase tracking-[0.15em] text-slate-400 mb-3">
          Pflichtschritt {currentStep + 1} von {REQUIRED_LABELS.length}
        </p>
        <div className="flex items-start">
          {REQUIRED_LABELS.map((label, index) => {
            const isCompleted = index < currentStep;
            const isCurrent = index === currentStep;

            return (
              <React.Fragment key={label}>
                <div className="flex flex-col items-center gap-1.5 flex-shrink-0">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold border-2 transition-all ${
                      isCompleted
                        ? 'bg-sky-500 border-sky-500 text-white'
                        : isCurrent
                          ? 'border-sky-500 text-sky-400 bg-sky-500/10'
                          : 'border-slate-700 text-slate-500'
                    }`}
                  >
                    {isCompleted ? <Check className="w-3.5 h-3.5" /> : index + 1}
                  </div>
                  <span
                    className={`text-xs text-center leading-tight ${
                      isCurrent
                        ? 'text-sky-400 font-medium'
                        : isCompleted
                          ? 'text-slate-300'
                          : 'text-slate-500'
                    }`}
                  >
                    {label}
                  </span>
                </div>
                {index < REQUIRED_LABELS.length - 1 && (
                  <div
                    className={`flex-1 h-0.5 mx-3 mt-4 transition-all ${
                      index < currentStep ? 'bg-sky-500' : 'bg-slate-700'
                    }`}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    );
  }

  // Optional gate (step 4): no progress indicator
  if (currentStep === 4) {
    return null;
  }

  // Optional phase: steps 5–11
  if (currentStep >= OPTIONAL_START && currentStep <= OPTIONAL_END) {
    const optionalIndex = currentStep - OPTIONAL_START;
    const currentLabel = OPTIONAL_LABELS[optionalIndex] ?? '';
    const progressPercent = ((optionalIndex + 1) / OPTIONAL_COUNT) * 100;

    return (
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium uppercase tracking-[0.15em] text-slate-400">
            Optionaler Schritt {optionalIndex + 1} von {OPTIONAL_COUNT}
          </span>
          <span className="text-sm font-medium text-slate-200">{currentLabel}</span>
        </div>
        <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>
    );
  }

  // Complete or unknown — no progress
  return null;
}
