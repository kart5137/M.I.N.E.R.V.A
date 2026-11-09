import { Globe } from "@/components/globe";
import { PageHeader } from "@/components/layout/page-header";
import { PlatformStatusPanel } from "@/components/overview/platform-status-panel";

export default function OverviewPage() {
  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="Overview"
        description="Global influenza surveillance from WHO FluNet laboratory data."
      />
      <div className="grid flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-h-[420px] overflow-hidden rounded-lg border border-border xl:min-h-[560px]">
          <Globe className="h-full min-h-[420px] w-full" />
        </div>
        <PlatformStatusPanel />
      </div>
    </div>
  );
}
