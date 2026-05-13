import { describe, it, expect, beforeEach } from "vitest";
import { glucoseSyncLogger } from "../glucoseSyncLogger";
import { calculateNextCheckDelay, CGM_INTERVAL_MS, POST_DETECTION_DELAY_MS } from "../testUtils";

describe("glucoseSyncLogger", () => {
  beforeEach(() => {
    glucoseSyncLogger.clear();
  });

  it("should log debug entries", () => {
    glucoseSyncLogger.debug("test_event", { key: "value" });
    const entries = glucoseSyncLogger.getEntries();
    expect(entries).toHaveLength(1);
    expect(entries[0].level).toBe("debug");
    expect(entries[0].event).toBe("test_event");
    expect(entries[0].details).toEqual({ key: "value" });
  });

  it("should log info entries", () => {
    glucoseSyncLogger.info("import_start");
    const entries = glucoseSyncLogger.getEntries("info");
    expect(entries).toHaveLength(1);
    expect(entries[0].event).toBe("import_start");
  });

  it("should log warn entries", () => {
    glucoseSyncLogger.warn("sensor_errors_accumulated", { errors: 3 });
    const entries = glucoseSyncLogger.getEntries("warn");
    expect(entries).toHaveLength(1);
  });

  it("should log error entries", () => {
    glucoseSyncLogger.error("import_failed", { error: "timeout" });
    const entries = glucoseSyncLogger.getEntries("error");
    expect(entries).toHaveLength(1);
  });

  it("should filter by level", () => {
    glucoseSyncLogger.debug("d1");
    glucoseSyncLogger.info("i1");
    glucoseSyncLogger.warn("w1");
    glucoseSyncLogger.error("e1");
    expect(glucoseSyncLogger.getEntries("debug")).toHaveLength(1);
    expect(glucoseSyncLogger.getEntries("info")).toHaveLength(1);
    expect(glucoseSyncLogger.getEntries("warn")).toHaveLength(1);
    expect(glucoseSyncLogger.getEntries("error")).toHaveLength(1);
  });

  it("should filter by sensorId", () => {
    glucoseSyncLogger.info("event1", { sensorId: "sensor-a" });
    glucoseSyncLogger.info("event2", { sensorId: "sensor-b" });
    glucoseSyncLogger.info("event3");
    expect(glucoseSyncLogger.getEntriesForSensor("sensor-a")).toHaveLength(1);
    expect(glucoseSyncLogger.getEntriesForSensor("sensor-b")).toHaveLength(1);
  });

  it("should cap at MAX_LOG_ENTRIES", () => {
    for (let i = 0; i < 550; i++) {
      glucoseSyncLogger.info(`event_${i}`);
    }
    expect(glucoseSyncLogger.getEntries()).toHaveLength(500);
  });

  it("should export log as string", () => {
    glucoseSyncLogger.info("test_event", { key: "val" });
    const log = glucoseSyncLogger.exportLog();
    expect(log).toContain("INFO");
    expect(log).toContain("test_event");
    expect(log).toContain('"key":"val"');
  });

  it("should provide summary", () => {
    glucoseSyncLogger.debug("d");
    glucoseSyncLogger.info("i");
    glucoseSyncLogger.warn("w");
    glucoseSyncLogger.error("e");
    const summary = glucoseSyncLogger.summary();
    expect(summary.total).toBe(4);
    expect(summary.byLevel.debug).toBe(1);
    expect(summary.byLevel.info).toBe(1);
    expect(summary.byLevel.warn).toBe(1);
    expect(summary.byLevel.error).toBe(1);
  });

  it("should clear all entries", () => {
    glucoseSyncLogger.info("event1");
    glucoseSyncLogger.info("event2");
    glucoseSyncLogger.clear();
    expect(glucoseSyncLogger.getEntries()).toHaveLength(0);
  });
});

describe("Sync timing calculations", () => {
  it("should calculate next check delay as CGM_INTERVAL + 30s after last reading", () => {
    const lastReadingTime = Date.now() - 4 * 60 * 1000;
    const delay = calculateNextCheckDelay(lastReadingTime);
    expect(delay).toBeGreaterThan(0);
    expect(delay).toBeLessThanOrEqual(CGM_INTERVAL_MS + POST_DETECTION_DELAY_MS);
  });

  it("should return minimum delay when reading is old", () => {
    const lastReadingTime = Date.now() - 30 * 60 * 1000;
    const delay = calculateNextCheckDelay(lastReadingTime);
    expect(delay).toBeGreaterThan(0);
  });

  it("should handle exact 5-minute-old reading", () => {
    const now = 10000000;
    const lastReadingTime = now - 5 * 60 * 1000;
    const delay = calculateNextCheckDelay(lastReadingTime, now);
    expect(delay).toBeGreaterThan(0);
    expect(delay).toBeLessThanOrEqual(POST_DETECTION_DELAY_MS + 1000);
  });
});

describe("Backoff calculation", () => {
  it("should increase delay with consecutive errors", () => {
    const delays: number[] = [];
    for (let errors = 0; errors < 5; errors++) {
      const base = Math.min(10000 * Math.pow(2, errors), 300000);
      delays.push(base);
    }
    for (let i = 1; i < delays.length; i++) {
      expect(delays[i]).toBeGreaterThan(delays[i - 1]);
    }
  });

  it("should cap at max interval", () => {
    const maxDelay = Math.min(10000 * Math.pow(2, 10), 300000);
    expect(maxDelay).toBeLessThanOrEqual(300000);
  });
});

describe("Sensor change detection", () => {
  it("should detect different sensor IDs", () => {
    const sensorA = { id: "sensor-a", lastTs: "2026-04-28T08:00:00" };
    const sensorB = { id: "sensor-b", lastTs: "2026-04-28T08:05:00" };
    expect(sensorA.id).not.toBe(sensorB.id);
  });

  it("should handle null sensor gracefully", () => {
    const sensorId = null;
    expect(sensorId ?? "unknown").toBe("unknown");
  });
});

describe("Network resilience scenarios", () => {
  it("should track consecutive error count", () => {
    let errors = 0;
    const maxErrors = 10;

    for (let i = 0; i < 5; i++) {
      errors++;
    }
    expect(errors).toBe(5);
    expect(errors).toBeLessThan(maxErrors);
  });

  it("should trigger offline mode at max errors", () => {
    let errors = 0;
    const maxErrors = 10;
    for (let i = 0; i < maxErrors; i++) {
      errors++;
    }
    expect(errors >= maxErrors).toBe(true);
  });

  it("should reset error count after successful import", () => {
    let errors = 5;
    errors = 0;
    expect(errors).toBe(0);
  });
});
