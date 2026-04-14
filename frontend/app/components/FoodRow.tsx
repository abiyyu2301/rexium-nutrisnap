"use client";

import React from "react";

interface IdentifiedFood {
  raw_name: string;
  matched_name: string | null;
  calories_kcal: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  fiber_g: number | null;
  confidence: number;
  source: string | null;
}

interface FoodRowProps {
  food: IdentifiedFood;
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const level = pct >= 80 ? "high" : pct >= 60 ? "mid" : "low";
  return (
    <span className={`confBadge ${level}`} title={`Tingkat kepercayaan: ${pct}%`}>
      {pct}%
    </span>
  );
}

function MacroMiniPills({ food }: { food: IdentifiedFood }) {
  const items = [
    { label: "P", value: food.protein_g, color: "var(--protein)" },
    { label: "K", value: food.carbs_g, color: "var(--carbs)" },
    { label: "L", value: food.fat_g, color: "var(--fat)" },
  ];

  return (
    <div className="foodMacros">
      {items.map(
        (m) =>
          m.value != null && (
            <span
              key={m.label}
              className="foodMacroPill"
              style={{ color: m.color }}
            >
              <span>{m.label}:</span>
              {m.value.toFixed(1)}g
            </span>
          )
      )}
    </div>
  );
}

export default function FoodRow({ food }: FoodRowProps) {
  const confPct = Math.round(food.confidence * 100);
  const isLowConf = confPct < 60;

  return (
    <li className="foodRow">
      <div className="foodRowHeader">
        <div className="foodInfo">
          <span className="foodName">
            {food.matched_name || food.raw_name}
          </span>
          {!food.matched_name && (
            <span className="foodNoMatch">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
              </svg>
              Tidak ditemukan di database
            </span>
          )}
          {food.matched_name && food.matched_name !== food.raw_name && (
            <span className="foodRaw">&quot;{food.raw_name}&quot;</span>
          )}
        </div>
        <ConfidenceBadge confidence={food.confidence} />
      </div>

      <MacroMiniPills food={food} />

      {food.calories_kcal != null && (
        <span
          className="foodCal"
          style={{ fontWeight: 700, color: "var(--green)", fontSize: "0.85rem" }}
        >
          {food.calories_kcal} kkal
        </span>
      )}

      {isLowConf && (
        <div className="lowConfWarning">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
          </svg>
          Tidak yakin? Coba foto lebih jelas dengan cahaya yang baik
        </div>
      )}
    </li>
  );
}
