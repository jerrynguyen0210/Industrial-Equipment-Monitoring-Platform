#include "gateway/mqtt/client.hpp"

#include "gateway/log.hpp"

#include <mosquitto.h>

#include <atomic>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>

namespace gateway::mqtt {

struct Client::Impl {
  explicit Impl(const Config &config, OnMessage handler)
      : host(config.mqtt_host), port(config.mqtt_port), username(config.mqtt_username),
        on_message(std::move(handler)) {
    std::ifstream source(config.mqtt_password_file, std::ios::binary);
    if (!source) {
      throw std::runtime_error("cannot read MQTT_PASSWORD_FILE");
    }
    char buffer[4097];
    source.read(buffer, sizeof(buffer));
    const auto count = source.gcount();
    if (count > 4096) {
      throw std::runtime_error("MQTT_PASSWORD_FILE exceeds 4096 bytes");
    }
    if (source.bad()) {
      throw std::runtime_error("cannot read MQTT_PASSWORD_FILE");
    }
    password.assign(buffer, static_cast<std::size_t>(count));
    while (!password.empty() && (password.back() == '\n' || password.back() == '\r')) {
      password.pop_back();
    }
    if (password.empty() || password.find('\0') != std::string::npos) {
      throw std::runtime_error("MQTT_PASSWORD_FILE is empty or invalid");
    }
  }

  ~Impl() {
    if (running) {
      mosquitto_disconnect(mosq);
      mosquitto_loop_stop(mosq, false);
    }
    if (mosq) {
      mosquitto_destroy(mosq);
    }
    if (library_ready) {
      mosquitto_lib_cleanup();
    }
  }

  static void on_connect_callback(mosquitto *mosq, void *context, int code) {
    auto &self = *static_cast<Impl *>(context);
    if (code != 0) {
      log(Level::error, "mqtt", "connect_rejected", "broker rejected MQTT connection");
      return;
    }
    const int result = mosquitto_subscribe(mosq, nullptr, "equipment/+/telemetry", 1);
    if (result != MOSQ_ERR_SUCCESS) {
      log(Level::error, "mqtt", "subscribe_failed", mosquitto_strerror(result));
      self.fatal.store(true);
    }
  }

  static void on_subscribe_callback(mosquitto *, void *context, int, int count,
                                    const int *granted) {
    if (count == 1 && granted && granted[0] == 1) {
      log(Level::info, "mqtt", "subscribed", "equipment/+/telemetry QoS 1");
    } else {
      log(Level::error, "mqtt", "subscribe_rejected", "broker denied telemetry subscription");
      static_cast<Impl *>(context)->fatal.store(true);
    }
  }

  static void on_disconnect_callback(mosquitto *, void *, int code) {
    if (code != 0) {
      log(Level::warning, "mqtt", "disconnected", "MQTT connection lost; reconnecting");
    }
  }

  static void on_message_callback(mosquitto *mosq, void *context,
                                  const mosquitto_message *message) {
    auto &self = *static_cast<Impl *>(context);
    if (!message || !message->topic || message->payloadlen < 0 || message->qos != 1) {
      log(Level::warning, "intake", "message_rejected", "invalid_mqtt_message");
      return;
    }
    try {
      const auto size = static_cast<std::size_t>(message->payloadlen);
      const std::string_view payload(size == 0 ? "" : static_cast<const char *>(message->payload),
                                     size);
      self.on_message(message->topic, payload, message->retain);
    } catch (const std::exception &error) {
      log(Level::error, "intake", "storage_error", error.what());
      self.fatal.store(true);
      mosquitto_disconnect(mosq);
    }
  }

  void start() {
    if (mosquitto_lib_init() != MOSQ_ERR_SUCCESS) {
      throw std::runtime_error("mosquitto library initialization failed");
    }
    library_ready = true;
    mosq = mosquitto_new(username.c_str(), true, this);
    if (!mosq) {
      throw std::runtime_error("cannot create MQTT client");
    }
    mosquitto_connect_callback_set(mosq, on_connect_callback);
    mosquitto_subscribe_callback_set(mosq, on_subscribe_callback);
    mosquitto_disconnect_callback_set(mosq, on_disconnect_callback);
    mosquitto_message_callback_set(mosq, on_message_callback);
    int result = mosquitto_username_pw_set(mosq, username.c_str(), password.c_str());
    if (result != MOSQ_ERR_SUCCESS) {
      throw std::runtime_error("cannot configure MQTT credentials");
    }
    result = mosquitto_reconnect_delay_set(mosq, 1, 30, true);
    if (result != MOSQ_ERR_SUCCESS) {
      throw std::runtime_error("cannot configure MQTT reconnect delay");
    }
    result = mosquitto_connect_async(mosq, host.c_str(), port, 60);
    if (result != MOSQ_ERR_SUCCESS) {
      throw std::runtime_error("cannot start MQTT connection: " +
                               std::string(mosquitto_strerror(result)));
    }
    result = mosquitto_loop_start(mosq);
    if (result != MOSQ_ERR_SUCCESS) {
      throw std::runtime_error("cannot start MQTT network loop: " +
                               std::string(mosquitto_strerror(result)));
    }
    running = true;
  }

  void stop() {
    if (!running) {
      return;
    }
    mosquitto_disconnect(mosq);
    const int result = mosquitto_loop_stop(mosq, false);
    running = false;
    // The loop may already have exited after a broker connection rejection.
    if (result != MOSQ_ERR_SUCCESS && result != MOSQ_ERR_INVAL) {
      throw std::runtime_error("cannot stop MQTT network loop: " +
                               std::string(mosquitto_strerror(result)));
    }
  }

  std::string host;
  int port;
  std::string username;
  std::string password;
  OnMessage on_message;
  mosquitto *mosq = nullptr;
  bool library_ready = false;
  bool running = false;
  std::atomic<bool> fatal{false};
};

Client::Client(const Config &config, OnMessage on_message)
    : impl_(std::make_unique<Impl>(config, std::move(on_message))) {}

Client::~Client() = default;

void Client::start() { impl_->start(); }
void Client::stop() { impl_->stop(); }
bool Client::failed() const { return impl_->fatal.load(); }

} // namespace gateway::mqtt
