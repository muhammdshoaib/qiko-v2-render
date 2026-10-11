"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { ConsentProvider } from "@/components/consent/ConsentProvider";
import { CrmProvider } from "@/lib/crm/store";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={client}>
      <ConsentProvider>
        <CrmProvider>
          {children}
          <Toaster />
        </CrmProvider>
      </ConsentProvider>
    </QueryClientProvider>
  );
}
