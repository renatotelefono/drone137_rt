#pragma once
#include "flight_core.h"
#include "cJSON.h"
#include <cstdio>
#include <cstdlib>

namespace d137 {
inline void number(cJSON* o,const char* key,double value) { cJSON_AddNumberToObject(o,key,value); }
inline void boolean(cJSON* o,const char* key,bool value) { cJSON_AddBoolToObject(o,key,value); }
inline void text(cJSON* o,const char* key,const char* value) {
  if(value&&*value)cJSON_AddStringToObject(o,key,value);else cJSON_AddNullToObject(o,key);
}
inline bool fields(cJSON* o,const char* const* names,int count) {
  if(!cJSON_IsObject(o)||cJSON_GetArraySize(o)!=count)return false;
  for(int i=0;i<count;i++) {
    int occurrences=0;
    for(cJSON* x=o->child;x;x=x->next)if(x->string&&!std::strcmp(x->string,names[i]))++occurrences;
    if(occurrences!=1)return false;
  }
  return true;
}
inline bool numeric(cJSON* o,const char* key,double& result,double lo,double hi,bool integer=false) {
  cJSON* v=cJSON_GetObjectItemCaseSensitive(o,key);
  if(!cJSON_IsNumber(v)||!std::isfinite(v->valuedouble)||v->valuedouble<lo||v->valuedouble>hi||
      (integer&&std::floor(v->valuedouble)!=v->valuedouble))return false;
  result=v->valuedouble;return true;
}
inline bool identity(cJSON* o,const char* key,char* result,size_t length,bool hex=false) {
  cJSON* v=cJSON_GetObjectItemCaseSensitive(o,key);
  if(!cJSON_IsString(v)||!v->valuestring)return false;
  size_t n=std::strlen(v->valuestring);
  if(!n||n>=length||(hex&&n!=32))return false;
  for(size_t i=0;i<n;i++) {
    char c=v->valuestring[i];
    if(hex ? !((c>='a'&&c<='f')||(c>='0'&&c<='9')) :
      !((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'))return false;
  }
  std::memcpy(result,v->valuestring,n+1);return true;
}
inline bool operation(cJSON* o,Op& op) {
  cJSON* v=cJSON_GetObjectItemCaseSensitive(o,"operation");
  if(!cJSON_IsString(v))return false;
  const char* names[]={"arm","attitude","heartbeat","land","disarm","motor_test"};
  for(int i=0;i<6;i++)if(!std::strcmp(v->valuestring,names[i])) {op=static_cast<Op>(i);return true;}
  return false;
}
inline cJSON* hello(FlightCore& core,uint64_t now) {
  core.tick(now);auto* out=cJSON_CreateObject();
  number(out,"protocol",1);text(out,"device_id",core.device);text(out,"boot_id",core.boot);
  number(out,"clock_us",double(now));text(out,"state",core.state_name());text(out,"owner",core.owner);
  boolean(out,"flight_enabled",core.flight_enabled());boolean(out,"calibrated",core.calibrated);
  boolean(out,"commissioned",core.commissioned);boolean(out,"fault_latched",core.fault_latched);
  boolean(out,"bench_motor_tests",core.bench_enabled);
  boolean(out,"restrained_rig",core.rig_enabled);boolean(out,"physical_flight_qualified",false);
  number(out,"voltage_v",core.voltage);text(out,"reason",core.reason);
  auto* limits=cJSON_AddObjectToObject(out,"limits");number(limits,"tilt_rad",.26);
  number(limits,"yaw_rate_rad_s",1);number(limits,"thrust",.8);number(limits,"control_timeout_us",DEADLINE_US);
  auto* sp=cJSON_AddObjectToObject(out,"setpoint");number(sp,"roll_rad",core.setpoint.roll);
  number(sp,"pitch_rad",core.setpoint.pitch);number(sp,"yaw_rate_rad_s",core.setpoint.yaw_rate);number(sp,"thrust",core.setpoint.thrust);
  auto* telemetry=cJSON_AddObjectToObject(out,"controller");
  number(telemetry,"roll_rad",core.roll);number(telemetry,"pitch_rad",core.pitch);number(telemetry,"yaw_rad",core.yaw);
  number(telemetry,"imu_time_us",double(core.last_imu));number(telemetry,"imu_samples",double(core.samples));
  number(telemetry,"missed_ticks",double(core.missed_ticks));
  auto* motors=cJSON_AddArrayToObject(telemetry,"motor_duty");
  for(double duty:core.motors)cJSON_AddItemToArray(motors,cJSON_CreateNumber(duty));
  return out;
}
inline cJSON* error(const char* message,int code,int& status) {
  status=code;auto* result=cJSON_CreateObject();text(result,"error",message);return result;
}
inline cJSON* parse_bounded(const char* body) {
  if(!body||std::strlen(body)>1536||std::strstr(body,"\\u0000"))return nullptr;
  int depth=0;bool quoted=false,escape=false;
  for(const char* p=body;*p;p++) {
    if(escape) {escape=false;continue;}
    if(quoted&&*p=='\\') {escape=true;continue;}
    if(*p=='"') {quoted=!quoted;continue;}
    if(!quoted&&(*p=='{'||*p=='[')&&++depth>5)return nullptr;
    if(!quoted&&(*p=='}'||*p==']'))--depth;
  }
  return cJSON_ParseWithOpts(body,nullptr,true);
}

// The same parser and state machine run on the ESP32 and in the desktop harness.
// Authentication and transport are enforced by the server, before this call.
inline cJSON* handle(FlightCore& core,const char* path,const char* raw,uint64_t now,
                    const char* new_session,int& status) {
  status=200;
  if(!std::strcmp(path,"/v1/hello"))return hello(core,now);
  cJSON* body=parse_bounded(raw);
  if(!body)return error("Invalid JSON body",400,status);
  struct Guard {cJSON* o;~Guard(){cJSON_Delete(o);}} guard{body};
  Reply result{};Command command{};double value=0;
  if(!std::strcmp(path,"/v1/session")) {
    const char* keys[]={"client_id"};char client[65]{};
    if(!fields(body,keys,1)||!identity(body,"client_id",client,sizeof(client)))return error("Invalid session request",400,status);
    result=core.claim(client,new_session,now);
    if(result.error)return error(result.error,result.status,status);
    auto* out=cJSON_CreateObject();text(out,"boot_id",core.boot);text(out,"session_id",core.session);
    number(out,"clock_us",double(now));number(out,"lease_until_us",double(now+LEASE_US));return out;
  }
  if(!operation(body,command.operation))return error("Unsupported operation",400,status);
  if(!identity(body,"boot_id",command.boot,sizeof(command.boot),true)||
      !numeric(body,"deadline_us",value,0,9007199254740991.,true))return error("Invalid identity or deadline",400,status);
  command.deadline=static_cast<uint64_t>(value);
  if(!std::strcmp(path,"/v1/emergency")) {
    const char* keys[]={"boot_id","deadline_us","operation"};
    if(!fields(body,keys,3))return error("Invalid emergency envelope",400,status);
    result=core.emergency(command.boot,command.operation,command.deadline,now);
  } else if(!std::strcmp(path,"/v1/command")) {
    const char* keys[]={"boot_id","deadline_us","operation","session_id","sequence","setpoint"};
    const char* bench_keys[]={"boot_id","deadline_us","operation","session_id","sequence","motor","duty","duration_ms"};
    bool envelope=command.operation==Op::MotorTest?fields(body,bench_keys,8):fields(body,keys,command.operation==Op::Attitude?6:5);
    if(!envelope||
       !identity(body,"session_id",command.session,sizeof(command.session),true)||
       !numeric(body,"sequence",value,0,4294967295.,true))return error("Invalid command envelope",400,status);
    command.sequence=static_cast<uint32_t>(value);
    if(command.operation==Op::MotorTest){
      if(!numeric(body,"motor",value,0,3,true))return error("Invalid bench motor",400,status);
      command.motor=unsigned(value);
      if(!numeric(body,"duration_ms",value,20,200,true)||!numeric(body,"duty",command.duty,.01,.2))return error("Invalid bench pulse",400,status);
      command.duration_ms=unsigned(value);
    }
    if(command.operation==Op::Attitude) {
      cJSON* sp=cJSON_GetObjectItemCaseSensitive(body,"setpoint");
      const char* names[]={"roll_rad","pitch_rad","yaw_rate_rad_s","thrust"};
      if(!fields(sp,names,4)||!numeric(sp,names[0],command.setpoint.roll,-.26,.26)||
         !numeric(sp,names[1],command.setpoint.pitch,-.26,.26)||
         !numeric(sp,names[2],command.setpoint.yaw_rate,-1,1)||
         !numeric(sp,names[3],command.setpoint.thrust,0,.8))return error("Invalid attitude setpoint",400,status);
    }
    result=core.command(command,now);
  } else return error("Unknown endpoint",404,status);
  if(result.error)return error(result.error,result.status,status);
  auto* out=cJSON_CreateObject();boolean(out,"accepted",true);text(out,"state",core.state_name());
  number(out,"clock_us",double(result.duplicate?result.clock:now));
  if(!std::strcmp(path,"/v1/command"))number(out,"sequence",command.sequence);
  if(result.duplicate)boolean(out,"duplicate",true);
  return out;
}
}
