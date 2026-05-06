# glucotracker · Android

Mobile companion for glucotracker — a personal food diary for a person with type 1 diabetes.

## Prerequisites

- Android Studio Meerkat (2024.3.1) or later
- JDK 17
- Android SDK 35
- An emulator or physical device running API 26+

## Build

```bash
./gradlew assembleDebug
```

Install on connected device:

```bash
./gradlew installDebug
```

## Verify

```bash
./gradlew lint
./gradlew test
```

## Architecture

Single-activity Jetpack Compose app with Hilt DI, Ktor HTTP client, Room for local cache,
DataStore for preferences, WorkManager for background sync, CameraX for photo capture,
Coil 3 for image loading, and kotlinx-datetime for date/time handling.

## Fonts

All fonts are OFL-licensed:
- PT Serif (Google Fonts / ParaType)
- Inter (Rasmus Andersson)
- JetBrains Mono (JetBrains)
