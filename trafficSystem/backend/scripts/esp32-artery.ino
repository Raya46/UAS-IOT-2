// ESP32-S3 WROOM Dashcam — MJPEG stream + MQTT status
// ponytail: HTTP MJPEG for video (proven pattern), MQTT for discovery/control only

#include <WiFi.h>
#include <esp_camera.h>
#include <esp_http_server.h>
#include <ESPmDNS.h>

// ── WiFi ──
const char* ssid     = "rayarayaraya";
const char* password = "123456789";

// ── MQTT (optional — camera works without it) ──
#define MQTT_ENABLED true
#if MQTT_ENABLED
#include <PubSubClient.h>
// ponytail: change to your computer/broker IP on the same WiFi
const char* mqtt_server = "10.194.248.176";
const int   mqtt_port   = 1883;
const char* mqtt_topic_status  = "traffic/esp32cam/status";
const char* mqtt_topic_control = "traffic/esp32cam/control";
WiFiClient   espClient;
PubSubClient mqtt(espClient);
unsigned long lastMqttPublish = 0;
#endif

// ── Camera pins for ESP32-S3 WROOM + OV2640 ──
// ponytail: adjust to your board — these are Freenove ESP32-S3 WROOM CAM pins
#define PWDN_GPIO_NUM   -1
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM   15
#define SIOD_GPIO_NUM    4
#define SIOC_GPIO_NUM    5
#define Y9_GPIO_NUM     16
#define Y8_GPIO_NUM     17
#define Y7_GPIO_NUM     18
#define Y6_GPIO_NUM     12
#define Y5_GPIO_NUM     10
#define Y4_GPIO_NUM      8
#define Y3_GPIO_NUM      9
#define Y2_GPIO_NUM     11
#define VSYNC_GPIO_NUM   6
#define HREF_GPIO_NUM    7
#define PCLK_GPIO_NUM   13

// Built-in LED (status indicator) — GPIO 2 on most boards
#define LED_GPIO_NUM     2

httpd_handle_t stream_httpd = NULL;

// ── MJPEG Stream Handler ──
static esp_err_t stream_handler(httpd_req_t *req) {
  static const char *STREAM_CT   = "multipart/x-mixed-replace;boundary=frame";
  static const char *STREAM_BOND = "\r\n--frame\r\n";
  static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

  httpd_resp_set_type(req, STREAM_CT);
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  char part_buf[64];
  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) return ESP_FAIL;

    size_t hlen = snprintf(part_buf, 64, STREAM_PART, fb->len);

    esp_err_t res = httpd_resp_send_chunk(req, STREAM_BOND, strlen(STREAM_BOND));
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, part_buf, hlen);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);

    esp_camera_fb_return(fb);
    if (res != ESP_OK) return res;
  }
}

// ── Single JPEG Capture ──
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { httpd_resp_send_500(req); return ESP_FAIL; }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

// ── Status endpoint (JSON) ──
static esp_err_t status_handler(httpd_req_t *req) {
  char buf[256];
  snprintf(buf, sizeof(buf),
    "{\"ip\":\"%s\",\"mac\":\"%s\",\"rssi\":%d,\"uptime\":%lu,"
    "\"stream_url\":\"http://%s/stream\",\"hostname\":\"esp32cam.local\"}",
    WiFi.localIP().toString().c_str(),
    WiFi.macAddress().c_str(),
    WiFi.RSSI(),
    millis() / 1000,
    WiFi.localIP().toString().c_str()
  );
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, buf, strlen(buf));
}

void startHttpServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.ctrl_port   = 32768;
  config.max_open_sockets = 4;
  config.lru_purge_enable = true;  // ponytail: auto-close oldest connection when full

  if (httpd_start(&stream_httpd, &config) != ESP_OK) {
    Serial.println("HTTP server start failed");
    return;
  }

  httpd_uri_t stream_uri  = { .uri = "/stream",  .method = HTTP_GET, .handler = stream_handler };
  httpd_uri_t capture_uri = { .uri = "/capture", .method = HTTP_GET, .handler = capture_handler };
  httpd_uri_t status_uri  = { .uri = "/status",  .method = HTTP_GET, .handler = status_handler };

  httpd_register_uri_handler(stream_httpd, &stream_uri);
  httpd_register_uri_handler(stream_httpd, &capture_uri);
  httpd_register_uri_handler(stream_httpd, &status_uri);
}

void initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // ponytail: auto-detect PSRAM for resolution ceiling
  if (psramFound()) {
    config.frame_size   = FRAMESIZE_VGA;   // 640x480
    config.jpeg_quality = 12;
    config.fb_count     = 2;
    config.grab_mode    = CAMERA_GRAB_LATEST;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
    Serial.println("PSRAM found — VGA mode, 2 frame buffers");
  } else {
    config.frame_size   = FRAMESIZE_QVGA;  // 320x240
    config.jpeg_quality = 15;
    config.fb_count     = 1;
    config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
    Serial.println("No PSRAM — QVGA mode, 1 frame buffer");
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);
    s->set_saturation(s, 0);
    // ponytail: auto-exposure + auto-whitebalance for outdoor dashcam
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 1);
  }
}

// ── MQTT ──
#if MQTT_ENABLED
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];

  if (msg == "restart") {
    Serial.println("MQTT restart command received");
    ESP.restart();
  }
  if (msg.startsWith("resolution:")) {
    sensor_t *s = esp_camera_sensor_get();
    if (!s) return;
    String res = msg.substring(11);
    if      (res == "QVGA") s->set_framesize(s, FRAMESIZE_QVGA);
    else if (res == "CIF")  s->set_framesize(s, FRAMESIZE_CIF);
    else if (res == "VGA")  s->set_framesize(s, FRAMESIZE_VGA);
    else if (res == "SVGA") s->set_framesize(s, FRAMESIZE_SVGA);
    else if (res == "XGA")  s->set_framesize(s, FRAMESIZE_XGA);
    Serial.printf("Resolution changed to %s\n", res.c_str());
  }
}

void publishStatus() {
  if (!mqtt.connected()) return;
  char buf[256];
  snprintf(buf, sizeof(buf),
    "{\"ip\":\"%s\",\"stream_url\":\"http://%s/stream\","
    "\"mac\":\"%s\",\"rssi\":%d,\"uptime\":%lu}",
    WiFi.localIP().toString().c_str(),
    WiFi.localIP().toString().c_str(),
    WiFi.macAddress().c_str(),
    WiFi.RSSI(),
    millis() / 1000
  );
  mqtt.publish(mqtt_topic_status, buf);
}

void mqttReconnect() {
  if (mqtt.connected()) return;
  String clientId = "esp32cam-" + WiFi.macAddress();
  if (mqtt.connect(clientId.c_str())) {
    Serial.println("MQTT connected");
    mqtt.subscribe(mqtt_topic_control);
    publishStatus();
  }
}
#endif

// ── WiFi reconnect ──
void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.println("WiFi lost — reconnecting...");
  WiFi.disconnect();
  WiFi.begin(ssid, password);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(500);
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi reconnected: %s\n", WiFi.localIP().toString().c_str());
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);

  // Status LED
  pinMode(LED_GPIO_NUM, OUTPUT);
  digitalWrite(LED_GPIO_NUM, LOW);

  // WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi OK — IP: %s\n", WiFi.localIP().toString().c_str());
  digitalWrite(LED_GPIO_NUM, HIGH);

  // mDNS — accessible at http://esp32cam.local
  if (MDNS.begin("esp32cam")) {
    Serial.println("mDNS: esp32cam.local");
    MDNS.addService("http", "tcp", 80);
  }

  // Camera
  initCamera();

  // HTTP server (MJPEG stream + capture + status)
  startHttpServer();
  Serial.printf("Stream:  http://%s/stream\n", WiFi.localIP().toString().c_str());
  Serial.printf("Capture: http://%s/capture\n", WiFi.localIP().toString().c_str());
  Serial.printf("Status:  http://%s/status\n", WiFi.localIP().toString().c_str());

  // MQTT
#if MQTT_ENABLED
  mqtt.setServer(mqtt_server, mqtt_port);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(512);
  Serial.printf("MQTT broker: %s:%d\n", mqtt_server, mqtt_port);
#endif
}

void loop() {
  ensureWiFi();

#if MQTT_ENABLED
  if (!mqtt.connected()) mqttReconnect();
  mqtt.loop();

  // Publish status every 30s
  if (millis() - lastMqttPublish > 30000) {
    publishStatus();
    lastMqttPublish = millis();
  }
#endif
}
