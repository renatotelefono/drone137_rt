// drone137 ESP32 camera bench: no arming endpoint, mixer or motor PWM.
#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "esp_system.h"
#if __has_include("config.h")
#include "config.h"
#else
#include "config.example.h"
#endif

static httpd_handle_t server = nullptr;
static char boot_id[17];
static uint64_t sequence = 0;
// Proposed carrier assignments. Camera-only firmware always drives these LOW.
static const int motor_gates[] = {1, 2, 4, 7};

static esp_err_t capture(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_set_status(req, "503 Service Unavailable");
    return httpd_resp_sendstr(req, "Capture unavailable");
  }
  if (fb->format != PIXFORMAT_JPEG || fb->len > 200000) {
    esp_camera_fb_return(fb);
    return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "JPEG exceeds camera contract");
  }
  char frame_id[24], captured[24], width[12], height[12];
  snprintf(frame_id, sizeof(frame_id), "%llu", (unsigned long long)++sequence);
  uint64_t us = (uint64_t)fb->timestamp.tv_sec * 1000000ULL + fb->timestamp.tv_usec;
  snprintf(captured, sizeof(captured), "%llu", (unsigned long long)us);
  snprintf(width, sizeof(width), "%u", (unsigned)fb->width);
  snprintf(height, sizeof(height), "%u", (unsigned)fb->height);
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  httpd_resp_set_hdr(req, "X-Boot-Id", boot_id);
  httpd_resp_set_hdr(req, "X-Frame-Id", frame_id);
  httpd_resp_set_hdr(req, "X-Capture-Time-Us", captured);
  httpd_resp_set_hdr(req, "X-Width", width);
  httpd_resp_set_hdr(req, "X-Height", height);
  esp_err_t result = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return result;
}

void setup() {
  for (int pin : motor_gates) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  Serial.begin(115200);
  snprintf(boot_id, sizeof(boot_id), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
  if (!psramFound()) {
    Serial.println("PSRAM required. Select XIAO_ESP32S3 with OPI PSRAM.");
    return;
  }
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = 15; c.pin_d1 = 17; c.pin_d2 = 18; c.pin_d3 = 16;
  c.pin_d4 = 14; c.pin_d5 = 12; c.pin_d6 = 11; c.pin_d7 = 48;
  c.pin_xclk = 10; c.pin_pclk = 13; c.pin_vsync = 38; c.pin_href = 47;
  c.pin_sccb_sda = 40; c.pin_sccb_scl = 39;
  c.pin_pwdn = -1; c.pin_reset = -1;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_VGA;
  c.jpeg_quality = 14;
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("Camera initialization failed: 0x%x\n", err);
    return;
  }
  sensor_t *sensor = esp_camera_sensor_get();
  Serial.printf("Sensor PID: 0x%04x; verify focus/orientation on the bench\n", sensor->id.PID);
  // Camera modules vary (OV2640/OV3660/OV5640). No autofocus success is assumed.
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(CAMERA_WIFI_SSID, CAMERA_WIFI_PASSWORD);
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 30000) delay(100);
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi unavailable; reset after checking credentials/network.");
    return;
  }
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.max_open_sockets = 2;
  config.lru_purge_enable = true;
  config.send_wait_timeout = 2;
  config.recv_wait_timeout = 2;
  if (httpd_start(&server, &config) != ESP_OK) {
    Serial.println("HTTP server failed");
    return;
  }
  httpd_uri_t uri = {};
  uri.uri = "/capture"; uri.method = HTTP_GET; uri.handler = capture;
  if (httpd_register_uri_handler(server, &uri) != ESP_OK) {
    httpd_stop(server); server = nullptr;
    Serial.println("HTTP route failed");
    return;
  }
  Serial.printf("drone137 camera bench: http://%s/capture\n", WiFi.localIP().toString().c_str());
  Serial.println("MOTORS DISABLED. Camera bench firmware is not flight firmware.");
}

void loop() { delay(100); }
