// Optional process bridge to GPL-3.0-or-later OpenVINS. See config/openvins-runtime.json.
// Inputs are sensor measurements only. Never call initialize_with_gt or feed_measurement_simulation.
#include <cstdio>
#include <cmath>
#include <iostream>
#include <memory>
#include <string>
#include <unistd.h>
#include <nlohmann/json.hpp>
#include <opencv2/imgcodecs.hpp>
#include "core/VioManager.h"
#include "state/StateHelper.h"
#include "state/State.h"
#include "utils/print.h"
#include "utils/sensor_data.h"
#include "utils/opencv_yaml_parse.h"
#include "track/TrackBase.h"
#include "feat/FeatureDatabase.h"
#include "feat/Feature.h"

using json = nlohmann::json;

class SensorVio : public ov_msckf::VioManager {
public:
  using ov_msckf::VioManager::VioManager;
  bool ground_phase_finished = false;
  void stationary_phase(bool grounded) {
    if (grounded && ground_phase_finished)
      throw std::runtime_error("Cannot re-enable ground initialization after liftoff");
    // Upstream permanently disables beginning-only ZUPT after enough clone
    // states, even when no motion was commanded and an early disparity check
    // merely lacked shared tracks. Keep detecting stationarity while unarmed.
    // Actual corrections still require the upstream sensor consistency tests.
    has_moved_since_zupt = !grounded;
    if (!grounded) { ground_phase_finished = true; did_zupt_update = false; }
  }
  bool stationary_update_applied() const { return did_zupt_update; }
  size_t stable_tracks() {
    size_t count=0;
    for(const auto &camera:trackFEATS->get_last_ids()) for(size_t id:camera.second) {
      auto feature=trackFEATS->get_feature_database()->get_feature(id);
      if(!feature) continue;
      auto times=feature->timestamps.find(camera.first);
      if(times!=feature->timestamps.end() && times->second.size()>=3 && times->second.back()-times->second.front()>=.2) count++;
    }
    return count;
  }
};

int main(int argc, char **argv) {
  FILE *protocol = fdopen(dup(STDOUT_FILENO), "w");
  dup2(STDERR_FILENO, STDOUT_FILENO); // Upstream diagnostics cannot corrupt JSON replies.
  auto reply = [&](const json &message) { auto line = message.dump(); fprintf(protocol, "%s\n", line.c_str()); fflush(protocol); };
  try {
    if (argc != 2) throw std::runtime_error("Expected camera/IMU configuration path");
    auto parser = std::make_shared<ov_core::YamlParser>(argv[1]);
    ov_core::Printer::setPrintLevel("SILENT");
    ov_msckf::VioManagerOptions options;
    options.print_and_load(parser);
    options.num_opencv_threads = 1;
    options.use_multi_threading_pubs = false;
    options.use_multi_threading_subs = false;
    if (!parser->successful()) throw std::runtime_error("Incomplete OpenVINS configuration");
    auto vio = std::make_shared<SensorVio>(options);
    reply({{"ready", true}, {"source", "RGB and IMU only"}});
    double last_imu = -1, last_camera = -1;
    std::string line;
    while (std::getline(std::cin, line)) {
      try {
        auto input = json::parse(line);
        if (input.value("op", "") == "close") { reply({{"closed", true}}); break; }
        if (input.contains("stationary_phase")) vio->stationary_phase(input.at("stationary_phase").get<bool>());
        for (const auto &sample : input.at("imu")) {
          ov_core::ImuData imu;
          imu.timestamp = sample.at("time_s").get<double>();
          if (!std::isfinite(imu.timestamp) || imu.timestamp <= last_imu) continue;
          for (int i=0; i<3; i++) {
            imu.wm(i) = sample.at("gyro_flu").at(i).get<double>();
            imu.am(i) = sample.at("specific_force_flu").at(i).get<double>();
          }
          if (!imu.wm.allFinite() || !imu.am.allFinite()) throw std::runtime_error("Non-finite IMU sample");
          vio->feed_measurement_imu(imu);
          last_imu=imu.timestamp;
        }
        if (input.contains("camera")) {
          const auto &camera=input.at("camera");
          ov_core::CameraData data;
          data.timestamp=camera.at("time_s").get<double>();
          if (!std::isfinite(data.timestamp) || data.timestamp <= last_camera || data.timestamp > last_imu)
            throw std::runtime_error("Camera timestamp lacks fresh bracketing IMU data");
          cv::Mat frame=cv::imread(camera.at("path").get<std::string>(), cv::IMREAD_GRAYSCALE);
          if (frame.empty()) throw std::runtime_error("Camera image could not be decoded");
          data.sensor_ids.push_back(0); data.images.push_back(frame);
          data.masks.push_back(cv::Mat::zeros(frame.rows,frame.cols,CV_8UC1));
          vio->feed_measurement_camera(data);
          last_camera=data.timestamp;
        }
        json output={{"initialized",vio->initialized()},{"last_imu_time_s",last_imu}};
        output["stable_image_tracks"]=vio->stable_tracks();
        output["stationary_update_applied"]=vio->stationary_update_applied();
        if (vio->initialized()) {
          auto state=vio->get_state();
          auto p=state->_imu->pos(); auto v=state->_imu->vel(); auto q=state->_imu->quat();
          output["time_s"]=state->_timestamp;
          output["position"]={p(0),p(1),p(2)}; output["velocity"]={v(0),v(1),v(2)};
          output["q_global_to_imu_jpl"]={q(0),q(1),q(2),q(3)};
          Eigen::Matrix3d rotation=state->_imu->Rot().transpose();
          output["rotation_imu_to_global"]=json::array();
          for(int row=0;row<3;row++) output["rotation_imu_to_global"].push_back({rotation(row,0),rotation(row,1),rotation(row,2)});
          auto covariance=ov_msckf::StateHelper::get_marginal_covariance(state,{state->_imu});
          output["position_std_m"]={std::sqrt(std::max(0.,covariance(3,3))),std::sqrt(std::max(0.,covariance(4,4))),std::sqrt(std::max(0.,covariance(5,5)))};
          // Preserve cross-covariances: launch-relative drift is not the
          // uncertainty of a recent displacement through the observed map.
          auto reference=state->_clones_IMU.lower_bound(state->_timestamp-1.);
          if(reference!=state->_clones_IMU.end() && state->_timestamp-reference->first>=.25) {
            auto joint=ov_msckf::StateHelper::get_marginal_covariance(state,{state->_imu->p(),reference->second->p()});
            output["relative_position_span_s"]=state->_timestamp-reference->first;
            output["relative_position_joint_covariance"]=json::array();
            for(int row=0;row<6;row++) {
              json values=json::array();
              for(int column=0;column<6;column++) values.push_back(joint(row,column));
              output["relative_position_joint_covariance"].push_back(values);
            }
          }
          double timestamp; std::unordered_map<size_t,Eigen::Vector3d> world,uvd;
          vio->get_active_tracks(timestamp,world,uvd);
          output["landmark_time_s"]=timestamp;
          output["landmarks"]=json::array();
          for (const auto &item:world) {
            auto pixel=uvd.find(item.first);
            if (!item.second.allFinite() || pixel==uvd.end() || !pixel->second.allFinite()) continue;
            output["landmarks"].push_back({{"id",item.first},{"point",{item.second(0),item.second(1),item.second(2)}},{"uvd",{pixel->second(0),pixel->second(1),pixel->second(2)}}});
          }
        }
        reply(output);
      } catch (const std::exception &error) { reply({{"error",error.what()}}); }
    }
  } catch (const std::exception &error) { reply({{"error",error.what()}}); return 1; }
  fclose(protocol);
}
