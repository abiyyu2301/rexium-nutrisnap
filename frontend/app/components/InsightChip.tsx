"use client";

import React from "react";

type InsightType = "positive" | "suggestion" | "concern" | "neutral";

interface InsightChipProps {
  text: string;
  type: InsightType;
}

const ICONS: Record<InsightType, string> = {
  positive: "✅",
  suggestion: "💡",
  concern: "⚠️",
  neutral: "ℹ️",
};

export default function InsightChip({ text, type }: InsightChipProps) {
  return (
    <span className={`insightChip ${type}`}>
      {ICONS[type]} {text}
    </span>
  );
}
