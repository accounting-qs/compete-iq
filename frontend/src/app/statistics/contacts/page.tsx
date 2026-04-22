import { Suspense } from "react";
import { StatisticsContactsPage } from "@/components/statistics/StatisticsContactsPage";

// `useSearchParams()` requires a Suspense boundary so Next.js can render
// the fallback during static/streaming render without bailing out.
export default function StatisticsContacts() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-64">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm text-zinc-500">Loading...</span>
          </div>
        </div>
      }
    >
      <StatisticsContactsPage />
    </Suspense>
  );
}
