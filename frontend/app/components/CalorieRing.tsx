"use client";

import React, { useEffect, useRef } from "react";

interface CalorieRingProps {
  current: number;
  target?: number;
  size?: number;
  strokeWidth?: number;
}

const RDA_DEFAULT = 2000;

export default function CalorieRing({
  current,
  target = RDA_DEFAULT,
  size = 100,
  strokeWidth = 8,
}: CalorieRingProps) {
  const pct = Math.min((current / target) * 100, 100);
  const overPct = (current / target) * 100;

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;

  const color =
    overPct > 100
      ? "var(--calorie-over)"
      : overPct > 85
      ? "var(--calorie-warn)"
      : "var(--calorie-ok)";

  return (
    <svg
      className="calorieRing"
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`${current} dari ${target} kkal`}
    >
      {/* Track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--border)"
        strokeWidth={strokeWidth}
      />
      {/* Progress */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dashoffset 0.8s var(--ease-out), stroke 0.4s" }}
      />
      {/* Center text */}
      <text
        x={size / 2}
        y={size / 2 - 4}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={size < 80 ? "14" : "18"}
        fontWeight="800"
        fill={color}
        fontFamily="'Plus Jakarta Sans', sans-serif"
      >
        {Math.round(pct)}%
      </text>
      <text
        x={size / 2}
        y={size / 2 + (size < 80 ? 12 : 16)}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={size < 80 ? "7" : "9"}
        fill="var(--text-sec)"
        fontFamily="'Plus Jakarta Sans', sans-serif"
        fontWeight="500"
      >
        dari RDA
      </text>
    </svg>
  );
}
