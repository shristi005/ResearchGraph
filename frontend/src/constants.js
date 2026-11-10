export const REL = {
  semantic_similarity: { label: "Semantic similarity", short: "similar", color: "#3F5D4E", dash: null },
  shared_topic: { label: "Shared topic", short: "topic", color: "#D9A566", dash: null },
  shared_methodology: { label: "Shared method", short: "method", color: "#B06A4F", dash: null },
  citation: { label: "Citation", short: "cites", color: "#6B7B8B", dash: "7 6" },
};

export const CATEGORY = {
  limitation: { label: "Limitation-based", color: "#E5B5A5", blurb: "A weakness several papers report" },
  methodological: { label: "Methodological", color: "#D9C5A8", blurb: "Different methods for similar problems" },
  combination: { label: "Exploratory combination", color: "#A8C3B0", blurb: "Ideas never discussed together (a prompt, not a finding)" },
  future_work: { label: "Future work", color: "#F0D9A8", blurb: "Next steps the authors suggest" },
};

export const STATUS = {
  uploaded: { label: "Uploaded", bg: "#EFE3D1" },
  analyzing: { label: "Analyzing…", bg: "#D9A566" },
  analyzed: { label: "Analyzed", bg: "#A8C3B0" },
  embedded: { label: "Analyzed", bg: "#A8C3B0" },
  failed: { label: "Failed", bg: "#E5B5A5" },
};
