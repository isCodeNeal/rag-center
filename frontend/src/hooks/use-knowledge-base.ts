import { useMutation } from "@tanstack/react-query";
import { createKnowledgeBase } from "@/services/knowledge-base";
import type { CreateKnowledgeBaseRequest, KnowledgeBaseData } from "@/types/api";

export function useCreateKnowledgeBase() {
  return useMutation<KnowledgeBaseData, Error, CreateKnowledgeBaseRequest>({
    mutationFn: createKnowledgeBase,
  });
}
