"use client";

import React from "react";

interface RecentAnalysis {
  id: string;
  previewUrl: string;
  totalCalories: number;
  foods: string[];
  timestamp: number; // Unix ms
}

interface RecentCardProps {
  item: RecentAnalysis;
  onRecall: (item: RecentAnalysis) => void;
}

function timeAgo(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "Baru saja";
  if (mins < 60) return `${mins}m lalu`;
  if (hours < 24) return `${hours}j lalu`;
  return `${days}h lalu`;
}

export default function RecentCard({ item, onRecall }: RecentCardProps) {
  return (
    <button className="recentCard" onClick={() => onRecall(item)} type="button">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={item.previewUrl}
        alt="Food preview"
        className="recentThumb"
      />
      <div className="recentInfo">
        <p className="recentFoods">{item.foods.slice(0, 2).join(", ")}</p>
        <div className="recentMeta">
          <span className="recentCals">{item.totalCalories} kkal</span>
          <span className="recentTime">{timeAgo(item.timestamp)}</span>
        </div>
      </div>
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--muted)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ flexShrink: 0 }}
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </button>
  );
}
