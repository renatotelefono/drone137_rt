#pragma once
// Offline, unprovisioned build: motor outputs are always disabled.
// scripts/esp32_firmware.py creates ignored per-aircraft configuration instead.
#define D137_DEVICE_ID "unprovisioned"
#define D137_WIFI_SSID ""
#define D137_WIFI_PASSWORD ""
#define D137_CREDENTIAL ""
#define D137_CERTIFICATE ""
#define D137_PRIVATE_KEY ""
#define D137_PROVISIONED 0
#define D137_OUTPUTS_ENABLED 0
#define D137_COMMISSIONED 0
#define D137_BENCH_OUTPUTS 0
#define D137_VBAT_SCALE 2.0
// Sensor axes must be physically verified: +X forward, +Y left, +Z up.
static const float D137_IMU_TO_FLU[9]={1,0,0,0,1,0,0,0,1};

#define D137_RESTRAINED_RIG 0
