# Glucotracker Bridge

Glucotracker uses a separate, AGPL-licensed Gadgetbridge fork for direct
communication with the Amazfit Helio Strap. The fork lives in a separate
repository so Bluetooth ownership and Gadgetbridge's copyleft boundary do not
become part of the Glucotracker APK.

The fork uses the Android package `com.glucotracker.bridge`, so it can be
installed next to an upstream Gadgetbridge build without overwriting that
app's database or settings. Only one app may own the Helio Strap connection at
a time.

## Data path

1. The gluco Android flavor sends a signature-protected sync request.
2. Glucotracker Bridge connects to the paired Helio Strap and fetches activity,
   heart rate, HRV, sleep, SpO2 and stress records.
3. Bridge writes those records to Health Connect.
4. Only after that export finishes, Glucotracker reads Health Connect and sends
   the permitted records to its own backend.

The food flavor contains neither the IPC client nor Health Connect code.

## Pairing migration from Zepp

Do not remove the strap inside Zepp and do not factory-reset it before saving
the Huami authentication key. Either action invalidates the key.

1. While the strap is still paired in Zepp, retrieve its auth key using a
   supported Huami-token method.
2. Stop Zepp and uninstall it without unpairing the strap in Zepp.
3. Install Glucotracker Bridge, add the Helio Strap, and enter the key with the
   `0x` prefix when requested.
4. Accept companion-device pairing so Android can keep the BLE service
   available in the background.
5. In Bridge, grant Health Connect write permissions and select the Helio Strap
   for export.
6. In Glucotracker, open **Ещё → Браслет** and use
   **Синхронизировать браслет**.

## Trust boundary

The control receiver requires
`com.glucotracker.mobile.permission.CONTROL_WEARABLE_BRIDGE` with Android's
`signature` protection level. Production builds of both APKs therefore need to
be signed with the same release key. A differently signed application cannot
connect the strap or request an export through this interface.

The fork keeps Gadgetbridge's lack of the Android `INTERNET` permission. Server
upload remains Glucotracker's responsibility.
