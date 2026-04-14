"use client";

import React from "react";
import InsightChip from "./InsightChip";

type InsightType = "positive" | "suggestion" | "concern" | "neutral";

interface NutritionSummary {
  total_calories_kcal: number;
  total_protein_g: number;
  total_carbs_g: number;
  total_fat_g: number;
  total_fiber_g: number;
}

const RDA = {
  calories: 2000,
  protein: 50,
  carbs: 275,
  fat: 65,
  fiber: 30,
};

interface InsightPanelProps {
  summary: NutritionSummary;
}

function generateInsights(summary: NutritionSummary): { text: string; type: InsightType }[] {
  const insights: { text: string; type: InsightType }[] = [];

  const calPct = (summary.total_calories_kcal / RDA.calories) * 100;
  const proteinPct = (summary.total_protein_g / RDA.protein) * 100;
  const carbsPct = (summary.total_carbs_g / RDA.carbs) * 100;
  const fatPct = (summary.total_fat_g / RDA.fat) * 100;
  const fiberPct = (summary.total_fiber_g / RDA.fiber) * 100;

  // Calorie insights
  if (calPct > 120) {
    insights.push({ text: "Kalori tinggi —注意摄入量", type: "concern" });
  } else if (calPct >= 80 && calPct <= 120) {
    insights.push({ text: "Kalori pas 👍", type: "positive" });
  } else if (calPct >= 50 && calPct < 80) {
    insights.push({ text: "Kalori sedang", type: "neutral" });
  } else if (calPct < 50 && calPct > 0) {
    insights.push({ text: "Kalori rendah", type: "suggestion" });
  }

  // Protein
  if (proteinPct >= 30) {
    insights.push({ text: "Tinggi protein ✅", type: "positive" });
  }

  // Fiber
  if (fiberPct < 20 && fiberPct > 0) {
    insights.push({ text: "Rendah serat — coba tambah sayur", type: "suggestion" });
  } else if (fiberPct >= 40) {
    insights.push({ text: "Serat baik 👍", type: "positive" });
  }

  // Fat
  if (fatPct > 100) {
    insights.push({ text: "Lemak tinggi —注意油脂摄入", type: "concern" });
  } else if (fatPct >= 60 && fatPct <= 100) {
    insights.push({ text: "Lemak dalam batas normal", type: "neutral" });
  }

  // Carbs
  if (carbsPct > 100) {
    insights.push({ text: "Karbo tinggi —注意碳水摄入", type: "concern" });
  } else if (carbsPct >= 50 && carbsPct <= 100) {
    insights.push({ text: "Karbo dalam range normal", type: "neutral" });
  }

  // Cap at 4 insights
  return insights.slice(0, 4);
}

export default function InsightPanel({ summary }: InsightPanelProps) {
  const insights = generateInsights(summary);

  if (insights.length === 0) {
    return null;
  }

  return (
    <div className="insightPanel anim-card">
      <p className="insightTitle">Insight Kesehatan</p>
      <div className="insightChips">
        {insights.map((ins, i) => (
          <InsightChip key={i} text={ins.text} type={ins.type} />
        ))}
      </div>
    </div>
  );
}
