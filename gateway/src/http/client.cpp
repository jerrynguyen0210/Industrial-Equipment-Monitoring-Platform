#include "gateway/http/client.hpp"

#include <curl/curl.h>

#include <memory>
#include <stdexcept>
#include <string>

namespace gateway::http {
namespace {

constexpr std::size_t max_request_bytes = 9 * 1024 * 1024;
constexpr std::size_t max_response_bytes = 1024 * 1024;

size_t receive(char *data, size_t size, size_t count, void *context) {
  auto &body = *static_cast<std::string *>(context);
  if (size != 0 && count > max_response_bytes / size) {
    return 0;
  }
  const auto bytes = size * count;
  if (bytes > max_response_bytes - body.size()) {
    return 0;
  }
  body.append(data, bytes);
  return bytes;
}

int progress(void *context, curl_off_t, curl_off_t, curl_off_t, curl_off_t) {
  return static_cast<std::atomic<bool> *>(context)->load() ? 1 : 0;
}

} // namespace

CurlClient::CurlClient(std::string api_base_url, std::string gateway_api_key)
    : url_(std::move(api_base_url) + "/v1/telemetry/batches"), token_(std::move(gateway_api_key)) {
  if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
    throw std::runtime_error("cannot initialize HTTP client");
  }
}

CurlClient::~CurlClient() { curl_global_cleanup(); }

Response CurlClient::post_batch(std::string_view body) {
  if (body.empty() || body.size() > max_request_bytes) {
    throw std::runtime_error("HTTP batch exceeds allowed size");
  }
  if (stopping_.load()) {
    throw std::runtime_error("HTTP client is stopping");
  }
  std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> handle(curl_easy_init(), curl_easy_cleanup);
  if (!handle) {
    throw std::runtime_error("cannot create HTTP request");
  }
  curl_slist *raw_headers = nullptr;
  raw_headers = curl_slist_append(raw_headers, "Content-Type: application/json");
  if (!raw_headers) {
    throw std::runtime_error("cannot allocate HTTP headers");
  }
  std::unique_ptr<curl_slist, decltype(&curl_slist_free_all)> headers(raw_headers,
                                                                      curl_slist_free_all);
  raw_headers = curl_slist_append(headers.get(), ("Authorization: Bearer " + token_).c_str());
  if (!raw_headers) {
    throw std::runtime_error("cannot allocate HTTP authorization header");
  }
  headers.release();
  headers.reset(raw_headers);

  std::string response_body;
  curl_easy_setopt(handle.get(), CURLOPT_URL, url_.c_str());
  curl_easy_setopt(handle.get(), CURLOPT_HTTPHEADER, headers.get());
  curl_easy_setopt(handle.get(), CURLOPT_POST, 1L);
  curl_easy_setopt(handle.get(), CURLOPT_POSTFIELDS, body.data());
  curl_easy_setopt(handle.get(), CURLOPT_POSTFIELDSIZE_LARGE, static_cast<curl_off_t>(body.size()));
  curl_easy_setopt(handle.get(), CURLOPT_CONNECTTIMEOUT_MS, 3000L);
  curl_easy_setopt(handle.get(), CURLOPT_TIMEOUT_MS, 10000L);
  curl_easy_setopt(handle.get(), CURLOPT_FOLLOWLOCATION, 0L);
  curl_easy_setopt(handle.get(), CURLOPT_PROTOCOLS_STR, "http,https");
  curl_easy_setopt(handle.get(), CURLOPT_NOSIGNAL, 1L);
  curl_easy_setopt(handle.get(), CURLOPT_SSL_VERIFYPEER, 1L);
  curl_easy_setopt(handle.get(), CURLOPT_SSL_VERIFYHOST, 2L);
  curl_easy_setopt(handle.get(), CURLOPT_WRITEFUNCTION, receive);
  curl_easy_setopt(handle.get(), CURLOPT_WRITEDATA, &response_body);
  curl_easy_setopt(handle.get(), CURLOPT_XFERINFOFUNCTION, progress);
  curl_easy_setopt(handle.get(), CURLOPT_XFERINFODATA, &stopping_);
  curl_easy_setopt(handle.get(), CURLOPT_NOPROGRESS, 0L);
  const CURLcode result = curl_easy_perform(handle.get());
  if (result != CURLE_OK) {
    throw std::runtime_error(std::string("HTTP request failed: ") + curl_easy_strerror(result));
  }
  long status = 0;
  if (curl_easy_getinfo(handle.get(), CURLINFO_RESPONSE_CODE, &status) != CURLE_OK || status < 0 ||
      status > 999) {
    throw std::runtime_error("cannot read HTTP response status");
  }
  return {static_cast<int>(status), std::move(response_body)};
}

void CurlClient::stop() { stopping_.store(true); }

} // namespace gateway::http
