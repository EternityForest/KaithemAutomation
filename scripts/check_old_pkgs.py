import subprocess
import sys
import time
from datetime import UTC, datetime

import requests

# Calculate timestamp for exactly one year ago
ONE_YEAR_AGO = datetime.now(UTC).timestamp() - (365 * 24 * 60 * 60)


def get_installed_packages():
    """Get a dictionary of installed packages and their versions."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=json"],
        capture_output=True,
        text=True,
    )
    import json

    return {pkg["name"]: pkg["version"] for pkg in json.loads(result.stdout)}


def get_pypi_release_date(package_name, version):
    """Fetch the release date of a specific package version from PyPI."""
    url = f"https://pypi.org/pypi/{package_name}/{version}/json"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        # PyPI provides a list of files for a version, get the first one's upload time
        if data.get("urls"):
            upload_time_str = data["urls"][0]["upload_time_iso8601"]
            return datetime.fromisoformat(upload_time_str).timestamp()
    return None


def main():
    print("Analyzing your virtual environment...")
    packages = get_installed_packages()
    old_packages = []

    for i, (name, version) in enumerate(packages.items(), start=1):
        # Optional: Add sleep to respect PyPI rate limits if your venv is huge
        if i % 5 == 0:
            time.sleep(1)

        release_ts = get_pypi_release_date(name, version)

        if release_ts:
            if release_ts < ONE_YEAR_AGO:
                days_old = (datetime.now(UTC).timestamp() - release_ts) // (
                    24 * 3600
                )
                old_packages.append((name, version, int(days_old)))
                print(f"[OLD] {name} {version} ({days_old} days old)")
        else:
            print(f"[?] Could not verify release date for {name}")

    print("\n=== Summary ===")
    if not old_packages:
        print("No packages found that are older than a year.")
    else:
        print(f"Found {len(old_packages)} package(s) released > 1 year ago:")
        for name, version, days in old_packages:
            print(f"- {name}=={version} ({days // 365} years/days old)")


if __name__ == "__main__":
    main()
