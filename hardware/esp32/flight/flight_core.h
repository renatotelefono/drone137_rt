#pragma once
// Shared onboard/desktop controller. Units: seconds, radians, SI; body FLU.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace d137 {
constexpr double G = 9.80665;
constexpr uint64_t DEADLINE_US = 250000, LEASE_US = 2000000;
struct Vec { double x=0, y=0, z=0; };
inline bool finite(Vec a) { return std::isfinite(a.x)&&std::isfinite(a.y)&&std::isfinite(a.z); }
inline double norm(Vec a) { return std::sqrt(a.x*a.x+a.y*a.y+a.z*a.z); }
inline double clamp(double x,double lo,double hi) { return std::max(lo,std::min(hi,x)); }
struct Setpoint { double roll=0,pitch=0,yaw_rate=0,thrust=0; };
enum class Op { Arm, Attitude, Heartbeat, Land, Disarm, MotorTest };
enum class State { Disarmed, Armed, Landing };
struct Command {
  char boot[33]{}, session[33]{};
  uint32_t sequence=0;
  uint64_t deadline=0;
  Op operation=Op::Heartbeat;
  Setpoint setpoint{};
  unsigned motor=0,duration_ms=0;
  double duty=0;
};
struct Reply { int status=200; const char* error=nullptr; bool duplicate=false; uint64_t clock=0; };
inline bool same(const Command& a,const Command& b) {
  return !std::strcmp(a.boot,b.boot)&&!std::strcmp(a.session,b.session)&&a.sequence==b.sequence&&
    a.deadline==b.deadline&&a.operation==b.operation&&a.setpoint.roll==b.setpoint.roll&&
    a.setpoint.pitch==b.setpoint.pitch&&a.setpoint.yaw_rate==b.setpoint.yaw_rate&&a.setpoint.thrust==b.setpoint.thrust&&
    a.motor==b.motor&&a.duration_ms==b.duration_ms&&a.duty==b.duty;
}

class FlightCore {
 public:
  char boot[33]{}, device[65]{}, owner[65]{}, session[33]{};
  State state=State::Disarmed;
  const char* reason=nullptr;
  bool outputs_enabled=false, commissioned=false, calibrated=false, fault_latched=false;
  bool bench_enabled=false, rig_enabled=false;
  double voltage=0, roll=0, pitch=0, yaw=0;
  Vec bias{}, gyro{}, acceleration{};
  Setpoint setpoint{};
  std::array<double,4> motors{};
  uint64_t last_imu=0, samples=0, missed_ticks=0;
  // Gain defaults are provisional: bench verification/tuning required.
  double calibration_seconds=9., angle_kp=4., rate_kp=.045, rate_ki=.06, rate_kd=.0005;

  const char* state_name() const {
    return state==State::Armed?"armed":state==State::Landing?"landing":"disarmed";
  }
  bool flight_enabled() const { return outputs_enabled&&(commissioned||rig_enabled)&&!fault_latched; }
  void reset(const char* identity,const char* boot_id) {
    *this=FlightCore{};
    std::strncpy(device,identity,64); std::strncpy(boot,boot_id,32);
  }
  void revoke() { owner[0]=session[0]=0; lease_until=0; }
  void disarm(const char* why) {
    state=State::Disarmed;reason=why;setpoint={};motors.fill(0);integral={};bench_until=0;revoke();
  }
  void fault(const char* why) { fault_latched=true;disarm(why); }
  void land(uint64_t now,const char* why) {
    if(bench_until){disarm(why);return;}
    if(state==State::Armed) {state=State::Landing;landing_start=now;landing_thrust=setpoint.thrust;reason=why;}
    revoke();
  }
  Reply claim(const char* client,const char* token,uint64_t now) {
    tick(now);
    if(state!=State::Disarmed)return {409,"Disarm before acquiring control"};
    if(owner[0])return {423,"Control session already owned"};
    std::strncpy(owner,client,64);std::strncpy(session,token,32);
    lease_until=now+LEASE_US;has_last=false;return {};
  }
  Reply command(const Command& c,uint64_t now) {
    tick(now);
    if(std::strcmp(c.boot,boot))return {409,"Boot identity mismatch"};
    if(has_last&&c.sequence==last.sequence) {
      if(!same(c,last))return {409,"Sequence reused with different content"};
      return {200,nullptr,true,last_ack_time};
    }
    if(has_last&&c.sequence<last.sequence)return {409,"Out-of-order command"};
    if(!session[0]||std::strcmp(c.session,session))return {409,"Control session mismatch"};
    if(c.deadline<=now||c.deadline-now>DEADLINE_US)return {409,"Expired or excessive deadline"};
    switch(c.operation) {
      case Op::Arm:
        if(state!=State::Disarmed||bench_until||!flight_enabled()||!calibrated||!last_imu||now<last_imu||
           now-last_imu>20000||voltage<3.8||voltage>4.20||std::abs(roll)>.17||std::abs(pitch)>.17)
          return {409,"Aircraft does not meet arming checks"};
        state=State::Armed;armed_at=now;reason=nullptr;setpoint={};integral={};control_until=c.deadline;break;
      case Op::Attitude:
        if(state!=State::Armed)return {409,"Aircraft is not armed"};
        if(!valid(c.setpoint))return {400,"Invalid attitude setpoint"};
        if(rig_enabled&&c.setpoint.thrust>.65)return {400,"Restrained rig thrust limit"};
        setpoint=c.setpoint;control_until=c.deadline;break;
      case Op::Heartbeat:break; // Ownership only: cannot prolong motor commands.
      case Op::Land:land(now,"Operator landing ramp");break;
      case Op::Disarm:disarm("Operator disarmed");break;
      case Op::MotorTest:
        if(!bench_enabled||fault_latched||state!=State::Disarmed||bench_until||!calibrated||
           now<last_imu||now-last_imu>20000||voltage<3.8||voltage>4.20)
          return {409,"Propeller-free bench test is unavailable"};
        if(c.motor>3||!std::isfinite(c.duty)||c.duty<=0||c.duty>.2||c.duration_ms<20||c.duration_ms>200)
          return {400,"Invalid bench pulse"};
        bench_until=std::min(c.deadline,now+c.duration_ms*1000);bench_motor=c.motor;bench_duty=c.duty;
        reason="Propeller-free bench pulse";break;
    }
    if(owner[0])lease_until=now+LEASE_US;
    last=c;has_last=true;last_ack_time=now;return {200,nullptr,false,now};
  }
  Reply emergency(const char* expected_boot,Op op,uint64_t deadline,uint64_t now) {
    tick(now);
    if(std::strcmp(boot,expected_boot))return {409,"Boot identity mismatch"};
    if(deadline<=now||deadline-now>DEADLINE_US)return {409,"Expired emergency request"};
    if(op==Op::Disarm)disarm("Emergency disarm");
    else if(op==Op::Land)land(now,"Emergency landing ramp");
    else return {400,"Invalid emergency action"};
    return {};
  }
  static bool valid(Setpoint s) {
    return std::isfinite(s.roll)&&std::abs(s.roll)<=.26&&std::isfinite(s.pitch)&&std::abs(s.pitch)<=.26&&
      std::isfinite(s.yaw_rate)&&std::abs(s.yaw_rate)<=1&&std::isfinite(s.thrust)&&s.thrust>=0&&s.thrust<=.8;
  }
  void tick(uint64_t now) {
    if(bench_until){
      if(now<last_imu||now-last_imu>20000){fault("Bench IMU unavailable");return;}
      if(voltage<2.8||voltage>4.25){fault("Invalid bench supply voltage");return;}
      if(now>=bench_until||voltage<3.2||!bench_enabled||fault_latched){bench_until=0;motors.fill(0);}
    }
    if(rig_enabled&&state!=State::Disarmed&&now-armed_at>=5000000){disarm("Restrained rig five-second limit");return;}
    if(state!=State::Disarmed) {
      if(!last_imu||now<last_imu||now-last_imu>20000) {fault("IMU unavailable");return;}
      if(!std::isfinite(voltage)||voltage<2.8||voltage>4.25) {fault("Invalid supply voltage");return;}
      if(std::abs(roll)>.70||std::abs(pitch)>.70) {fault("Attitude limit exceeded");return;}
      if(state==State::Armed&&now>=control_until)land(now,"Setpoint expired");
      if(voltage<3.2)land(now,"Critical battery");
    }
    if(owner[0]&&now>=lease_until)land(now,"Control lease expired");
    if(state==State::Landing) {
      // A bounded throttle ramp, not altitude-aware landing.
      double fraction=clamp(1.-double(now-landing_start)/1500000.,0,1);
      setpoint={0,0,0,landing_thrust*fraction};
      if(fraction<=0)disarm("Landing ramp complete");
    }
    if(state==State::Disarmed||!flight_enabled())motors.fill(0);
    if(bench_until)motors[bench_motor]=bench_duty;
  }

  void imu(uint64_t now,Vec measured_gyro,Vec measured_acc,double measured_voltage) {
    if(!finite(measured_gyro)||!finite(measured_acc)||norm(measured_gyro)>35||norm(measured_acc)>160||
       !std::isfinite(measured_voltage)||measured_voltage<0||measured_voltage>5||
       (last_imu&&now<=last_imu)) {fault("Invalid IMU or battery sample");return;}
    double dt=last_imu?double(now-last_imu)/1e6:.002;
    if(dt>.020) {
      ++missed_ticks;
      if(state!=State::Disarmed||bench_until) {fault("Control loop overrun");return;}
      calibration_start=0;calibration_count=0;bias_sum={};acc_sum={};
      dt=.002;
    }
    last_imu=now;voltage=measured_voltage;acceleration=measured_acc;++samples;
    if(!calibrated) {
      bool still=norm(measured_gyro)<.10&&std::abs(norm(measured_acc)-G)<.45;
      if(!still) {calibration_start=0;calibration_count=0;bias_sum={};acc_sum={};return;}
      if(!calibration_start)calibration_start=now;
      bias_sum.x+=measured_gyro.x;bias_sum.y+=measured_gyro.y;bias_sum.z+=measured_gyro.z;
      acc_sum.x+=measured_acc.x;acc_sum.y+=measured_acc.y;acc_sum.z+=measured_acc.z;
      ++calibration_count;
      if(double(now-calibration_start)/1e6<calibration_seconds||calibration_count<100)return;
      bias={bias_sum.x/calibration_count,bias_sum.y/calibration_count,bias_sum.z/calibration_count};
      double r=std::atan2(acc_sum.y,acc_sum.z),p=std::atan2(-acc_sum.x,std::hypot(acc_sum.y,acc_sum.z));
      q={std::cos(r/2)*std::cos(p/2),std::sin(r/2)*std::cos(p/2),std::cos(r/2)*std::sin(p/2),-std::sin(r/2)*std::sin(p/2)};
      calibrated=true;
    }
    gyro={measured_gyro.x-bias.x,measured_gyro.y-bias.y,measured_gyro.z-bias.z};
    Vec corrected=gyro;double a=norm(measured_acc);
    if(std::abs(a-G)<1.5&&a>1) {
      Vec expected={2*(q[1]*q[3]-q[0]*q[2]),2*(q[0]*q[1]+q[2]*q[3]),1-2*(q[1]*q[1]+q[2]*q[2])};
      Vec v={measured_acc.x/a,measured_acc.y/a,measured_acc.z/a};
      corrected.x+=1.5*(v.y*expected.z-v.z*expected.y);
      corrected.y+=1.5*(v.z*expected.x-v.x*expected.z);
      corrected.z+=1.5*(v.x*expected.y-v.y*expected.x);
    }
    auto old=q;double h=.5*dt;
    q[0]+=h*(-old[1]*corrected.x-old[2]*corrected.y-old[3]*corrected.z);
    q[1]+=h*( old[0]*corrected.x+old[2]*corrected.z-old[3]*corrected.y);
    q[2]+=h*( old[0]*corrected.y-old[1]*corrected.z+old[3]*corrected.x);
    q[3]+=h*( old[0]*corrected.z+old[1]*corrected.y-old[2]*corrected.x);
    double n=std::sqrt(q[0]*q[0]+q[1]*q[1]+q[2]*q[2]+q[3]*q[3]);
    if(!std::isfinite(n)||n<.5) {fault("Attitude estimator invalid");return;}
    for(auto& value:q)value/=n;
    roll=std::atan2(2*(q[0]*q[1]+q[2]*q[3]),1-2*(q[1]*q[1]+q[2]*q[2]));
    pitch=std::asin(clamp(2*(q[0]*q[2]-q[3]*q[1]),-1,1));
    yaw=std::atan2(2*(q[0]*q[3]+q[1]*q[2]),1-2*(q[2]*q[2]+q[3]*q[3]));
    tick(now);
    if(bench_until)return;
    if(state==State::Disarmed||!flight_enabled()||setpoint.thrust<.05) {motors.fill(0);integral={};previous=gyro;return;}
    Vec error={angle_kp*(setpoint.roll-roll)-gyro.x,angle_kp*(setpoint.pitch-pitch)-gyro.y,setpoint.yaw_rate-gyro.z};
    double blend=dt/(.012+dt);
    derivative.x+=blend*((gyro.x-previous.x)/dt-derivative.x);
    derivative.y+=blend*((gyro.y-previous.y)/dt-derivative.y);
    derivative.z+=blend*((gyro.z-previous.z)/dt-derivative.z);previous=gyro;
    Vec next={clamp(integral.x+rate_ki*error.x*dt,-.08,.08),clamp(integral.y+rate_ki*error.y*dt,-.08,.08),clamp(integral.z+rate_ki*error.z*dt,-.08,.08)};
    double r=clamp(rate_kp*error.x+next.x-rate_kd*derivative.x,-.2,.2);
    double p=clamp(rate_kp*error.y+next.y-rate_kd*derivative.y,-.2,.2);
    double y=clamp(rate_kp*error.z+next.z-rate_kd*derivative.z,-.12,.12);
    // X quad: front-right CW, rear-right CCW, rear-left CW, front-left CCW.
    std::array<double,4> correction={-r-p+y,-r+p-y,r+p+y,r-p-y};
    double scale=1;
    for(double v:correction)if(v>0)scale=std::min(scale,(.9-setpoint.thrust)/v);else if(v<0)scale=std::min(scale,setpoint.thrust/-v);
    if(scale>=.999)integral=next; // Anti-windup when an actuator saturates.
    for(unsigned i=0;i<4;++i)motors[i]=clamp(setpoint.thrust+scale*correction[i],0,.9);
  }

 private:
  uint64_t lease_until=0,control_until=0,landing_start=0,calibration_start=0,calibration_count=0,last_ack_time=0;
  uint64_t bench_until=0,armed_at=0;
  unsigned bench_motor=0;
  double bench_duty=0;
  double landing_thrust=0;
  bool has_last=false;
  Command last{};
  Vec bias_sum{},acc_sum{},integral{},previous{},derivative{};
  std::array<double,4> q={1,0,0,0};
};
} // namespace d137
