import type { ApiSection } from '../../../data/api-endpoints/types';
import type { RateLimitConfig } from '../../../lib/apiRateLimitMatch';
import { EndpointCard } from './EndpointCard';

export interface ApiSectionListProps {
  sections: ApiSection[];
  rateLimits: Record<string, RateLimitConfig>;
  t: (key: string) => string;
}

export function ApiSectionList({ sections, rateLimits, t }: ApiSectionListProps) {
  return (
    <>
      {sections.map((section) => (
        <div key={section.title}>
          <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
            <div className="p-1.5 sm:p-2 bg-cyan-500/20 rounded-lg text-cyan-400">
              {section.icon}
            </div>
            <h2 className="text-lg sm:text-xl font-bold text-white">{section.title}</h2>
          </div>
          <div className="space-y-2 sm:space-y-3">
            {section.endpoints.map((endpoint, idx) => (
              <EndpointCard
                key={idx}
                endpoint={endpoint}
                rateLimits={rateLimits}
                t={t}
              />
            ))}
          </div>
        </div>
      ))}
    </>
  );
}
