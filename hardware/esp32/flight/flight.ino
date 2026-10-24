// Scout 110-B prototype. Board-side stabilization; ground PC supplies bounded goals.
// No autonomous position/height controller or qualified flight gains are claimed.
#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <atomic>
#include "esp_camera.h"
#include "esp_https_server.h"
#include "esp_timer.h"
#include "esp_task_wdt.h"
#include "driver/ledc.h"
#include "flight_wire.h"
#if !CONFIG_SCCB_HARDWARE_I2C_PORT1 || !CONFIG_CAMERA_CORE0 || CONFIG_FREERTOS_HZ < 1000 || CONFIG_LWIP_MAX_SOCKETS < 16
#error "Scout requires camera I2C1/core0, 1 kHz scheduler and 16 sockets; use pinned ESP32 core"
#endif
#if __has_include("config.h")
#include "config.h"
#else
#include "config.example.h"
#endif

static const int motor_pins[]={1,2,4,7};
static d137::FlightCore controller;
static SemaphoreHandle_t state_mutex;
static portMUX_TYPE output_lock=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<bool> output_fault{false};
static std::atomic<uint64_t> loop_stamp{0};
static bool pwm_ready=false,camera_ready=false;
struct Sample {uint64_t stamp;d137::Vec gyro,acc;};
static Sample ring[256];
static unsigned ring_head=0,ring_count=0;
static char boot_id[33];
static httpd_handle_t control_server=nullptr,camera_server=nullptr,stop_server=nullptr;

static uint64_t clock_us(){return esp_timer_get_time();}
static void token(char* result){
  uint8_t bytes[16];esp_fill_random(bytes,sizeof(bytes));
  for(int i=0;i<16;i++)snprintf(result+2*i,3,"%02x",bytes[i]);
}
static void outputs(const std::array<double,4>& duty){
  portENTER_CRITICAL(&output_lock);
  for(int i=0;i<4;i++){
    uint32_t value=(!output_fault.load()&&((D137_OUTPUTS_ENABLED&&(D137_COMMISSIONED||D137_RESTRAINED_RIG))||D137_BENCH_OUTPUTS))?uint32_t(d137::clamp(duty[i],0,.9)*1023):0;
    if(pwm_ready){ledc_set_duty(LEDC_LOW_SPEED_MODE,ledc_channel_t(i+1),value);ledc_update_duty(LEDC_LOW_SPEED_MODE,ledc_channel_t(i+1));}
    else digitalWrite(motor_pins[i],LOW);
  }
  portEXIT_CRITICAL(&output_lock);
}
static void latch_stop(){output_fault.store(true);outputs({0,0,0,0});}
static bool read_registers(uint8_t reg,uint8_t* data,size_t size){
  Wire.beginTransmission(0x68);Wire.write(reg);
  if(Wire.endTransmission(false)!=0)return false;
  if(Wire.requestFrom(uint8_t(0x68),size,true)!=size)return false;
  for(size_t i=0;i<size;i++)data[i]=Wire.read();return true;
}
static bool write_register(uint8_t reg,uint8_t value){
  Wire.beginTransmission(0x68);Wire.write(reg);Wire.write(value);return Wire.endTransmission()==0;
}
static d137::Vec rotate(d137::Vec v){
  const float* r=D137_IMU_TO_FLU;
  return {r[0]*v.x+r[1]*v.y+r[2]*v.z,r[3]*v.x+r[4]*v.y+r[5]*v.z,r[6]*v.x+r[7]*v.y+r[8]*v.z};
}
static bool imu_init(){
  Wire.begin(5,6,400000);Wire.setTimeOut(3);
  uint8_t id=0;
  if(!read_registers(0x75,&id,1)||id!=0x68)return false;
  if(!write_register(0x6b,0x80))return false;
  delay(100);
  // PLL gyro clock, 500 Hz, DLPF 44/42 Hz, gyro +/-2000 dps, accel +/-8 g.
  const uint8_t settings[][2]={{0x6b,1},{0x6c,0},{0x19,1},{0x1a,3},{0x1b,0x18},{0x1c,0x10},{0x38,1}};
  for(auto& p:settings){if(!write_register(p[0],p[1]))return false;uint8_t value;if(!read_registers(p[0],&value,1)||value!=p[1])return false;}
  return true;
}
static void flight_task(void*){
  esp_task_wdt_add(nullptr);
  TickType_t last=xTaskGetTickCount();
  double voltage=analogReadMilliVolts(9)*D137_VBAT_SCALE/1000.;
  for(;;){
    uint64_t now=clock_us();uint8_t ready=0,data[14];
    if(output_fault.load()){outputs({0,0,0,0});vTaskDelay(pdMS_TO_TICKS(2));esp_task_wdt_reset();continue;}
    if(!read_registers(0x3a,&ready,1)){latch_stop();continue;}
    if(!(ready&1)){vTaskDelayUntil(&last,pdMS_TO_TICKS(2));continue;}
    if(!read_registers(0x3b,data,14)){latch_stop();continue;}
    auto signed_word=[&](int n){return int16_t((uint16_t(data[n])<<8)|data[n+1]);};
    const double g=d137::G/4096.,w=3.141592653589793/180./16.4;
    d137::Vec acc=rotate({signed_word(0)*g,signed_word(2)*g,signed_word(4)*g});
    d137::Vec gyro=rotate({signed_word(8)*w,signed_word(10)*w,signed_word(12)*w});
    // Low-pass divider noise. Low voltage is still evaluated by the controller.
    voltage+=.04*(analogReadMilliVolts(9)*D137_VBAT_SCALE/1000.-voltage);
    if(xSemaphoreTake(state_mutex,pdMS_TO_TICKS(2))!=pdTRUE){latch_stop();continue;}
    controller.imu(now,gyro,acc,voltage);
    ring[ring_head]={now,gyro,acc};ring_head=(ring_head+1)%256;ring_count=std::min(256u,ring_count+1);
    if(controller.fault_latched)output_fault.store(true);
    outputs(controller.motors);loop_stamp.store(now);
    xSemaphoreGive(state_mutex);esp_task_wdt_reset();
    vTaskDelayUntil(&last,pdMS_TO_TICKS(2));
  }
}
static void supervisor_task(void*){
  for(;;){
    uint64_t stamp=loop_stamp.load();
    if(stamp&&clock_us()-stamp>20000)latch_stop();
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}
static bool authorized(httpd_req_t* req){
  char value[128]{};size_t n=httpd_req_get_hdr_value_len(req,"Authorization");
  if(!D137_PROVISIONED||n!=7+strlen(D137_CREDENTIAL)||n>=sizeof(value)||httpd_req_get_hdr_value_str(req,"Authorization",value,sizeof(value))!=ESP_OK)return false;
  unsigned diff=0;const char* prefix="Bearer ";
  for(size_t i=0;i<n;i++)diff|=uint8_t(value[i])^uint8_t(i<7?prefix[i]:D137_CREDENTIAL[i-7]);
  return diff==0;
}
static esp_err_t json_reply(httpd_req_t* req,cJSON* value,int status=200){
  const char* label=status==200?"200 OK":status==400?"400 Bad Request":status==401?"401 Unauthorized":status==409?"409 Conflict":status==423?"423 Locked":"503 Service Unavailable";
  httpd_resp_set_status(req,label);httpd_resp_set_type(req,"application/json");httpd_resp_set_hdr(req,"Cache-Control","no-store");
  char* body=cJSON_PrintUnformatted(value);cJSON_Delete(value);
  if(!body)return ESP_FAIL;
  esp_err_t result=httpd_resp_sendstr(req,body);cJSON_free(body);return result;
}
static esp_err_t failure(httpd_req_t* req,const char* reason,int code){
  int status;return json_reply(req,d137::error(reason,code,status),code);
}
static esp_err_t control(httpd_req_t* req){
  if(!authorized(req))return failure(req,"Authentication required",401);
  char body[1537]{};
  if(req->content_len>1536)return failure(req,"Body too large",400);
  size_t got=0;
  while(got<req->content_len){int n=httpd_req_recv(req,body+got,req->content_len-got);if(n<=0)return ESP_FAIL;got+=n;}
  // Embedded NUL must not truncate an authenticated command.
  if(strlen(body)!=got)return failure(req,"Invalid request encoding",400);
  char session[33];token(session);
  if(xSemaphoreTake(state_mutex,pdMS_TO_TICKS(3))!=pdTRUE)return failure(req,"Controller busy",503);
  if(output_fault.load())controller.fault("Hardware runtime fault");
  int status=200;cJSON* reply=d137::handle(controller,req->uri,body,clock_us(),session,status);
  outputs(controller.motors);
  xSemaphoreGive(state_mutex);
  if(!strcmp(req->uri,"/v1/hello")){
    d137::text(reply,"kind","aircraft");d137::text(reply,"firmware","scout-flight-prototype-v1");
    d137::boolean(reply,"mission_ready",false);d137::boolean(reply,"camera_ready",camera_ready);
    d137::number(reply,"free_heap_bytes",ESP.getFreeHeap());d137::number(reply,"minimum_free_heap_bytes",ESP.getMinFreeHeap());
    auto* channels=cJSON_AddObjectToObject(reply,"channels");d137::number(channels,"camera_port",8444);d137::number(channels,"emergency_port",8445);
  }
  return json_reply(req,reply,status);
}
static esp_err_t imu_stream(httpd_req_t* req){
  if(!authorized(req))return failure(req,"Authentication required",401);
  char query[64]{},cursor[32]{};
  if(httpd_req_get_url_query_str(req,query,sizeof(query))!=ESP_OK||httpd_query_key_value(query,"after_us",cursor,sizeof(cursor))!=ESP_OK)return failure(req,"Invalid IMU cursor",400);
  if(!*cursor)return failure(req,"Invalid IMU cursor",400);
  for(char* p=cursor;*p;p++)if(*p<'0'||*p>'9')return failure(req,"Invalid IMU cursor",400);
  char* end;errno=0;uint64_t after=strtoull(cursor,&end,10);if(errno||*end)return failure(req,"Invalid IMU cursor",400);
  // Snapshot first; JSON/network work never holds the real-time controller lock.
  Sample* copy=static_cast<Sample*>(malloc(sizeof(ring)));if(!copy)return failure(req,"No sample buffer",503);
  if(xSemaphoreTake(state_mutex,pdMS_TO_TICKS(3))!=pdTRUE){free(copy);return failure(req,"Controller busy",503);}
  unsigned count=ring_count;for(unsigned i=0;i<count;i++)copy[i]=ring[(ring_head+256-count+i)%256];
  xSemaphoreGive(state_mutex);
  auto* reply=cJSON_CreateObject();d137::text(reply,"boot_id",boot_id);d137::number(reply,"clock_us",clock_us());
  d137::number(reply,"oldest_time_us",count?copy[0].stamp:0);d137::boolean(reply,"overrun",after&&count&&copy[0].stamp>after+20000);
  auto* samples=cJSON_AddArrayToObject(reply,"samples");
  for(unsigned i=0;i<count;i++)if(copy[i].stamp>after){
    auto* s=cJSON_CreateObject();d137::number(s,"time_us",copy[i].stamp);
    double gyro[]={copy[i].gyro.x,copy[i].gyro.y,copy[i].gyro.z},acc[]={copy[i].acc.x,copy[i].acc.y,copy[i].acc.z};
    cJSON_AddItemToObject(s,"gyro_flu_rad_s",cJSON_CreateDoubleArray(gyro,3));
    cJSON_AddItemToObject(s,"specific_force_flu_m_s2",cJSON_CreateDoubleArray(acc,3));cJSON_AddItemToArray(samples,s);
  }
  free(copy);return json_reply(req,reply);
}
static esp_err_t camera(httpd_req_t* req){
  if(!authorized(req))return failure(req,"Authentication required",401);
  if(!camera_ready)return failure(req,"Camera unavailable",503);
  camera_fb_t* frame=esp_camera_fb_get();if(!frame)return failure(req,"Capture unavailable",503);
  uint64_t capture=uint64_t(frame->timestamp.tv_sec)*1000000+frame->timestamp.tv_usec;
  if(frame->format!=PIXFORMAT_JPEG||frame->len>200000||clock_us()-capture>250000){esp_camera_fb_return(frame);return failure(req,"Stale or oversized image",503);}
  static uint64_t sequence=0;
  char seq[24],stamp[24],width[12],height[12];
  snprintf(seq,sizeof(seq),"%llu",(unsigned long long)++sequence);snprintf(stamp,sizeof(stamp),"%llu",(unsigned long long)capture);
  snprintf(width,sizeof(width),"%u",unsigned(frame->width));snprintf(height,sizeof(height),"%u",unsigned(frame->height));
  httpd_resp_set_type(req,"image/jpeg");httpd_resp_set_hdr(req,"Cache-Control","no-store");
  httpd_resp_set_hdr(req,"X-Boot-Id",boot_id);httpd_resp_set_hdr(req,"X-Frame-Id",seq);
  httpd_resp_set_hdr(req,"X-Capture-Time-Us",stamp);httpd_resp_set_hdr(req,"X-Width",width);httpd_resp_set_hdr(req,"X-Height",height);
  esp_err_t result=httpd_resp_send(req,reinterpret_cast<char*>(frame->buf),frame->len);esp_camera_fb_return(frame);return result;
}
static bool start_server(httpd_handle_t* server,uint16_t port,uint16_t control_port){
  httpd_ssl_config_t c=HTTPD_SSL_CONFIG_DEFAULT();c.port_secure=port;c.httpd.ctrl_port=control_port;
  c.httpd.core_id=0;c.httpd.task_priority=4;c.httpd.max_open_sockets=2;c.httpd.max_uri_handlers=5;
  c.httpd.recv_wait_timeout=1;c.httpd.send_wait_timeout=1;c.tls_handshake_timeout_ms=1500;c.httpd.lru_purge_enable=true;
  c.servercert=reinterpret_cast<const uint8_t*>(D137_CERTIFICATE);c.servercert_len=strlen(D137_CERTIFICATE)+1;
  c.prvtkey_pem=reinterpret_cast<const uint8_t*>(D137_PRIVATE_KEY);c.prvtkey_len=strlen(D137_PRIVATE_KEY)+1;
  return httpd_ssl_start(server,&c)==ESP_OK;
}
static bool route(httpd_handle_t s,const char* path,httpd_method_t method,esp_err_t(*fn)(httpd_req_t*)){
  httpd_uri_t uri={};uri.uri=path;uri.method=method;uri.handler=fn;return httpd_register_uri_handler(s,&uri)==ESP_OK;
}
void setup(){
  for(int pin:motor_pins){digitalWrite(pin,LOW);pinMode(pin,OUTPUT);}Serial.begin(115200);
  token(boot_id);controller.reset(D137_DEVICE_ID,boot_id);
  controller.outputs_enabled=D137_OUTPUTS_ENABLED;controller.commissioned=D137_COMMISSIONED;
  controller.bench_enabled=D137_BENCH_OUTPUTS;controller.rig_enabled=D137_RESTRAINED_RIG;
  state_mutex=xSemaphoreCreateMutex();if(!state_mutex){latch_stop();return;}
  // Camera uses timer/channel 0. Motors use timer 1, channels 1..4, at 24 kHz.
  ledc_timer_config_t timer={};timer.speed_mode=LEDC_LOW_SPEED_MODE;timer.timer_num=LEDC_TIMER_1;
  timer.duty_resolution=LEDC_TIMER_10_BIT;timer.freq_hz=24000;timer.clk_cfg=LEDC_AUTO_CLK;
  if(ledc_timer_config(&timer)!=ESP_OK){latch_stop();return;}
  for(int i=0;i<4;i++){
    ledc_channel_config_t c={};c.gpio_num=motor_pins[i];c.speed_mode=LEDC_LOW_SPEED_MODE;c.channel=ledc_channel_t(i+1);c.timer_sel=LEDC_TIMER_1;
    if(ledc_channel_config(&c)!=ESP_OK){latch_stop();return;}
  }
  pwm_ready=true;outputs({0,0,0,0});
  analogReadResolution(12);analogSetPinAttenuation(9,ADC_11db);
  if(!imu_init()){Serial.println("IMU initialization failed; outputs disabled");latch_stop();return;}
  loop_stamp.store(clock_us());
  if(xTaskCreatePinnedToCore(flight_task,"flight",6144,nullptr,20,nullptr,1)!=pdPASS||
     xTaskCreatePinnedToCore(supervisor_task,"supervisor",2048,nullptr,22,nullptr,0)!=pdPASS){latch_stop();return;}
  if(psramFound()){
    camera_config_t c={};c.ledc_channel=LEDC_CHANNEL_0;c.ledc_timer=LEDC_TIMER_0;
    c.pin_d0=15;c.pin_d1=17;c.pin_d2=18;c.pin_d3=16;c.pin_d4=14;c.pin_d5=12;c.pin_d6=11;c.pin_d7=48;
    c.pin_xclk=10;c.pin_pclk=13;c.pin_vsync=38;c.pin_href=47;c.pin_sccb_sda=40;c.pin_sccb_scl=39;c.pin_pwdn=-1;c.pin_reset=-1;
    c.xclk_freq_hz=20000000;c.pixel_format=PIXFORMAT_JPEG;c.frame_size=FRAMESIZE_VGA;c.jpeg_quality=14;
    c.fb_count=2;c.fb_location=CAMERA_FB_IN_PSRAM;c.grab_mode=CAMERA_GRAB_LATEST;camera_ready=esp_camera_init(&c)==ESP_OK;
  }
  if(!D137_PROVISIONED){Serial.println("Unprovisioned build: no network, outputs disabled");return;}
  WiFi.mode(WIFI_STA);WiFi.setSleep(false);WiFi.setAutoReconnect(true);WiFi.begin(D137_WIFI_SSID,D137_WIFI_PASSWORD);
  uint64_t start=clock_us();while(WiFi.status()!=WL_CONNECTED&&clock_us()-start<30000000)delay(100);
  if(WiFi.status()!=WL_CONNECTED){Serial.println("Wi-Fi unavailable; reset after checking network");return;}
  bool ok=start_server(&control_server,443,32768)&&start_server(&camera_server,8444,32769)&&start_server(&stop_server,8445,32770);
  if(ok)ok=route(control_server,"/v1/hello",HTTP_GET,control)&&route(control_server,"/v1/session",HTTP_POST,control)&&
    route(control_server,"/v1/command",HTTP_POST,control)&&route(control_server,"/v1/imu",HTTP_GET,imu_stream)&&
    route(camera_server,"/v1/camera",HTTP_GET,camera)&&route(stop_server,"/v1/hello",HTTP_GET,control)&&
    route(stop_server,"/v1/emergency",HTTP_POST,control);
  if(!ok){latch_stop();Serial.println("HTTPS startup failed; outputs disabled");return;}
  Serial.printf("Drone137 %s https://%s (camera 8444, stop 8445)\n",D137_DEVICE_ID,WiFi.localIP().toString().c_str());
  Serial.println("Prototype firmware. Physical commissioning and restrained tuning required.");
}
void loop(){delay(100);}
