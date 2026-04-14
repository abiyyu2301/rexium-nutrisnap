"use client";

import React from "react";

interface MacroCardProps {
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  rdaProtein?: number;
  rdaCarbs?: number;
  rdaFat?: number;
  rdaFiber?: number;
}

const DEFAULT_RDA = {
  protein: 50,
  carbs: 275,
  fat: 65,
  fiber: 30,
};

function MacroItem({
  name,
  value,
  rda,
  color,
  bgColor,
}: {
  name: string;
  value: number;
  rda: number;
  color: string;
  bgColor: string;
}) {
  const pct = Math.min((value / rda) * 100, 100);
  return (
    <div className="macroItem" style={{ background: bgColor }}>
      <div className="macroItemHeader">
        <div
          className="macroDot"
          style={{ background: color }}
        />
        <span className="macroName">{name}</span>
        <span className="macroValue">{value.toFixed(1)}g</span>
      </div>
      <div className="macroTrack">
        <div
          className="macroFill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="macroRda">{pct.toFixed(0)}% RDA</span>
    </div>
  );
}

export default function MacroCard({
  protein_g,
  carbs_g,
  fat_g,
  fiber_g,
  rdaProtein = DEFAULT_RDA.protein,
  rdaCarbs = DEFAULT_RDA.carbs,
  rdaFat = DEFAULT_RDA.fat,
  rdaFiber = DEFAULT_RDA.fiber,
}: MacroCardProps) {
  return (
    <div className="macroCard anim-card">
      <p className="macroTitle">Makronutrien</p>
      <div className="macroGrid">
        <MacroItem
          name="Protein"
          value={protein_g}
          rda={rdaProtein}
          color="var(--protein)"
          bgColor="var(--protein-bg)"
        />
        <MacroItem
          name="Karbo"
          value={carbs_g}
          rda={rdaCarbs}
          color="var(--carbs)"
          bgColor="var(--carbs-bg)"
        />
        <MacroItem
          name="Lemak"
          value={fat_g}
          rda={rdaFat}
          color="var(--fat)"
          bgColor="var(--fat-bg)"
        />
        <MacroItem
          name="Serat"
          value={fiber_g}
          rda={rdaFiber}
          color="var(--fiber)"
          bgColor="var(--fiber-bg)"
        />
      </div>
    </div>
  );
}
