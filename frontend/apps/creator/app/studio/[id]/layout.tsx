import type { ReactNode } from "react";
import { StudioWorkerRouteGuard } from "@/components/studio/worker-route-guard";

export default function StudioWorkerLayout({ children }: { children: ReactNode }) {
  return <StudioWorkerRouteGuard>{children}</StudioWorkerRouteGuard>;
}
