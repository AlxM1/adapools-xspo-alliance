"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Video, Mic, User } from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { pipelineApi, voiceApi, avatarApi } from "@/lib/api";
import { toast } from "sonner";

const pipelineSchema = z.object({
  newsletter_title: z.string().min(1, "Title is required"),
  newsletter_content: z.string().min(50, "Content must be at least 50 characters"),
  generate_long_form: z.boolean().default(true),
  generate_shorts: z.boolean().default(true),
  shorts_count: z.number().min(1).max(10).default(3),
  voice_id: z.string().optional(),
  avatar_id: z.string().optional(),
  target_platforms: z.array(z.string()).min(1, "Select at least one platform"),
  auto_publish: z.boolean().default(false),
});

type PipelineForm = z.infer<typeof pipelineSchema>;

const platforms = [
  { id: "youtube", name: "YouTube", icon: Video },
  { id: "tiktok", name: "TikTok", icon: Video },
  { id: "instagram", name: "Instagram", icon: Video },
  { id: "x", name: "X (Twitter)", icon: Video },
];

export default function NewPipelinePage() {
  const router = useRouter();
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(["youtube"]);

  const { data: voices } = useQuery({
    queryKey: ["voices"],
    queryFn: voiceApi.list,
  });

  const { data: avatars } = useQuery({
    queryKey: ["avatars"],
    queryFn: avatarApi.list,
  });

  const createPipeline = useMutation({
    mutationFn: pipelineApi.create,
    onSuccess: (data) => {
      toast.success("Pipeline started successfully");
      router.push(`/pipeline/${data.id}`);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to create pipeline");
    },
  });

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<PipelineForm>({
    resolver: zodResolver(pipelineSchema),
    defaultValues: {
      generate_long_form: true,
      generate_shorts: true,
      shorts_count: 3,
      target_platforms: ["youtube"],
      auto_publish: false,
    },
  });

  const generateLongForm = watch("generate_long_form");
  const generateShorts = watch("generate_shorts");

  const togglePlatform = (platformId: string) => {
    const newPlatforms = selectedPlatforms.includes(platformId)
      ? selectedPlatforms.filter((p) => p !== platformId)
      : [...selectedPlatforms, platformId];
    setSelectedPlatforms(newPlatforms);
    setValue("target_platforms", newPlatforms);
  };

  const onSubmit = (data: PipelineForm) => {
    createPipeline.mutate({
      ...data,
      target_platforms: selectedPlatforms,
    });
  };

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">New Pipeline</h1>
          <p className="text-muted-foreground">
            Convert your newsletter into engaging video content
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Newsletter Content */}
          <Card>
            <CardHeader>
              <CardTitle>Newsletter Content</CardTitle>
              <CardDescription>
                Paste your newsletter content to be converted into video
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Title</Label>
                <Input
                  id="title"
                  placeholder="Weekly Newsletter #42"
                  {...register("newsletter_title")}
                />
                {errors.newsletter_title && (
                  <p className="text-sm text-destructive">{errors.newsletter_title.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="content">Content</Label>
                <Textarea
                  id="content"
                  placeholder="Paste your newsletter content here..."
                  className="min-h-[200px]"
                  {...register("newsletter_content")}
                />
                {errors.newsletter_content && (
                  <p className="text-sm text-destructive">{errors.newsletter_content.message}</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Video Options */}
          <Card>
            <CardHeader>
              <CardTitle>Video Options</CardTitle>
              <CardDescription>
                Configure video generation settings
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Video Types */}
              <div className="space-y-4">
                <Label>Video Types</Label>
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      className="rounded border-gray-300"
                      {...register("generate_long_form")}
                    />
                    <span>Long-form video</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      className="rounded border-gray-300"
                      {...register("generate_shorts")}
                    />
                    <span>Short-form clips</span>
                  </label>
                </div>
              </div>

              {generateShorts && (
                <div className="space-y-2">
                  <Label htmlFor="shorts_count">Number of Shorts</Label>
                  <Select
                    defaultValue="3"
                    onValueChange={(value) => setValue("shorts_count", parseInt(value))}
                  >
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <SelectItem key={n} value={n.toString()}>
                          {n}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Voice Selection */}
              <div className="space-y-2">
                <Label>Voice</Label>
                <Select onValueChange={(value) => setValue("voice_id", value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a voice (or use default)" />
                  </SelectTrigger>
                  <SelectContent>
                    {voices?.items?.map((voice) => (
                      <SelectItem key={voice.id} value={voice.id}>
                        <div className="flex items-center space-x-2">
                          <Mic className="h-4 w-4" />
                          <span>{voice.name}</span>
                          {voice.is_default && (
                            <span className="text-xs text-muted-foreground">(default)</span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!voices?.items?.length && (
                  <p className="text-sm text-muted-foreground">
                    No voices available.{" "}
                    <a href="/voices" className="text-primary hover:underline">
                      Create one
                    </a>
                  </p>
                )}
              </div>

              {/* Avatar Selection */}
              <div className="space-y-2">
                <Label>Avatar</Label>
                <Select onValueChange={(value) => setValue("avatar_id", value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select an avatar (or use default)" />
                  </SelectTrigger>
                  <SelectContent>
                    {avatars?.items?.map((avatar) => (
                      <SelectItem key={avatar.id} value={avatar.id}>
                        <div className="flex items-center space-x-2">
                          <User className="h-4 w-4" />
                          <span>{avatar.name}</span>
                          {avatar.is_default && (
                            <span className="text-xs text-muted-foreground">(default)</span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!avatars?.items?.length && (
                  <p className="text-sm text-muted-foreground">
                    No avatars available.{" "}
                    <a href="/avatars" className="text-primary hover:underline">
                      Create one
                    </a>
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Publishing Options */}
          <Card>
            <CardHeader>
              <CardTitle>Publishing Options</CardTitle>
              <CardDescription>
                Select platforms and publishing preferences
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Platform Selection */}
              <div className="space-y-2">
                <Label>Target Platforms</Label>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {platforms.map((platform) => (
                    <button
                      key={platform.id}
                      type="button"
                      onClick={() => togglePlatform(platform.id)}
                      className={`flex flex-col items-center justify-center p-4 rounded-lg border-2 transition-colors ${
                        selectedPlatforms.includes(platform.id)
                          ? "border-primary bg-primary/10"
                          : "border-muted hover:border-muted-foreground"
                      }`}
                    >
                      <platform.icon className="h-6 w-6 mb-2" />
                      <span className="text-sm font-medium">{platform.name}</span>
                    </button>
                  ))}
                </div>
                {errors.target_platforms && (
                  <p className="text-sm text-destructive">{errors.target_platforms.message}</p>
                )}
              </div>

              {/* Auto Publish */}
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded border-gray-300"
                  {...register("auto_publish")}
                />
                <span>Automatically publish when video is ready</span>
              </label>
            </CardContent>
          </Card>

          {/* Submit */}
          <div className="flex justify-end space-x-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.back()}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createPipeline.isPending}>
              {createPipeline.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Start Pipeline
            </Button>
          </div>
        </form>
      </div>
    </DashboardLayout>
  );
}
