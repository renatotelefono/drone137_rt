// Apache-2.0. Bounded RGB image -> JPEG bridge. Native build pending Mac validation.
#include <gz/transport/Node.hh>
#include <gz/msgs/image.pb.h>
#include <jpeglib.h>
#include <arpa/inet.h>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <thread>

std::mutex mutex;
std::optional<gz::msgs::Image> latest;

void receive(const gz::msgs::Image &image) {
  // Only accept the selected bounded RGB8 sensor configuration.
  if (image.width() != 320 || image.height() != 240 ||
      image.pixel_format_type() != gz::msgs::PixelFormatType::RGB_INT8 ||
      image.step() < image.width()*3 || image.data().size() < image.step()*image.height() ||
      image.data().size() > 320*240*4) return;
  std::lock_guard<std::mutex> lock(mutex);
  latest = image; // overwrite one slot; never queue stale images
}

int main(int argc, char **argv) {
  if (argc != 2) { std::cerr << "Usage: drone137-image-bridge <image-topic>\n"; return 2; }
  gz::transport::Node node;
  if (!node.Subscribe(argv[1], receive)) return 3;
  while (std::cout.good()) {
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    std::optional<gz::msgs::Image> frame;
    { std::lock_guard<std::mutex> lock(mutex); frame.swap(latest); }
    if (!frame) continue;
    jpeg_compress_struct encoder{};
    jpeg_error_mgr error{};
    encoder.err = jpeg_std_error(&error);
    jpeg_create_compress(&encoder);
    unsigned char *output = nullptr;
    unsigned long size = 0;
    jpeg_mem_dest(&encoder, &output, &size);
    encoder.image_width = frame->width();
    encoder.image_height = frame->height();
    encoder.input_components = 3;
    encoder.in_color_space = JCS_RGB;
    jpeg_set_defaults(&encoder);
    jpeg_set_quality(&encoder, 85, TRUE);
    jpeg_start_compress(&encoder, TRUE);
    while (encoder.next_scanline < encoder.image_height) {
      auto *row = reinterpret_cast<JSAMPLE *>(
          const_cast<char *>(frame->data().data()) + encoder.next_scanline * frame->step());
      jpeg_write_scanlines(&encoder, &row, 1);
    }
    jpeg_finish_compress(&encoder);
    double stamp = frame->header().stamp().sec() + frame->header().stamp().nsec()*1e-9;
    std::ostringstream metadata;
    metadata.precision(17);
    metadata << "{\"width\":320,\"height\":240,\"sensor_time_s\":" << stamp
             << ",\"bytes\":" << size << "}";
    std::string header = metadata.str();
    uint32_t length = htonl(static_cast<uint32_t>(header.size()));
    std::cout.write(reinterpret_cast<char *>(&length), 4);
    std::cout.write(header.data(), header.size());
    std::cout.write(reinterpret_cast<char *>(output), size);
    std::cout.flush();
    jpeg_destroy_compress(&encoder);
    std::free(output);
  }
}
