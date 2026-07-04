"use client";

import Link from "next/link";
import { XCircle } from "lucide-react";
import { Button, Card, CardContent } from "@qiko/ui";

export default function CheckoutCancelPage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-4 py-10 text-center">
          <span className="grid size-12 place-items-center rounded-full bg-muted text-muted-foreground">
            <XCircle className="size-7" />
          </span>
          <div>
            <p className="text-lg font-semibold">Checkout cancelled</p>
            <p className="text-sm text-muted-foreground">No charge was made.</p>
          </div>
          <Link href="/billing"><Button variant="outline">Back to billing</Button></Link>
        </CardContent>
      </Card>
    </main>
  );
}
