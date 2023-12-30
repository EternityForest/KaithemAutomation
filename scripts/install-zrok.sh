(set -euo pipefail;

apt-get install -y jq

cd $(mktemp -d);

ZROK_VERSION=$(
  curl -sSf https://api.github.com/repos/openziti/zrok/releases/latest \
  | jq -r '.tag_name'
);

case $(uname -m) in
  x86_64)          GOXARCH=amd64 ;;
  aarch64|arm64)   GOXARCH=arm64 ;;
  armv7|armhf|arm) GOXARCH=arm   ;;
  *)               echo "ERROR: unknown arch '$(uname -m)'" >&2
                   exit 1        ;;
esac;

curl -sSfL \
  "https://github.com/openziti/zrok/releases/download/${ZROK_VERSION}/zrok_${ZROK_VERSION#v}_linux_${GOXARCH}.tar.gz" \
  | tar -xz -f -;

sudo install -o root -g root ./zrok /usr/local/bin/;
zrok version;
)