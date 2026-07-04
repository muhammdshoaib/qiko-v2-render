"use client";

import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { Button, Card, CardContent } from "@qiko/ui";

export default function CheckoutSuccessPage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-4 py-10 text-center">
          <span className="grid size-12 place-items-center rounded-full bg-accent text-success">
            <CheckCircle2 className="size-7" />
          </span>
          <div>
            <p className="text-lg font-semibold">Payment successful</p>
            <p className="text-sm text-muted-foreground">Your subscription is now active.</p>
          </div>
          <Link href="/dashboard"><Button>Go to dashboard</Button></Link>
        </CardContent>
      </Card>
    </main>
  );
}
