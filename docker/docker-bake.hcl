variable "DOCKER_BUILD_DIR" {}
variable "KAITHEM_VERSION" {}

group "default" {
  targets = ["kaithem", "kaithem-kiosk", "kaithem-dev"]
}
variable "CACHE_DIR" {
  default = "${BAKE_CMD_CONTEXT}/.buildx-cache"
}

# Platform-independent wheel builder.
target "kaithem-builder" {
  platforms  = ["linux/amd64"]
  output     = ["type=cache"]
  cache-from = ["type=local,src=${CACHE_DIR}/builder"]
  cache-to   = ["type=local,dest=${CACHE_DIR}/builder,mode=max"]
}

# Native rust builder used by the kiosk image.
target "kaithem-native-rust-builder" {
  platforms  = ["linux/amd64", "linux/arm64"]
  output     = ["type=cache"]
  cache-from = ["type=local,src=${CACHE_DIR}/rust-builder"]
  cache-to   = ["type=local,dest=${CACHE_DIR}/rust-builder,mode=max"]
}

target "kaithem" {
  contexts   = { kaithem-builder = "target:kaithem-builder" }
  platforms  = ["linux/amd64", "linux/arm64"]
  output     = ["type=oci,dest=${DOCKER_BUILD_DIR}/kaithem-${KAITHEM_VERSION}.tar"]
  cache-from = ["type=local,src=${CACHE_DIR}/kaithem"]
  cache-to   = ["type=local,dest=${CACHE_DIR}/kaithem,mode=max"]
}

target "kaithem-kiosk" {
  contexts   = { kaithem-native-rust-builder = "target:kaithem-native-rust-builder" }
  platforms  = ["linux/amd64", "linux/arm64"]
  output     = ["type=oci,dest=${DOCKER_BUILD_DIR}/kaithem-kiosk-${KAITHEM_VERSION}.tar"]
  cache-from = ["type=local,src=${CACHE_DIR}/kiosk"]
  cache-to   = ["type=local,dest=${CACHE_DIR}/kiosk,mode=max"]
}

target "kaithem-dev" {
  contexts   = { kaithem-builder = "target:kaithem-builder" }
  platforms  = ["linux/amd64"]
  output     = ["type=oci,dest=${DOCKER_BUILD_DIR}/kaithem-dev-${KAITHEM_VERSION}.tar"]
  cache-from = ["type=local,src=${CACHE_DIR}/dev"]
  cache-to   = ["type=local,dest=${CACHE_DIR}/dev,mode=max"]
}