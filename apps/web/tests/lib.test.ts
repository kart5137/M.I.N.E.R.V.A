/**
 * Unit tests for display helpers and colour-class rules (M8).
 * Run with `npm test` (Node's built-in test runner; Node strips the TypeScript types).
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { changeClass, giClass, moranClass } from "../src/lib/detection-scale.ts";
import {
  addWeeks,
  formatInt,
  formatPct,
  formatSigned,
  formatWeek,
  isoWeekLabel,
  mondayOf,
  weeksBetween,
  windowLabel,
} from "../src/lib/format.ts";
import { MIN_SPECIMENS, positivityClass } from "../src/lib/positivity-scale.ts";
import type { CountryWindowValue, HotspotItem } from "../src/lib/types.ts";

describe("format", () => {
  it("shows missing values as a dash, never zero", () => {
    assert.equal(formatInt(null), "—");
    assert.equal(formatPct(undefined), "—");
    assert.equal(formatWeek(null), "—");
    assert.equal(formatInt(0), "0");
  });

  it("formats numbers", () => {
    assert.equal(formatInt(146533.4), "146,533");
    assert.equal(formatPct(0.0767), "7.7%");
    assert.equal(formatSigned(1.24, 1, " pp"), "+1.2 pp");
    assert.equal(formatSigned(-0.4), "−0.4");
    assert.equal(formatSigned(-0.04), "±0.0");
  });

  it("handles ISO weeks across year boundaries", () => {
    assert.equal(formatWeek("2026-10-12"), "12 Oct 2026");
    assert.equal(isoWeekLabel("2024-12-30"), "2025-W01");
    assert.equal(isoWeekLabel("2021-01-03"), "2020-W53");
    assert.equal(mondayOf("2025-01-05"), "2024-12-30");
    assert.equal(addWeeks("2024-12-30", 2), "2025-01-13");
    assert.equal(weeksBetween("2024-12-30", "2025-03-31"), 13);
    assert.equal(windowLabel({ start: "2025-01-06", end: "2025-01-06", weeks: 1 }), "Week of 6 Jan 2025");
  });
});

describe("positivity classes", () => {
  const v = (positivity: number | null, specimens_tested: number | null) =>
    ({ positivity, specimens_tested }) as CountryWindowValue;

  it("separates no data, too few specimens and bins", () => {
    assert.equal(positivityClass(undefined), -1);
    assert.equal(positivityClass(v(null, 500)), -1);
    assert.equal(positivityClass(v(0.5, MIN_SPECIMENS - 1)), 0);
    assert.equal(positivityClass(v(0.0, 100)), 1);
    assert.equal(positivityClass(v(0.05, 100)), 2); // bin edges are upper-exclusive
    assert.equal(positivityClass(v(0.39, 100)), 5);
    assert.equal(positivityClass(v(0.9, 100)), 6);
  });
});

describe("detection classes", () => {
  const h = (z: number, p: number, fdr: number, cls = "ns") =>
    ({
      gi_star: { z_score: z, p_value: p, p_fdr: fdr },
      local_moran: { classification: cls },
    }) as unknown as HotspotItem;

  it("Gi*: FDR-significant is strong, nominal-only is weak", () => {
    assert.equal(giClass(h(3, 0.001, 0.01)), 1);
    assert.equal(giClass(h(2, 0.01, 0.2)), 2);
    assert.equal(giClass(h(-2, 0.01, 0.2)), 3);
    assert.equal(giClass(h(-3, 0.001, 0.01)), 4);
    assert.equal(giClass(h(1, 0.3, 0.6)), 0);
  });

  it("Local Moran and forecast change", () => {
    assert.deepEqual(["HH", "LL", "HL", "LH", "ns"].map((c) => moranClass(h(0, 1, 1, c))), [1, 2, 3, 3, 0]);
    assert.deepEqual([6, 2, 0.5, -0.5, -2, -5].map(changeClass), [2, 1, 0, 0, 3, 4]);
  });
});
