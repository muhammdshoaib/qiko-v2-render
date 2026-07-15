"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CreditCard, KeyRound, Settings2, User, UserPlus, Users } from "lucide-react";
import { Badge, Button, Input, Label, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { addTeamMember, createTeam, me, type Team } from "@/lib/api";

const SETTINGS_TABS = [
  { id: "general", label: "General", icon: Settings2 },
  { id: "team", label: "Team", icon: Users },
] as const;

function SettingsCard({ icon: Icon, iconColor, title, children }: {
  icon: React.ComponentType<{ className?: string }>; iconColor: string; title: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] py-6">
      <div className="px-6">
        <div className="flex items-center gap-2 font-semibold leading-none text-white">
          <Icon className={cn("size-5", iconColor)} /> {title}
        </div>
      </div>
      <div className="px-6 pt-6">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState<(typeof SETTINGS_TABS)[number]["id"]>("general");
  const account = useQuery({ queryKey: ["me"], queryFn: me });

  return (
    <AppShell title="Settings">
      <div className="p-6 lg:p-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-8">
            <h1 className="mb-2 text-2xl font-bold text-white lg:text-3xl" style={{ fontFamily: "var(--font-display)" }}>
              Settings
            </h1>
            <p className="text-slate-400">Manage your account and preferences</p>
          </div>

          <div className="mb-6 inline-flex h-12 w-fit items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.015] p-1.5">
            {SETTINGS_TABS.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setTab(id)} aria-current={tab === id ? "page" : undefined}
                className={cn("inline-flex h-full items-center justify-center gap-1.5 rounded-xl border px-6 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                  tab === id ? "border-indigo-500/30 bg-indigo-500/10 text-white" : "border-transparent text-slate-300 hover:text-white")}>
                <Icon className={cn("size-4", tab === id ? "text-indigo-400" : "text-slate-500")} /> {label}
              </button>
            ))}
          </div>

          {tab === "general" && (
            <div className="space-y-6">
              <div>
                <h2 className="flex items-center gap-2 text-2xl font-semibold text-white">
                  <User className="size-6 text-indigo-400" /> General Settings
                </h2>
                <p className="mt-1 text-slate-400">Manage your account and preferences.</p>
              </div>

              <SettingsCard icon={User} iconColor="text-[#6366F1]" title="Profile">
                <div className="space-y-4">
                  <div>
                    <label className="text-sm text-slate-400">Name</label>
                    <p className="text-white">{account.data?.email?.split("@")[0] ?? "—"}</p>
                  </div>
                  <div>
                    <label className="text-sm text-slate-400">Email</label>
                    <p className="text-white">{account.data?.email ?? "—"}</p>
                  </div>
                </div>
              </SettingsCard>

              <SettingsCard icon={CreditCard} iconColor="text-emerald-400" title="Billing">
                <p className="mb-4 text-sm text-slate-400">Manage your subscription and payment methods</p>
                <Button onClick={() => (window.location.href = "/billing")}
                  className="w-full border-0 bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-900/30 hover:opacity-90">
                  <CreditCard className="size-4" /> View Plans <ArrowRight className="size-4" />
                </Button>
              </SettingsCard>

              <SettingsCard icon={KeyRound} iconColor="text-amber-400" title="Change Password">
                <p className="mb-4 text-sm text-slate-400">Update your account password securely.</p>
                <Button onClick={() => (window.location.href = "/forgot-password")}
                  className="w-full border-0 bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-lg shadow-violet-900/30 hover:shadow-violet-800/50">
                  <KeyRound className="size-4" /> Change Password <ArrowRight className="size-4" />
                </Button>
              </SettingsCard>
            </div>
          )}

          {tab === "team" && <TeamPanel />}
        </div>
      </div>
    </AppShell>
  );
}

function TeamPanel() {
  const [team, setTeam] = useState<Team | null>(null);
  const [owner, setOwner] = useState("");
  const [memberId, setMemberId] = useState("");
  const [role, setRole] = useState("editor");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ROLES = ["viewer", "editor", "admin"];

  async function create() {
    setBusy(true); setError(null);
    try { setTeam(await createTeam(owner)); } finally { setBusy(false); }
  }
  async function add() {
    setBusy(true); setError(null);
    try { setTeam(await addTeamMember(team!.team_id, memberId, role)); setMemberId(""); }
    catch { setError("Could not add member."); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="flex items-center gap-2 text-2xl font-semibold text-white">
          <Users className="size-6 text-indigo-400" /> Team
        </h2>
        <p className="mt-1 text-slate-400">Invite teammates and manage roles.</p>
      </div>

      {!team ? (
        <SettingsCard icon={UserPlus} iconColor="text-[#6366F1]" title="Create your team">
          <div className="space-y-4">
            <div className="space-y-1.5"><Label>Owner (your user id / email)</Label>
              <Input placeholder="owner@company.com" value={owner} onChange={(e) => setOwner(e.target.value)} /></div>
            <Button className="w-full" disabled={!owner || busy} onClick={create}>Create team</Button>
          </div>
        </SettingsCard>
      ) : (
        <>
          <SettingsCard icon={Users} iconColor="text-emerald-400" title="Members">
            <div className="space-y-2">
              {Object.entries(team.members).map(([uid, r]) => (
                <div key={uid} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <span className="text-sm">{uid}</span>
                  <Badge variant={r === "owner" ? "default" : "muted"}>{r}</Badge>
                </div>
              ))}
            </div>
          </SettingsCard>
          <SettingsCard icon={UserPlus} iconColor="text-[#6366F1]" title="Invite a member">
            <div className="space-y-4">
              <div className="space-y-1.5"><Label>User id / email</Label>
                <Input placeholder="teammate@company.com" value={memberId} onChange={(e) => setMemberId(e.target.value)} /></div>
              <div className="space-y-1.5"><Label>Role</Label>
                <select className="h-10 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 text-sm text-slate-200 transition-colors focus-visible:border-indigo-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 [&>option]:bg-[#0b0e16] [&>option]:text-slate-200"
                  value={role} onChange={(e) => setRole(e.target.value)}>
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select></div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button className="w-full" disabled={!memberId || busy} onClick={add}><UserPlus className="size-4" /> Add member</Button>
            </div>
          </SettingsCard>
        </>
      )}
    </div>
  );
}
