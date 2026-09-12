# Production build configuration for Kaithem.
#
# This file is not standalone: it is merged with docker-compose.yaml, which
# supplies the build context, dockerfile, and build args for each target.
# Invoke it as:
#
#   docker buildx bake -f docker-compose.yaml -f docker-bake.hcl
#
# It adds the production-only settings that used to live as --set CLI flags
# and x-bake: blocks:
#   - The intermediate builder images (kaithem-builder,
#     kaithem-native-rust-builder) are separate targets with cache-only
#     output; they are built once and consumed by the final images.
#   - The final images (kaithem, kaithem-kiosk, kaithem-dev) depend on the
#     builders via the `contexts` attribute (target: form) and are exported
#     to OCI tarballs under ${DOCKER_BUILD_DIR}.
#   - kaithem-dev is restricted to linux/amd64 to keep dev fast.
#   - The default group runs all three production targets.
#
# DOCKER_BUILD_DIR and KAITHEM_VERSION are exported by the Makefile and must
# be set in the environment (they have no defaults, matching the :?error
# guards in docker-compose.yaml).

variable "DOCKER_BUILD_DIR" {}
variable "KAITHEM_VERSION" {}

group "default" {
  targets = ["kaithem", "kaithem-kiosk", "kaithem-dev"]
}

# Platform-independent wheel builder. amd64 only because the wheel itself
# is platform-independent and the build is fastest on amd64.
target "kaithem-builder" {
  platforms = ["linux/amd64"]
  output    = ["type=cache"]
}

# Native rust builder used by the kiosk image.
target "kaithem-native-rust-builder" {
  platforms = ["linux/amd64", "linux/arm64"]
  output    = ["type=cache"]
}

target "kaithem" {
  # The app Dockerfile references `FROM kaithem-builder`.
  contexts  = { kaithem-builder = "target:kaithem-builder" }
  platforms = ["linux/amd64", "linux/arm64"]
  output    = ["type=oci,dest=${DOCKER_BUILD_DIR}/kaithem-${KAITHEM_VERSION}.tar"]
}

target "kaithem-kiosk" {
  # The kiosk Dockerfile references `FROM kaithem-native-rust-builder`.
  contexts  = { kaithem-native-rust-builder = "target:kaithem-native-rust-builder" }
  platforms = ["linux/amd64", "linux/arm64"]
  output    = ["type=oci,dest=${DOCKER_BUILD_DIR}/kaithem-kiosk-${KAITHEM_VERSION}.tar"]
}

target "kaithem-dev" {
  # The dev Dockerfile is based on the app image and reuses its builder.
  contexts  = { kaithem-builder = "target:kaithem-builder" }
  platforms = ["linux/amd64"]
  output    = ["type=oci,dest=${DOCKER_BUILD_DIR}/kaithem-dev-${KAITHEM_VERSION}.tar"]
}
