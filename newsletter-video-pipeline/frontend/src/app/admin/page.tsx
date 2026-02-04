"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users,
  Activity,
  HardDrive,
  Clock,
  Search,
  MoreVertical,
  Shield,
  Ban,
  Trash2,
  RefreshCw,
} from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { formatDateTime } from "@/lib/utils";
import { toast } from "sonner";
import api from "@/lib/api";

interface SystemStats {
  total_users: number;
  active_users: number;
  total_pipelines: number;
  active_pipelines: number;
  total_videos: number;
  storage_used_gb: number;
  cpu_usage: number;
  memory_usage: number;
}

interface AdminUser {
  id: string;
  email: string;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login_at?: string;
  pipeline_count: number;
}

function StatCard({
  title,
  value,
  description,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  description?: string;
  icon: any;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}

function UserRow({ user, onRefresh }: { user: AdminUser; onRefresh: () => void }) {
  const queryClient = useQueryClient();

  const updateRole = useMutation({
    mutationFn: async (role: string) => {
      await api.put(`/auth/admin/users/${user.id}/role`, { role });
    },
    onSuccess: () => {
      toast.success("User role updated");
      onRefresh();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to update role");
    },
  });

  const toggleActive = useMutation({
    mutationFn: async () => {
      await api.put(`/auth/admin/users/${user.id}/status`, {
        is_active: !user.is_active,
      });
    },
    onSuccess: () => {
      toast.success(`User ${user.is_active ? "deactivated" : "activated"}`);
      onRefresh();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to update status");
    },
  });

  const deleteUser = useMutation({
    mutationFn: async () => {
      await api.delete(`/auth/admin/users/${user.id}`);
    },
    onSuccess: () => {
      toast.success("User deleted");
      onRefresh();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to delete user");
    },
  });

  return (
    <tr className="border-b">
      <td className="py-4 px-4">
        <div>
          <p className="font-medium">{user.username}</p>
          <p className="text-sm text-muted-foreground">{user.email}</p>
        </div>
      </td>
      <td className="py-4 px-4">
        <Badge
          variant={
            user.role === "super_admin"
              ? "destructive"
              : user.role === "admin"
              ? "default"
              : "secondary"
          }
        >
          {user.role}
        </Badge>
      </td>
      <td className="py-4 px-4">
        <Badge variant={user.is_active ? "success" : "secondary"}>
          {user.is_active ? "Active" : "Inactive"}
        </Badge>
      </td>
      <td className="py-4 px-4 text-sm text-muted-foreground">
        {user.pipeline_count}
      </td>
      <td className="py-4 px-4 text-sm text-muted-foreground">
        {user.last_login_at ? formatDateTime(user.last_login_at) : "Never"}
      </td>
      <td className="py-4 px-4">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => updateRole.mutate("admin")}>
              <Shield className="mr-2 h-4 w-4" />
              Make Admin
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => updateRole.mutate("user")}>
              <Users className="mr-2 h-4 w-4" />
              Make User
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => toggleActive.mutate()}>
              <Ban className="mr-2 h-4 w-4" />
              {user.is_active ? "Deactivate" : "Activate"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-destructive"
              onClick={() => {
                if (confirm("Are you sure you want to delete this user?")) {
                  deleteUser.mutate();
                }
              }}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete User
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </td>
    </tr>
  );
}

export default function AdminPage() {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState("");

  const { data: stats, isLoading: statsLoading } = useQuery<SystemStats>({
    queryKey: ["admin-stats"],
    queryFn: async () => {
      const response = await api.get("/admin/stats");
      return response.data;
    },
    refetchInterval: 30000,
  });

  const { data: users, isLoading: usersLoading, refetch: refetchUsers } = useQuery<AdminUser[]>({
    queryKey: ["admin-users"],
    queryFn: async () => {
      const response = await api.get("/auth/admin/users");
      return response.data;
    },
  });

  const runMaintenance = useMutation({
    mutationFn: async (task: string) => {
      await api.post(`/admin/maintenance/${task}`);
    },
    onSuccess: (_, task) => {
      toast.success(`Maintenance task "${task}" started`);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to run maintenance");
    },
  });

  const filteredUsers = users?.filter(
    (user) =>
      user.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      user.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Admin Panel</h1>
          <p className="text-muted-foreground">
            System administration and user management
          </p>
        </div>

        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="maintenance">Maintenance</TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-4 mt-4">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <StatCard
                title="Total Users"
                value={stats?.total_users || 0}
                description={`${stats?.active_users || 0} active`}
                icon={Users}
              />
              <StatCard
                title="Active Pipelines"
                value={stats?.active_pipelines || 0}
                description={`${stats?.total_pipelines || 0} total`}
                icon={Activity}
              />
              <StatCard
                title="Storage Used"
                value={`${(stats?.storage_used_gb || 0).toFixed(1)} GB`}
                icon={HardDrive}
              />
              <StatCard
                title="System Load"
                value={`${(stats?.cpu_usage || 0).toFixed(0)}%`}
                description={`Memory: ${(stats?.memory_usage || 0).toFixed(0)}%`}
                icon={Clock}
              />
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Recent Activity</CardTitle>
                <CardDescription>
                  System events and user activities
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Activity log coming soon...
                </p>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Users Tab */}
          <TabsContent value="users" className="space-y-4 mt-4">
            <div className="flex items-center space-x-4">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search users..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Button variant="outline" onClick={() => refetchUsers()}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Refresh
              </Button>
            </div>

            <Card>
              <CardContent className="p-0">
                {usersLoading ? (
                  <div className="flex justify-center py-12">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                  </div>
                ) : (
                  <table className="w-full">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="py-3 px-4 text-left text-sm font-medium">User</th>
                        <th className="py-3 px-4 text-left text-sm font-medium">Role</th>
                        <th className="py-3 px-4 text-left text-sm font-medium">Status</th>
                        <th className="py-3 px-4 text-left text-sm font-medium">Pipelines</th>
                        <th className="py-3 px-4 text-left text-sm font-medium">Last Login</th>
                        <th className="py-3 px-4 text-left text-sm font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredUsers?.map((user) => (
                        <UserRow
                          key={user.id}
                          user={user}
                          onRefresh={() => refetchUsers()}
                        />
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Maintenance Tab */}
          <TabsContent value="maintenance" className="space-y-4 mt-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Cleanup Tasks</CardTitle>
                  <CardDescription>
                    Run system maintenance tasks
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => runMaintenance.mutate("cleanup_temp_files")}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Clean Temporary Files
                  </Button>
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => runMaintenance.mutate("cleanup_expired_tokens")}
                  >
                    <Clock className="mr-2 h-4 w-4" />
                    Clean Expired Tokens
                  </Button>
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => runMaintenance.mutate("cleanup_old_jobs")}
                  >
                    <Activity className="mr-2 h-4 w-4" />
                    Clean Old Jobs (30+ days)
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Database Operations</CardTitle>
                  <CardDescription>
                    Backup and maintenance operations
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => runMaintenance.mutate("backup_database")}
                  >
                    <HardDrive className="mr-2 h-4 w-4" />
                    Create Database Backup
                  </Button>
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => runMaintenance.mutate("generate_usage_stats")}
                  >
                    <Activity className="mr-2 h-4 w-4" />
                    Generate Usage Stats
                  </Button>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
