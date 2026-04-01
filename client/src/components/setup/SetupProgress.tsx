import React from 'react';
import { Check } from 'lucide-react';

export interface SetupProgressProps {
  currentStep: number;
  totalSteps: number;
  requiredSteps: number;
  stepLabels: string[];
}

export function SetupProgress({
  currentStep,
  totalSteps,
  requiredSteps,
  stepLabels,
}: SetupProgressProps) {
  return (
    <div className="w-full mb-8">
      <div className="flex items-center justify-between">
        {stepLabels.map((label, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;
          const isRequired = index < requiredSteps;
          const isOptional = !isRequired;

          return (
            <React.Fragment key={index}>
              <div className="flex flex-col items-center gap-1 flex-shrink-0">
                <div
                  className={`
                    w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold border-2 transition-all
                    ${isCompleted
                      ? 'bg-blue-600 border-blue-600 text-white'
                      : isCurrent
                        ? 'bg-transparent border-blue-500 text-blue-400'
                        : 'bg-transparent border-gray-600 text-gray-500'
                    }
                  `}
                >
                  {isCompleted ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <span>{index + 1}</span>
                  )}
                </div>
                <span
                  className={`text-xs text-center max-w-[72px] leading-tight ${
                    isCurrent
                      ? 'text-blue-400 font-medium'
                      : isCompleted
                        ? 'text-gray-300'
                        : 'text-gray-500'
                  }`}
                >
                  {label}
                </span>
                {isOptional && (
                  <span className="text-xs text-gray-600 italic">optional</span>
                )}
              </div>

              {index < totalSteps - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-2 transition-all ${
                    index < currentStep ? 'bg-blue-600' : 'bg-gray-700'
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
