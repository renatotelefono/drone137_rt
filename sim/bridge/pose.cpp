// Apache-2.0. Read-only simulator truth for rendering and evaluation, never control.
#include <gz/transport/Node.hh>
#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/double.pb.h>
#include <gz/msgs/model.pb.h>
#include <array>
#include <cmath>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <optional>
#include <thread>
std::mutex mutex;
std::optional<gz::msgs::Pose> latest;
double stamp = 0;
std::string vehicle;
std::optional<gz::msgs::Pose> cart;
std::array<double,4> rotors{};
std::array<bool,4> rotorSeen{};
double rotorStamp = 0;
void receiveJoints(const gz::msgs::Model &model) {
  std::lock_guard<std::mutex> lock(mutex);
  rotorStamp = model.header().stamp().sec()+model.header().stamp().nsec()*1e-9;
  for (const auto &j : model.joint()) for (int i=0;i<4;++i)
    if (j.name()=="rotor_"+std::to_string(i)+"_joint" && j.has_axis1()) {
      rotors[i]=j.axis1().velocity(); rotorSeen[i]=true;
    }
}
void receiveCart(const gz::msgs::Pose_V &poses) {
  for (const auto &p : poses.pose()) if (p.name() == "moving_cart") {
    std::lock_guard<std::mutex> lock(mutex); cart = p; break;
  }
}
void receive(const gz::msgs::Pose_V &poses) {
  for (const auto &p : poses.pose()) if (p.name() == vehicle) {
    std::lock_guard<std::mutex> lock(mutex);
    latest = p;
    stamp = p.header().stamp().sec() + p.header().stamp().nsec()*1e-9;
    break;
  }
}
int main(int argc, char **argv) {
  if (argc != 3) return 2;
  vehicle = argv[2];
  gz::transport::Node node;
  if (!node.Subscribe(argv[1], receive)) return 3;
  node.Subscribe("/model/moving_cart/pose", receiveCart);
  node.Subscribe("/drone137/rotor-joints", receiveJoints);
  auto command = node.Advertise<gz::msgs::Double>("/drone137/cart");
  std::cout << std::setprecision(12);
  while (std::cout.good()) {
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    std::lock_guard<std::mutex> lock(mutex);
    if (!latest) continue;
    const auto &p = latest->position(); const auto &q = latest->orientation();
    std::cout << "{\"sim_time\":" << stamp << ",\"position\":[" << p.x() << ',' << p.y() << ',' << p.z()
      << "],\"quaternion\":[" << q.x() << ',' << q.y() << ',' << q.z() << ',' << q.w() << "]";
    if (cart) std::cout << ",\"cart_position\":[" << cart->position().x() << ',' << cart->position().y() << ',' << cart->position().z() << ']';
    if (rotorSeen[0] && rotorSeen[1] && rotorSeen[2] && rotorSeen[3])
      std::cout << ",\"rotor_joint_rad_s\":[" << rotors[0] << ',' << rotors[1] << ',' << rotors[2] << ',' << rotors[3]
        << "],\"rotor_stamp\":" << rotorStamp;
    std::cout << '}' << std::endl;
    gz::msgs::Double desired; desired.set_data(.5*std::sin(stamp*2*3.141592653589793/9)); command.Publish(desired);
    latest.reset();
  }
}
