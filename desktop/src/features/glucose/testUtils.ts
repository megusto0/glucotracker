export {
  CGM_INTERVAL_MS,
  MIN_CHECK_INTERVAL_MS,
  POST_DETECTION_DELAY_MS,
  SENSOR_DISCONNECTED_AFTER_MS,
  calculateBackoffMs,
  calculateNextCheckDelay,
  delayFromLatestReading,
  isSensorStreamDisconnected,
  sensorReadingAgeMs,
} from "./glucoseSyncTiming";
