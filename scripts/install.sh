#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_user="${INKY_USER:-$(id -un)}"
service_group="${INKY_GROUP:-$(id -gn "$service_user")}"
python_bin="${INKY_PYTHON:-$(command -v python3)}"
service_template="$project_dir/systemd/inky-rotation.service.in"
rendered_service="$(mktemp)"

cleanup() {
  rm -f "$rendered_service"
}
trap cleanup EXIT

if [[ ! -x "$python_bin" ]]; then
  echo "Python interpreter is not executable: $python_bin" >&2
  exit 1
fi

if ! "$python_bin" -c "import PIL, inky"; then
  echo "The selected Python needs Pillow and Pimoroni's inky package." >&2
  echo "Install Inky first, then rerun with INKY_PYTHON=/path/to/python." >&2
  exit 1
fi

mkdir -p "$project_dir/var"

sed \
  -e "s|@USER@|$service_user|g" \
  -e "s|@GROUP@|$service_group|g" \
  -e "s|@PROJECT_DIR@|$project_dir|g" \
  -e "s|@PYTHON@|$python_bin|g" \
  "$service_template" > "$rendered_service"

sudo install -m 0644 "$rendered_service" /etc/systemd/system/inky-rotation.service
sudo install -m 0644 "$project_dir/systemd/inky-rotation.timer" /etc/systemd/system/
sudo systemctl daemon-reload

if systemctl list-unit-files inky-weather.timer --no-legend >/dev/null 2>&1; then
  sudo systemctl disable --now inky-weather.timer || true
fi

sudo systemctl enable --now inky-rotation.timer
echo "Installed. Check the schedule with: systemctl list-timers inky-rotation.timer"
