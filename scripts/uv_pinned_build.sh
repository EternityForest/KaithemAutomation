#!/bin/bash
set -euo pipefail

# For safety, only run this with a clean working directory.
uv lock --check
if [ -n "$(git status --porcelain)" ]; then
    echo "Working directory not clean."
    git status
    exit 1
fi

# CD to the directory one level up from where this script is.
cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"/..

cp pyproject.toml pyproject.toml.bak
cp uv.lock uv.lock.bak

# Export all non-development dependency versions from uv.lock.
uv export --locked --no-hashes --no-dev --no-emit-workspace \
    --output-file pinned_requirements.txt > /dev/null


file="pinned_requirements.txt"

if grep -Eq '==[\d \.]*[0-9][\d \.]*[A-Za-z]' "$file"; then
  echo "❌ Error: prerelease versions detected in $file"
  echo "Lines matching==[\d \.]*[0-9][\d \.]*[A-Za-z]:"
  grep -En '==[\d \.]*[0-9][\d \.]*[A-Za-z]' "$file"
  exit 1
fi


uv add  -r pinned_requirements.txt

# Build the package.
uv build

# Restore the original project state.
mv pyproject.toml.bak pyproject.toml
mv uv.lock.bak uv.lock
rm -f pinned_requirements.txt


# Check the wheel
dist_dir="dist"
venv_dir=".venv_wheel_test"
expected_bin="kaithem"


# === 2️⃣ Find the newest wheel ===
latest_wheel=$(ls -t "$dist_dir"/*.whl 2>/dev/null | head -n 1 || true)
if [[ -z "$latest_wheel" ]]; then
  echo "❌ No wheel found in $dist_dir/"
  exit 1
fi
echo "🧩 Found wheel: $latest_wheel"

# === 3️⃣ Create temporary venv and test install ===
rm -rf "$venv_dir"
python3 -m venv "$venv_dir"
source "$venv_dir/bin/activate"

echo "⚙️  Installing with uv..."
if ! uv pip install "$latest_wheel"; then
  echo "❌ Installation from wheel failed!"
  deactivate
  rm -rf "$venv_dir"
  exit 1
fi

echo "✅ Wheel installed successfully in test venv."

# Optionally: run smoke tests or import check
if ! python -c "import $(basename "$latest_wheel" | cut -d'-' -f1)" &>/dev/null; then
  echo "❌ Import test failed — module not importable."
  deactivate
  rm -rf "$venv_dir"
  exit 1
fi
echo "✅ Import test passed."


# === 5️⃣ Check for expected binary ===
if [[ ! -x "$venv_dir/bin/$expected_bin" ]]; then
  echo "❌ Expected binary '$expected_bin' not found in $venv_dir/bin/"
  echo "Contents of venv/bin:"
  ls -1 "$venv_dir/bin"
  deactivate
  rm -rf "$venv_dir"
  exit 1
fi
echo "✅ Binary '$expected_bin' found."


# Clean up
deactivate
rm -rf "$venv_dir"

echo "🎉 Sanity checks passed — wheel is good."