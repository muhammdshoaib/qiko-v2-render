"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CreditCard, KeyRound, Lock, Search, Settings2, Trash2, User, UserPlus, Users } from "lucide-react";
import { Badge, Button, Input, Label, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  ASSIGNABLE_ROLES,
  ROLE_LABELS,
  cancelInvite,
  inviteUser,
  listTenantUsers,
  me,
  removeUser,
  updateUserRole,
  type TenantRole,
  type TenantUser,
} from "@/lib/api";

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
            <h1 className="mb-2 text-2xl font-bold lg:text-3xl" style={{
              fontFamily: "var(--font-display)",
              background: "linear-gradient(135deg, #fff 0%, #6366F1 50%, #22D3EE 100%)",
              WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent",
            }}>
              Settings
            </h1>
            <p className="text-slate-400">Manage your account and preferences</p>
          </div>

          <div className="mb-6 inline-flex h-12 w-fit items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.015] p-1.5">
            {SETTINGS_TABS.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setTab(id)} aria-current={tab === id ? "page" : undefined}
                className={cn("inline-flex h-full items-center justify-center gap-1.5 rounded-xl border px-6 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                  tab === id ? "border-cyan-500/30 bg-cyan-500/10 text-white" : "border-transparent text-slate-300 hover:text-white")}>
                <Icon className={cn("size-4", tab === id ? "text-cyan-400" : "text-slate-500")} /> {label}
              </button>
            ))}
          </div>

          {tab === "general" && (
            <div className="space-y-6">
              <div>
                <h2 className="flex items-center gap-2 text-2xl font-semibold text-white">
                  <User className="size-6 text-cyan-400" /> General Settings
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
                <Button disabled aria-disabled="true" title="Locked"
                  className="w-full cursor-not-allowed border-0 bg-gradient-to-r from-emerald-600 to-cyan-600 text-white opacity-60 shadow-lg shadow-emerald-900/30">
                  <Lock className="size-4" /> View Plans
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

const SELECT_CLS =
  "h-9 rounded-lg border border-white/10 bg-white/[0.03] px-3 text-sm text-slate-200 transition-colors " +
  "focus-visible:border-cyan-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 " +
  "disabled:cursor-not-allowed disabled:opacity-50 [&>option]:bg-[#0b0e16] [&>option]:text-slate-200";

function roleBadgeVariant(role: TenantRole): "default" | "success" | "muted" {
  if (role === "owner" || role === "admin") return "default";
  if (role === "editor") return "success";
  return "muted";
}

function TeamPanel() {
  const qc = useQueryClient();
  const account = useQuery({ queryKey: ["me"], queryFn: me });
  const canManage = account.data?.role === "owner" || account.data?.role === "admin";

  const teamQuery = useQuery({ queryKey: ["tenant-users"], queryFn: listTenantUsers });
  const users = useMemo(() => teamQuery.data?.users ?? [], [teamQuery.data]);
  const pending = useMemo(() => teamQuery.data?.pending ?? [], [teamQuery.data]);

  const [subTab, setSubTab] = useState<"accepted" | "pending">("accepted");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | TenantRole>("all");
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Exclude<TenantRole, "owner">>("viewer");
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["tenant-users"] });

  const inviteMut = useMutation({
    mutationFn: () => inviteUser(inviteEmail.trim(), inviteRole),
    onSuccess: () => { setInviteEmail(""); setInviteRole("viewer"); setShowInvite(false); setError(null); setSubTab("pending"); invalidate(); },
    onError: () => setError("Could not send the invite. Check the email and try again."),
  });
  const roleMut = useMutation({
    mutationFn: (v: { userId: string; role: Exclude<TenantRole, "owner"> }) => updateUserRole(v.userId, v.role),
    onSuccess: () => { setError(null); invalidate(); },
    onError: () => setError("Could not update the role."),
  });
  const removeMut = useMutation({
    mutationFn: (userId: string) => removeUser(userId),
    onSuccess: () => { setError(null); invalidate(); },
    onError: () => setError("Could not remove the user."),
  });
  const cancelMut = useMutation({
    mutationFn: (email: string) => cancelInvite(email),
    onSuccess: () => { setError(null); invalidate(); },
    onError: () => setError("Could not cancel the invite."),
  });

  const q = search.trim().toLowerCase();
  const filteredUsers = users.filter((u) =>
    (roleFilter === "all" || u.role === roleFilter) &&
    (!q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)));
  const filteredPending = pending.filter((p) =>
    (roleFilter === "all" || p.role === roleFilter) &&
    (!q || p.email.toLowerCase().includes(q)));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-semibold text-white">
            <Users className="size-6 text-cyan-400" /> Team Access
          </h2>
          <p className="mt-1 text-slate-400">Invite users and assign roles: User, Creator, or Admin.</p>
        </div>
        {canManage && (
          <Button onClick={() => { setShowInvite((v) => !v); setError(null); }} aria-expanded={showInvite}
            className="border-0 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-900/30">
            <UserPlus className="size-4" /> Add Team
          </Button>
        )}
      </div>

      {showInvite && canManage && (
        <SettingsCard icon={UserPlus} iconColor="text-[#6366F1]" title="Invite a user">
          <form className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={(e) => { e.preventDefault(); if (inviteEmail.trim()) inviteMut.mutate(); }}>
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="invite-email">Email</Label>
              <Input id="invite-email" type="email" placeholder="teammate@company.com"
                value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-role">Role</Label>
              <select id="invite-role" className={cn(SELECT_CLS, "w-full sm:w-40")}
                value={inviteRole} onChange={(e) => setInviteRole(e.target.value as Exclude<TenantRole, "owner">)}>
                {ASSIGNABLE_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
            <Button type="submit" disabled={!inviteEmail.trim() || inviteMut.isPending}>
              <UserPlus className="size-4" /> Send invite
            </Button>
          </form>
        </SettingsCard>
      )}

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      <div className="inline-flex h-11 w-fit items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.015] p-1.5">
        {([["accepted", "Accepted", users.length], ["pending", "Pending", pending.length]] as const).map(([id, label, count]) => (
          <button key={id} onClick={() => setSubTab(id)} aria-current={subTab === id ? "page" : undefined}
            className={cn("inline-flex h-full items-center justify-center rounded-xl border px-5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
              subTab === id ? "border-cyan-500/30 bg-cyan-500/10 text-white" : "border-transparent text-slate-300 hover:text-white")}>
            {label} ({count})
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
          <Input aria-label="Search by name or email" placeholder="Search by name or email"
            value={search} onChange={(e) => setSearch(e.target.value)}
            className="border-white/10 bg-white/[0.03] pl-9 text-slate-200" />
        </div>
        <select aria-label="Filter by role" className={cn(SELECT_CLS, "w-full sm:w-44")}
          value={roleFilter} onChange={(e) => setRoleFilter(e.target.value as "all" | TenantRole)}>
          <option value="all">All roles</option>
          {(Object.keys(ROLE_LABELS) as TenantRole[]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
        </select>
      </div>

      <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.015]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wide text-slate-500">
              <th scope="col" className="px-4 py-3 font-medium">Name</th>
              <th scope="col" className="px-4 py-3 font-medium">Email</th>
              <th scope="col" className="px-4 py-3 font-medium">Role</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {teamQuery.isLoading && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">Loading team...</td></tr>
            )}
            {teamQuery.isError && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-destructive">Could not load the team.</td></tr>
            )}
            {!teamQuery.isLoading && !teamQuery.isError && subTab === "accepted" && (
              filteredUsers.length === 0 ? (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">No users match your filters.</td></tr>
              ) : filteredUsers.map((u) => (
                <AcceptedRow key={u.id} user={u} canManage={!!canManage}
                  onRole={(role) => roleMut.mutate({ userId: u.id, role })}
                  onRemove={() => { if (window.confirm(`Remove ${u.name} from the team?`)) removeMut.mutate(u.id); }}
                  busy={roleMut.isPending || removeMut.isPending} />
              ))
            )}
            {!teamQuery.isLoading && !teamQuery.isError && subTab === "pending" && (
              filteredPending.length === 0 ? (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">No pending invites.</td></tr>
              ) : filteredPending.map((p) => (
                <tr key={p.email} className="border-b border-white/[0.04] last:border-0">
                  <td className="px-4 py-3 text-slate-400">Invited</td>
                  <td className="px-4 py-3 text-white">{p.email}</td>
                  <td className="px-4 py-3"><Badge variant={roleBadgeVariant(p.role)}>{p.role_label}</Badge></td>
                  <td className="px-4 py-3 text-right">
                    {canManage && (
                      <button type="button" aria-label={`Cancel invite for ${p.email}`}
                        onClick={() => cancelMut.mutate(p.email)} disabled={cancelMut.isPending}
                        className="inline-flex size-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/60 disabled:opacity-50">
                        <Trash2 className="size-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AcceptedRow({ user, canManage, onRole, onRemove, busy }: {
  user: TenantUser; canManage: boolean;
  onRole: (role: Exclude<TenantRole, "owner">) => void; onRemove: () => void; busy: boolean;
}) {
  const editable = canManage && !user.is_owner;
  return (
    <tr className="border-b border-white/[0.04] last:border-0">
      <td className="px-4 py-3 font-medium text-white">{user.name}</td>
      <td className="px-4 py-3 text-slate-300">{user.email}</td>
      <td className="px-4 py-3">
        {editable ? (
          <select aria-label={`Change role for ${user.name}`} className={cn(SELECT_CLS, "w-36")}
            value={user.role} disabled={busy}
            onChange={(e) => onRole(e.target.value as Exclude<TenantRole, "owner">)}>
            {ASSIGNABLE_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        ) : (
          <Badge variant={roleBadgeVariant(user.role)}>{user.role_label}</Badge>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        {canManage && !user.is_owner && (
          <button type="button" aria-label={`Remove ${user.name}`} onClick={onRemove} disabled={busy}
            className="inline-flex size-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/60 disabled:opacity-50">
            <Trash2 className="size-4" />
          </button>
        )}
      </td>
    </tr>
  );
}
