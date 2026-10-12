"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { ConsentProvider } from "@/components/consent/ConsentProvider";
import { CrmProvider } from "@/lib/crm/store";
import { BrainProvider } from "@/lib/brain/store";
import { ReferralProvider } from "@/lib/brain/referral-store";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={client}>
      <ConsentProvider>
        <CrmProvider>
          <BrainProvider>
            <ReferralProvider>
            {children}
            <Toaster />
            </ReferralProvider>
          </BrainProvider>
        </CrmProvider>
      </ConsentProvider>
    </QueryClientProvider>
  );
}
