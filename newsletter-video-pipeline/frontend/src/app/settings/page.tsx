"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Key, Trash2, Plus, Copy, Loader2 } from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { formatDateTime } from "@/lib/utils";
import { toast } from "sonner";
import api from "@/lib/api";

const profileSchema = z.object({
  username: z.string().min(3, "Username must be at least 3 characters"),
  email: z.string().email("Invalid email address"),
});

const passwordSchema = z.object({
  current_password: z.string().min(1, "Current password is required"),
  new_password: z.string().min(8, "Password must be at least 8 characters"),
  confirm_password: z.string(),
}).refine((data) => data.new_password === data.confirm_password, {
  message: "Passwords don't match",
  path: ["confirm_password"],
});

type ProfileForm = z.infer<typeof profileSchema>;
type PasswordForm = z.infer<typeof passwordSchema>;

interface APIKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  created_at: string;
  expires_at?: string;
  last_used_at?: string;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { user, fetchUser } = useAuthStore();
  const [isApiKeyDialogOpen, setIsApiKeyDialogOpen] = useState(false);
  const [newApiKeyName, setNewApiKeyName] = useState("");
  const [newApiKey, setNewApiKey] = useState<string | null>(null);

  const { data: apiKeys, isLoading: apiKeysLoading } = useQuery<APIKey[]>({
    queryKey: ["api-keys"],
    queryFn: async () => {
      const response = await api.get("/auth/api-keys");
      return response.data;
    },
  });

  const {
    register: registerProfile,
    handleSubmit: handleProfileSubmit,
    formState: { errors: profileErrors },
  } = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      username: user?.username || "",
      email: user?.email || "",
    },
  });

  const {
    register: registerPassword,
    handleSubmit: handlePasswordSubmit,
    reset: resetPasswordForm,
    formState: { errors: passwordErrors },
  } = useForm<PasswordForm>({
    resolver: zodResolver(passwordSchema),
  });

  const updateProfile = useMutation({
    mutationFn: authApi.updateProfile,
    onSuccess: () => {
      toast.success("Profile updated successfully");
      fetchUser();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to update profile");
    },
  });

  const updatePassword = useMutation({
    mutationFn: async (data: PasswordForm) => {
      await api.put("/auth/me/password", {
        current_password: data.current_password,
        new_password: data.new_password,
      });
    },
    onSuccess: () => {
      toast.success("Password updated successfully");
      resetPasswordForm();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to update password");
    },
  });

  const createApiKey = useMutation({
    mutationFn: async () => {
      const response = await api.post("/auth/api-keys", {
        name: newApiKeyName,
        scopes: ["pipeline:read", "pipeline:write", "video:read", "video:write"],
      });
      return response.data;
    },
    onSuccess: (data) => {
      setNewApiKey(data.key);
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
      setNewApiKeyName("");
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to create API key");
    },
  });

  const deleteApiKey = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/auth/api-keys/${id}`);
    },
    onSuccess: () => {
      toast.success("API key deleted");
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to delete API key");
    },
  });

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground">
            Manage your account and preferences
          </p>
        </div>

        <Tabs defaultValue="profile">
          <TabsList>
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="security">Security</TabsTrigger>
            <TabsTrigger value="api-keys">API Keys</TabsTrigger>
          </TabsList>

          {/* Profile Tab */}
          <TabsContent value="profile" className="space-y-4 mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Profile Information</CardTitle>
                <CardDescription>
                  Update your account details
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleProfileSubmit((data) => updateProfile.mutate(data))} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <Input id="username" {...registerProfile("username")} />
                    {profileErrors.username && (
                      <p className="text-sm text-destructive">{profileErrors.username.message}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input id="email" type="email" {...registerProfile("email")} />
                    {profileErrors.email && (
                      <p className="text-sm text-destructive">{profileErrors.email.message}</p>
                    )}
                  </div>
                  <Button type="submit" disabled={updateProfile.isPending}>
                    {updateProfile.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Save Changes
                  </Button>
                </form>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Security Tab */}
          <TabsContent value="security" className="space-y-4 mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Change Password</CardTitle>
                <CardDescription>
                  Update your password to keep your account secure
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handlePasswordSubmit((data) => updatePassword.mutate(data))} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="current_password">Current Password</Label>
                    <Input
                      id="current_password"
                      type="password"
                      {...registerPassword("current_password")}
                    />
                    {passwordErrors.current_password && (
                      <p className="text-sm text-destructive">{passwordErrors.current_password.message}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="new_password">New Password</Label>
                    <Input
                      id="new_password"
                      type="password"
                      {...registerPassword("new_password")}
                    />
                    {passwordErrors.new_password && (
                      <p className="text-sm text-destructive">{passwordErrors.new_password.message}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="confirm_password">Confirm New Password</Label>
                    <Input
                      id="confirm_password"
                      type="password"
                      {...registerPassword("confirm_password")}
                    />
                    {passwordErrors.confirm_password && (
                      <p className="text-sm text-destructive">{passwordErrors.confirm_password.message}</p>
                    )}
                  </div>
                  <Button type="submit" disabled={updatePassword.isPending}>
                    {updatePassword.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Update Password
                  </Button>
                </form>
              </CardContent>
            </Card>
          </TabsContent>

          {/* API Keys Tab */}
          <TabsContent value="api-keys" className="space-y-4 mt-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>API Keys</CardTitle>
                    <CardDescription>
                      Manage API keys for programmatic access
                    </CardDescription>
                  </div>
                  <Dialog open={isApiKeyDialogOpen} onOpenChange={setIsApiKeyDialogOpen}>
                    <DialogTrigger asChild>
                      <Button>
                        <Plus className="mr-2 h-4 w-4" />
                        Create Key
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>
                          {newApiKey ? "API Key Created" : "Create API Key"}
                        </DialogTitle>
                      </DialogHeader>
                      {newApiKey ? (
                        <div className="space-y-4">
                          <p className="text-sm text-muted-foreground">
                            Make sure to copy your API key now. You won&apos;t be able to see it again!
                          </p>
                          <div className="flex items-center space-x-2">
                            <Input value={newApiKey} readOnly className="font-mono text-sm" />
                            <Button
                              variant="outline"
                              size="icon"
                              onClick={() => copyToClipboard(newApiKey)}
                            >
                              <Copy className="h-4 w-4" />
                            </Button>
                          </div>
                          <Button
                            className="w-full"
                            onClick={() => {
                              setNewApiKey(null);
                              setIsApiKeyDialogOpen(false);
                            }}
                          >
                            Done
                          </Button>
                        </div>
                      ) : (
                        <div className="space-y-4">
                          <div className="space-y-2">
                            <Label htmlFor="key-name">Key Name</Label>
                            <Input
                              id="key-name"
                              value={newApiKeyName}
                              onChange={(e) => setNewApiKeyName(e.target.value)}
                              placeholder="My API Key"
                            />
                          </div>
                          <DialogFooter>
                            <Button
                              variant="outline"
                              onClick={() => setIsApiKeyDialogOpen(false)}
                            >
                              Cancel
                            </Button>
                            <Button
                              onClick={() => createApiKey.mutate()}
                              disabled={!newApiKeyName || createApiKey.isPending}
                            >
                              {createApiKey.isPending && (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              )}
                              Create
                            </Button>
                          </DialogFooter>
                        </div>
                      )}
                    </DialogContent>
                  </Dialog>
                </div>
              </CardHeader>
              <CardContent>
                {apiKeysLoading ? (
                  <div className="flex justify-center py-8">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                  </div>
                ) : apiKeys && apiKeys.length > 0 ? (
                  <div className="space-y-4">
                    {apiKeys.map((key) => (
                      <div
                        key={key.id}
                        className="flex items-center justify-between p-4 border rounded-lg"
                      >
                        <div className="flex items-center space-x-4">
                          <Key className="h-5 w-5 text-muted-foreground" />
                          <div>
                            <p className="font-medium">{key.name}</p>
                            <p className="text-sm text-muted-foreground font-mono">
                              {key.key_prefix}...
                            </p>
                            <div className="flex items-center space-x-2 mt-1">
                              {key.scopes.slice(0, 3).map((scope) => (
                                <Badge key={scope} variant="outline" className="text-xs">
                                  {scope}
                                </Badge>
                              ))}
                              {key.scopes.length > 3 && (
                                <Badge variant="outline" className="text-xs">
                                  +{key.scopes.length - 3}
                                </Badge>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-4">
                          <div className="text-right text-sm text-muted-foreground">
                            <p>Created {formatDateTime(key.created_at)}</p>
                            {key.last_used_at && (
                              <p>Last used {formatDateTime(key.last_used_at)}</p>
                            )}
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => deleteApiKey.mutate(key.id)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <Key className="mx-auto h-12 w-12 text-muted-foreground" />
                    <p className="mt-4 text-sm text-muted-foreground">
                      No API keys yet. Create one to enable programmatic access.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
