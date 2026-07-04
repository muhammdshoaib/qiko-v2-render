"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Button, Card, CardContent, CardHeader, CardTitle, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { logout, me } from "@/lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const account = useQuery({ queryKey: ["me"], queryFn: me });

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <AppShell title="Settings">
      <div className="mx-auto max-w-lg space-y-6">
        <Card>
          <CardHeader><CardTitle>Account</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {account.isLoading && <Skeleton className="h-10 w-full" />}
            {account.data && (
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between"><dt className="text-muted-foreground">Email</dt><dd>{account.data.email}</dd></div>
                <div className="flex justify-between"><dt className="text-muted-foreground">Role</dt><dd>{account.data.role}</dd></div>
              </dl>
            )}
            <Button variant="outline" onClick={onLogout}>Sign out</Button>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
