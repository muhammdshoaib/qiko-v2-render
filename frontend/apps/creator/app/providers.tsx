"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { ConsentProvider } from "@/components/consent/ConsentProvider";
import { CrmProvider } from "@/lib/crm/store";
import { BrainProvider } from "@/lib/brain/store";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={client}>
      <ConsentProvider>
        <CrmProvider>
          <BrainProvider>
            {children}
            <Toaster />
          </BrainProvider>
        </CrmProvider>
      </ConsentProvider>
    </QueryClientProvider>
  );
}
