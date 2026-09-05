#!/usr/bin/env bash
set -Eeuo pipefail

FLAG_DIR="/var/lib/nvidia-spark-run-apt-upgrade-once"
FLAG_FILE="${FLAG_DIR}/done"
TAG="nvidia-spark-run-apt-upgrade-once"

log() { logger -t "${TAG}" "$*"; }

# Get the installed version of a package
# Usage: get_package_version <package_name>
# Returns: version string or empty string if not installed
get_package_version() {
    local package_name="$1"
    dpkg-query -W -f='${Version}' "${package_name}" 2>/dev/null || echo ""
}

get_kernel_short_version() {
    local version="$1"
    echo "${version}" | sed 's/\(.*-[0-9]\+\).*/\1/'
}

# Check if a package version is greater than or equal to a required version
# Usage: is_version_ge <installed_version> <required_version>
# Returns: 0 (true) if installed_version >= required_version, 1 (false) otherwise
is_version_ge() {
    local installed_version="$1"
    local required_version="$2"
    
    # Return false if installed version is empty
    if [[ -z "${installed_version}" ]] || [[ -z "${required_version}" ]]; then
        log "installed_version or required_version is empty; returning false"
        return 1
    fi
    
    # Use dpkg to compare versions properly (handles epochs, debian revisions, etc.)
    dpkg --compare-versions "${installed_version}" ge "${required_version}"
}

set_done_flag() {
    install -d -m 0700 "${FLAG_DIR}"
    echo "done" > "${FLAG_FILE}"
    chmod 0400 "${FLAG_FILE}"
}

# Already completed
if [[ -e "${FLAG_FILE}" ]]; then
    log "already completed; exiting"
    systemctl disable nvidia-spark-run-apt-upgrade-once.service || true
    exit 0
fi

#Define versions
MIN_CUDA_COMPUTE_REPO_LOWPRI_VERSION="25.09-2"
INSTALLED_CUDA_COMPUTE_REPO_LOWPRI_VERSION=$(get_package_version "cuda-compute-repo-lowpri")
NVIDIA_INSTALLED_MODULES_VERSION=$(get_kernel_short_version "$(get_package_version "linux-modules-nvidia-580-open-nvidia-hwe-24.04")")
RUNNING_KERNEL_VERSION=$(get_kernel_short_version "$(uname -r)")

if [ -z ${INSTALLED_CUDA_COMPUTE_REPO_LOWPRI_VERSION} ]; then
    log "cuda-compute-repo-lowpri is not installed; exiting"
    set_done_flag
    exit 0
fi

if ! is_version_ge ${INSTALLED_CUDA_COMPUTE_REPO_LOWPRI_VERSION} ${MIN_CUDA_COMPUTE_REPO_LOWPRI_VERSION}; then
    log "cuda-compute-repo-lowpri version ${INSTALLED_CUDA_COMPUTE_REPO_LOWPRI_VERSION} is not greater than or equal to ${MIN_CUDA_COMPUTE_REPO_LOWPRI_VERSION}; exiting"
    set_done_flag
else
    # Check if linux-modules-nvidia-580-open-nvidia-hwe-24.04 matches running kernel
    if [ ${RUNNING_KERNEL_VERSION} = ${NVIDIA_INSTALLED_MODULES_VERSION} ]; then
        log "Package version of linux-modules-nvidia-580-open-nvidia-hwe-24.04 ${NVIDIA_INSTALLED_MODULES_VERSION} matches running kernel ${RUNNING_KERNEL_VERSION}; exiting"
        set_done_flag
    else
        # need to run apt update and upgrade and touch the flag file
        log "Package version of linux-modules-nvidia-580-open-nvidia-hwe-24.04 ${NVIDIA_INSTALLED_MODULES_VERSION} does not match running kernel ${RUNNING_KERNEL_VERSION}"
        log "Running apt update and upgrade"
        /usr/bin/nm-online --wait-for-startup --timeout 300
        apt-get -y update || true
        apt-get install -y nvidia-driver-580-open linux-modules-nvidia-580-open-nvidia-hwe-24.04 ||:
        apt-get -y full-upgrade || true
        log "apt update and upgrade completed; creating flag file and marking done"
        set_done_flag
        reboot
    fi
fi

exit 0
