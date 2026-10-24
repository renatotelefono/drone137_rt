// Test/desktop ABI. No hardware outputs. ESP32 builds do not include this file.
#include "../hardware/esp32/flight/flight_wire.h"
#include <random>
extern "C" {
void* d137_create(const char* device,const char* boot,bool enabled) {
  auto* core=new d137::FlightCore();core->reset(device,boot);
  core->outputs_enabled=enabled;core->commissioned=enabled;return core;
}
void d137_destroy(void* p) {delete static_cast<d137::FlightCore*>(p);}
void d137_imu(void* p,uint64_t time,double gx,double gy,double gz,double ax,double ay,double az,double v) {
  static_cast<d137::FlightCore*>(p)->imu(time,{gx,gy,gz},{ax,ay,az},v);
}
void d137_tick(void* p,uint64_t time) {static_cast<d137::FlightCore*>(p)->tick(time);}
void d137_fault(void* p) {static_cast<d137::FlightCore*>(p)->fault("Runtime watchdog");}
void d137_bench(void* p,bool enabled) {static_cast<d137::FlightCore*>(p)->bench_enabled=enabled;}
void d137_rig(void* p) {auto* c=static_cast<d137::FlightCore*>(p);c->rig_enabled=true;c->outputs_enabled=true;c->commissioned=false;}
const char* d137_request(void* p,const char* path,const char* body,uint64_t now,const char* session,int* status) {
  cJSON* o=d137::handle(*static_cast<d137::FlightCore*>(p),path,body,now,session,*status);
  char* value=cJSON_PrintUnformatted(o);cJSON_Delete(o);return value;
}
void d137_free(void* p) {cJSON_free(p);}
}
