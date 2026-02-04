"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { User, Plus, Trash2, Star, Upload, Loader2 } from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { avatarApi, Avatar } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { toast } from "sonner";

function AvatarCard({ avatar, onDelete, onSetDefault }: { avatar: Avatar; onDelete: () => void; onSetDefault: () => void }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="aspect-square rounded-lg bg-muted mb-4 overflow-hidden">
          {avatar.thumbnail_url ? (
            <img
              src={avatar.thumbnail_url}
              alt={avatar.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <User className="h-16 w-16 text-muted-foreground" />
            </div>
          )}
        </div>
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-semibold">{avatar.name}</h3>
              {avatar.is_default && <Badge variant="secondary">Default</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">
              Created {formatDateTime(avatar.created_at)}
            </p>
          </div>
          <div className="flex space-x-2">
            {!avatar.is_default && (
              <Button variant="ghost" size="icon" onClick={onSetDefault}>
                <Star className="h-4 w-4" />
              </Button>
            )}
            <Button variant="ghost" size="icon" onClick={onDelete}>
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function AvatarsPage() {
  const queryClient = useQueryClient();
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);

  const { data: avatars, isLoading } = useQuery({
    queryKey: ["avatars"],
    queryFn: avatarApi.list,
  });

  const createAvatar = useMutation({
    mutationFn: async () => {
      if (!videoFile) throw new Error("No video file selected");
      const formData = new FormData();
      formData.append("name", name);
      formData.append("video_file", videoFile);
      return avatarApi.create(formData);
    },
    onSuccess: () => {
      toast.success("Avatar created successfully");
      queryClient.invalidateQueries({ queryKey: ["avatars"] });
      setIsDialogOpen(false);
      setName("");
      setVideoFile(null);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to create avatar");
    },
  });

  const deleteAvatar = useMutation({
    mutationFn: avatarApi.delete,
    onSuccess: () => {
      toast.success("Avatar deleted");
      queryClient.invalidateQueries({ queryKey: ["avatars"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to delete avatar");
    },
  });

  const setDefaultAvatar = useMutation({
    mutationFn: avatarApi.setDefault,
    onSuccess: () => {
      toast.success("Default avatar updated");
      queryClient.invalidateQueries({ queryKey: ["avatars"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to set default avatar");
    },
  });

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "video/*": [".mp4", ".mov", ".avi", ".mkv"],
    },
    maxFiles: 1,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        setVideoFile(acceptedFiles[0]);
      }
    },
  });

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">AI Avatars</h1>
            <p className="text-muted-foreground">
              Create and manage AI avatar personas for your videos
            </p>
          </div>
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                Create Avatar
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Create AI Avatar</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Avatar Name</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="My Avatar"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Reference Video</Label>
                  <div
                    {...getRootProps()}
                    className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                      isDragActive ? "border-primary bg-primary/10" : "border-muted-foreground/25"
                    }`}
                  >
                    <input {...getInputProps()} />
                    <Upload className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                    <p className="text-sm text-muted-foreground">
                      Drag & drop a video file here, or click to select
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      10-30 seconds with clear face visibility
                    </p>
                  </div>
                  {videoFile && (
                    <div className="flex items-center justify-between text-sm p-2 bg-muted rounded mt-2">
                      <span>{videoFile.name}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setVideoFile(null)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => createAvatar.mutate()}
                  disabled={!name || !videoFile || createAvatar.isPending}
                >
                  {createAvatar.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Create Avatar
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {/* Avatar List */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          </div>
        ) : avatars?.items && avatars.items.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {avatars.items.map((avatar) => (
              <AvatarCard
                key={avatar.id}
                avatar={avatar}
                onDelete={() => deleteAvatar.mutate(avatar.id)}
                onSetDefault={() => setDefaultAvatar.mutate(avatar.id)}
              />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <User className="h-12 w-12 text-muted-foreground" />
              <h3 className="mt-4 text-lg font-semibold">No avatars yet</h3>
              <p className="mt-2 text-sm text-muted-foreground text-center">
                Upload a video of yourself to create an AI avatar
              </p>
              <Button className="mt-4" onClick={() => setIsDialogOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Create Avatar
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Tips */}
        <Card>
          <CardHeader>
            <CardTitle>Tips for Better Avatars</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc list-inside space-y-2 text-sm text-muted-foreground">
              <li>Use a high-quality video (1080p or higher)</li>
              <li>Record with good lighting, preferably natural light</li>
              <li>Keep your face clearly visible and centered</li>
              <li>Avoid glasses or accessories that cover your face</li>
              <li>Record 10-30 seconds with natural head movements</li>
              <li>Use a neutral background for best results</li>
              <li>Include different expressions (smiling, talking, nodding)</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
