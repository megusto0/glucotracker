# glucotracker · Android

Mobile companion for glucotracker — a personal food diary for a person with type 1 diabetes.

## Prerequisites

- Android Studio Meerkat (2024.3.1) or later
- JDK 17
- Android SDK 35
- An emulator or physical device running API 26+

## Build

```bash
./gradlew assembleGlucoDebug assembleFoodDebug
```

Install both flavors on a connected device:

```bash
./gradlew installGlucoDebug
./gradlew installFoodDebug
```

The `gluco` flavor keeps package `com.glucotracker.mobile`. The `food` flavor installs
side-by-side as `com.glucotracker.mobile.food` and uses the launcher name `Журнал`.

## Verify

```bash
./gradlew lint testGlucoDebug testFoodDebug
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
