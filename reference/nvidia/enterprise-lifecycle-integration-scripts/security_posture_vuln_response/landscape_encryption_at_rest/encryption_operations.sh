#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# Encryption Operations Script - Wrapper for encryption reporting and enablement.
# Modes: report, fscrypt, reencrypt, encrypt, encrypt-once, resume, verify, tpm-status, tpm-enable, usb-key, luks-guide, fde-root

set -eo pipefail

SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || echo "$0")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-report}"

FSCRYPT_AUTO_ENCRYPT="${FSCRYPT_AUTO_ENCRYPT:-false}"
FSCRYPT_PROTECTOR_NAME="${FSCRYPT_PROTECTOR_NAME:-dgx_spark_protector}"
FSCRYPT_PASSPHRASE="${FSCRYPT_PASSPHRASE:-}"
FSCRYPT_RAW_KEY_FILE="${FSCRYPT_RAW_KEY_FILE:-}"

FDE_MAP_NAME="${FDE_MAP_NAME:-root_crypt}"
FDE_REDUCE_SIZE="${FDE_REDUCE_SIZE:-32M}"
FDE_TPM_PCRS="${FDE_TPM_PCRS:-0+7}"
FDE_STATE_ROOT="${FDE_STATE_ROOT:-/var/lib/dgx_spark_management/security_posture_vuln_response/landscape_encryption_at_rest/fde_workflow}"
FDE_STATE_FILE="${FDE_STATE_ROOT}/state.env"

USB_KEY_MOUNT_PREFIX="${USB_KEY_MOUNT_PREFIX:-/run/dgx_fde_usb}"
USB_KEY_LABEL="${USB_KEY_LABEL:-DGXFDEBOOT}"
USB_KEY_CONFIG_REL="${USB_KEY_CONFIG_REL:-dgx-fde/unattended.conf}"
USB_KEY_BOOT_LABEL="${USB_KEY_BOOT_LABEL:-DGX FDE TEMP USB}"
USB_KEY_ESP_LABEL="${USB_KEY_ESP_LABEL:-DGXFDEBOOT}"
USB_KEY_ROOT_LABEL="${USB_KEY_ROOT_LABEL:-DGXFDEROOT}"
USB_OFFLINE_SERVICE="${USB_OFFLINE_SERVICE:-dgx-fde-offline.service}"
USB_OFFLINE_SCRIPT="${USB_OFFLINE_SCRIPT:-/usr/local/sbin/dgx_usb_offline_encrypt.sh}"
USB_BOOTSTRAP_STAGE_PREFIX="${USB_BOOTSTRAP_STAGE_PREFIX:-/var/tmp/dgx_fde_usb_stage}"
USB_RETRY_ATTEMPTS="${USB_RETRY_ATTEMPTS:-3}"

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: Must run as root."
        exit 1
    fi
}

risk_acknowledged() {
    local ack="${1:-}"
    if [ "$ack" = "--i-accept-risks" ] || [ "${I_ACCEPT_THE_RISKS:-}" = "true" ]; then
        return 0
    fi
    return 1
}

is_true() {
    case "${1:-}" in
        true|TRUE|True|1|yes|YES|on|ON)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

require_command() {
    local cmd="$1"
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: Required command not found: $cmd"
        exit 1
    }
}

retry_cmd() {
    local attempts="${1:-1}"
    local n=1
    shift

    while true; do
        if "$@"; then
            return 0
        fi
        if [ "$n" -ge "$attempts" ]; then
            return 1
        fi
        echo "WARN: Command failed (attempt $n/$attempts). Retrying..."
        n=$((n + 1))
        sleep 2
    done
}

boot_fallback_filename() {
    case "$(uname -m 2>/dev/null || true)" in
        aarch64|arm64)
            echo "BOOTAA64.EFI"
            ;;
        x86_64|amd64)
            echo "BOOTX64.EFI"
            ;;
        *)
            # Default to x86_64 fallback filename when architecture mapping is unknown.
            echo "BOOTX64.EFI"
            ;;
    esac
}

choose_bootloader_source() {
    local candidate
    for candidate in \
        /boot/efi/EFI/ubuntu/shimaa64.efi \
        /boot/efi/EFI/ubuntu/shimx64.efi \
        /boot/efi/EFI/ubuntu/grubaa64.efi \
        /boot/efi/EFI/ubuntu/grubx64.efi \
        /boot/efi/EFI/BOOT/BOOTAA64.EFI \
        /boot/efi/EFI/BOOT/BOOTX64.EFI; do
        [ -f "$candidate" ] && { echo "$candidate"; return 0; }
    done
    return 1
}

resolve_usb_device_details() {
    local source="$1"
    local type part disk parent existing

    USB_SOURCE="$source"
    USB_PARTITION=""
    USB_DISK=""
    USB_MOUNTPOINT=""
    USB_AUTOMOUNTED=false

    if [ -d "$source" ]; then
        USB_MOUNTPOINT="$source"
        existing="$(findmnt -rn -T "$source" -o SOURCE 2>/dev/null || true)"
        if [ -n "$existing" ] && [ -b "$existing" ]; then
            type="$(lsblk -ndo TYPE "$existing" 2>/dev/null || true)"
            if [ "$type" = "part" ]; then
                USB_PARTITION="$existing"
                parent="$(lsblk -ndo PKNAME "$existing" 2>/dev/null || true)"
                [ -n "$parent" ] && USB_DISK="/dev/$parent"
            elif [ "$type" = "disk" ]; then
                USB_DISK="$existing"
            fi
        fi
        return 0
    fi

    [ -b "$source" ] || {
        echo "ERROR: USB source must be a mountpoint or block device: $source"
        return 1
    }

    type="$(lsblk -ndo TYPE "$source" 2>/dev/null || true)"
    case "$type" in
        disk)
            USB_DISK="$source"
            part="$(lsblk -nrpo NAME,TYPE "$source" 2>/dev/null | awk '$2=="part"{print $1; exit}')"
            [ -n "$part" ] && USB_PARTITION="$part"
            ;;
        part)
            USB_PARTITION="$source"
            parent="$(lsblk -ndo PKNAME "$source" 2>/dev/null || true)"
            [ -n "$parent" ] && USB_DISK="/dev/$parent"
            ;;
        *)
            echo "ERROR: Unsupported USB source type for $source (type=$type)"
            return 1
            ;;
    esac

    return 0
}

mount_usb_source() {
    local source="$1"
    local existing

    resolve_usb_device_details "$source" || return 1

    if [ -n "$USB_MOUNTPOINT" ]; then
        return 0
    fi

    [ -n "$USB_PARTITION" ] || {
        echo "ERROR: No USB partition found for source: $source"
        return 1
    }

    existing="$(findmnt -rn -S "$USB_PARTITION" -o TARGET 2>/dev/null || true)"
    if [ -n "$existing" ]; then
        USB_MOUNTPOINT="$existing"
        return 0
    fi

    USB_MOUNTPOINT="$(mktemp -d "${USB_KEY_MOUNT_PREFIX}.XXXXXX")"
    mount "$USB_PARTITION" "$USB_MOUNTPOINT"
    USB_AUTOMOUNTED=true
}

cleanup_usb_mount() {
    if [ "${USB_AUTOMOUNTED:-false}" = "true" ] && [ -n "${USB_MOUNTPOINT:-}" ]; then
        umount "$USB_MOUNTPOINT" 2>/dev/null || true
        rmdir "$USB_MOUNTPOINT" 2>/dev/null || true
    fi
    USB_AUTOMOUNTED=false
    USB_MOUNTPOINT=""
}

partition_usb_disk() {
    local disk="$1"
    local esp_part root_part

    require_command parted
    require_command mkfs.vfat
    require_command mkfs.ext4

    echo "Partitioning USB disk ${disk} for temporary offline encryption OS..."
    parted -s "$disk" mklabel gpt
    parted -s "$disk" mkpart primary fat32 1MiB 513MiB
    parted -s "$disk" mkpart primary ext4 513MiB 100%
    parted -s "$disk" set 1 esp on
    partprobe "$disk" 2>/dev/null || true
    sleep 1

    esp_part="$(lsblk -nrpo NAME,TYPE,PARTN "$disk" 2>/dev/null | awk '$2=="part" && $3=="1"{print $1; exit}')"
    root_part="$(lsblk -nrpo NAME,TYPE,PARTN "$disk" 2>/dev/null | awk '$2=="part" && $3=="2"{print $1; exit}')"

    [ -n "$esp_part" ] || {
        echo "ERROR: Could not detect created USB ESP partition on ${disk}."
        return 1
    }
    [ -n "$root_part" ] || {
        echo "ERROR: Could not detect created USB root partition on ${disk}."
        return 1
    }

    mkfs.vfat -F 32 -n "$USB_KEY_ESP_LABEL" "$esp_part"
    mkfs.ext4 -F -L "$USB_KEY_ROOT_LABEL" "$root_part"

    USB_PARTITION="$esp_part"
    USB_ROOT_PARTITION="$root_part"
}

format_usb_esp_if_needed() {
    local part="$1"
    local fstype

    require_command mkfs.vfat

    fstype="$(lsblk -ndo FSTYPE "$part" 2>/dev/null || true)"
    if [ "$fstype" = "vfat" ] || [ "$fstype" = "fat32" ]; then
        return 0
    fi

    echo "Formatting ${part} as FAT32 for EFI boot usage..."
    mkfs.vfat -F 32 -n "$USB_KEY_ESP_LABEL" "$part"
}

prepare_usb_offline_rootfs() {
    local usb_disk="$1"
    local esp_part="$2"
    local root_part="$3"
    local root_mnt stage_mnt release arch mirror grub_target grub_pkg
    local kernel_pkg_base

    require_command debootstrap
    require_command chroot
    require_command grub-install
    require_command mount
    require_command umount
    require_command rsync

    release="$(. /etc/os-release 2>/dev/null; echo "${VERSION_CODENAME:-noble}")"
    arch="$(dpkg --print-architecture 2>/dev/null || echo arm64)"

    case "$arch" in
        arm64|aarch64)
            mirror="http://ports.ubuntu.com/ubuntu-ports"
            grub_target="arm64-efi"
            grub_pkg="grub-efi-arm64-bin"
            ;;
        amd64|x86_64)
            mirror="http://archive.ubuntu.com/ubuntu"
            grub_target="x86_64-efi"
            grub_pkg="grub-efi-amd64-bin"
            ;;
        *)
            echo "ERROR: Unsupported architecture for USB offline rootfs bootstrap: $arch"
            return 1
            ;;
    esac

    stage_mnt="$(mktemp -d "${USB_BOOTSTRAP_STAGE_PREFIX}.XXXXXX")"
    echo "Bootstrapping Ubuntu ${release} (${arch}) into local stage: ${stage_mnt}"
    retry_cmd "$USB_RETRY_ATTEMPTS" debootstrap --arch="$arch" --variant=minbase "$release" "$stage_mnt" "$mirror"
    cp -f /etc/resolv.conf "$stage_mnt/etc/resolv.conf"

    cat > "$stage_mnt/etc/fstab" <<EOF
LABEL=${USB_KEY_ROOT_LABEL} / ext4 defaults 0 1
LABEL=${USB_KEY_ESP_LABEL} /boot/efi vfat umask=0077 0 1
EOF
    echo "dgx-fde-usb" > "$stage_mnt/etc/hostname"

    for d in dev proc sys run; do
        mkdir -p "$stage_mnt/$d"
        mount --bind "/$d" "$stage_mnt/$d"
    done

    chroot "$stage_mnt" apt-get update -qq
    chroot "$stage_mnt" apt-get install -y -qq \
        systemd-sysv initramfs-tools ca-certificates \
        cryptsetup-bin cryptsetup-initramfs e2fsprogs tpm2-tools \
        efibootmgr grub-common "$grub_pkg"

    kernel_pkg_base="linux-image-generic"
    if ! chroot "$stage_mnt" apt-get install -y -qq "$kernel_pkg_base"; then
        kernel_pkg_base="linux-image-$(uname -r)"
        chroot "$stage_mnt" apt-get install -y -qq "$kernel_pkg_base"
    fi

    mkdir -p "$stage_mnt/etc/dgx-fde"
    cat > "$stage_mnt/$USB_OFFLINE_SCRIPT" <<'RUNNER_EOF'
#!/bin/bash
set -eo pipefail

CONFIG_PATH="/boot/efi/dgx-fde/unattended.conf"
TARGET_MNT="/mnt/targetroot"

log() { echo "[dgx-fde-offline] $*"; }
fail() { echo "[dgx-fde-offline][ERROR] $*" >&2; exit 1; }

[ -f "$CONFIG_PATH" ] || fail "Missing config: $CONFIG_PATH"
# shellcheck disable=SC1090
. "$CONFIG_PATH"

[ "${ALLOW_UNATTENDED:-false}" = "true" ] || fail "ALLOW_UNATTENDED must be true in USB config."
[ -n "${FDE_DEVICE:-}" ] || fail "FDE_DEVICE must be set in USB config."
[ -b "$FDE_DEVICE" ] || fail "FDE_DEVICE is not a block device: $FDE_DEVICE"
[ -n "${FDE_PASSPHRASE:-}" ] || fail "FDE_PASSPHRASE must be set in USB config."

FDE_MAP_NAME="${FDE_MAP_NAME:-root_crypt}"
FDE_REDUCE_SIZE="${FDE_REDUCE_SIZE:-32M}"
FDE_TPM_PCRS="${FDE_TPM_PCRS:-0+7}"
ENROLL_TPM="${ENROLL_TPM:-true}"

if findmnt -rn -S "$FDE_DEVICE" >/dev/null 2>&1; then
    fail "Target device is mounted. Refusing to continue."
fi

ROOT_SRC="$(findmnt -no SOURCE / 2>/dev/null || true)"
if [ "$ROOT_SRC" = "$FDE_DEVICE" ]; then
    fail "Current root is target device. Must boot from USB rootfs."
fi

KEYFILE="$(mktemp)"
chmod 600 "$KEYFILE"
printf '%s' "$FDE_PASSPHRASE" > "$KEYFILE"
trap 'shred -u "$KEYFILE" 2>/dev/null || rm -f "$KEYFILE"' EXIT

if cryptsetup isLuks "$FDE_DEVICE" 2>/dev/null; then
    log "Target already has LUKS header; skipping encrypt operation."
else
    log "Starting offline reencrypt on $FDE_DEVICE ..."
    cryptsetup reencrypt --encrypt --reduce-device-size "$FDE_REDUCE_SIZE" \
        --key-file "$KEYFILE" --batch-mode --verbose "$FDE_DEVICE"
fi

if [ ! -e "/dev/mapper/$FDE_MAP_NAME" ]; then
    cryptsetup open --key-file "$KEYFILE" "$FDE_DEVICE" "$FDE_MAP_NAME"
fi

e2fsck -fy "/dev/mapper/$FDE_MAP_NAME" || true
resize2fs "/dev/mapper/$FDE_MAP_NAME" || true

mkdir -p "$TARGET_MNT"
mount "/dev/mapper/$FDE_MAP_NAME" "$TARGET_MNT"

LUKS_UUID="$(blkid -s UUID -o value "$FDE_DEVICE")"
[ -n "$LUKS_UUID" ] || fail "Could not determine LUKS UUID for $FDE_DEVICE."

if [ -f "$TARGET_MNT/etc/crypttab" ]; then
    awk -v map="$FDE_MAP_NAME" '$1 != map { print }' "$TARGET_MNT/etc/crypttab" > "$TARGET_MNT/etc/crypttab.new"
    mv "$TARGET_MNT/etc/crypttab.new" "$TARGET_MNT/etc/crypttab"
fi
echo "$FDE_MAP_NAME UUID=$LUKS_UUID none luks,discard" >> "$TARGET_MNT/etc/crypttab"

if [ -f "$TARGET_MNT/etc/fstab" ]; then
    awk -v dev="$FDE_DEVICE" -v map="/dev/mapper/$FDE_MAP_NAME" '
        /^[[:space:]]*#/ { print; next }
        NF < 2 { print; next }
        {
            if ($2 == "/" && ($1 == dev || index($1, "UUID=") == 1)) {
                $1 = map
            }
            print
        }
    ' "$TARGET_MNT/etc/fstab" > "$TARGET_MNT/etc/fstab.new"
    mv "$TARGET_MNT/etc/fstab.new" "$TARGET_MNT/etc/fstab"
fi

for d in dev proc sys run; do
    mount --bind "/$d" "$TARGET_MNT/$d"
done

chroot "$TARGET_MNT" update-initramfs -u -k all
chroot "$TARGET_MNT" update-grub || true

if [ "$ENROLL_TPM" = "true" ] && chroot "$TARGET_MNT" command -v systemd-cryptenroll >/dev/null 2>&1; then
    if [ -e /dev/tpmrm0 ] || [ -e /dev/tpm0 ]; then
        chroot "$TARGET_MNT" systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs="$FDE_TPM_PCRS" "$FDE_DEVICE" || true
    fi
fi

for d in run sys proc dev; do
    umount "$TARGET_MNT/$d" 2>/dev/null || true
done
umount "$TARGET_MNT" 2>/dev/null || true
cryptsetup close "$FDE_MAP_NAME" 2>/dev/null || true

sed -i 's/^ALLOW_UNATTENDED=.*/ALLOW_UNATTENDED=false/' "$CONFIG_PATH" || true

systemctl disable --now dgx-fde-offline.service >/dev/null 2>&1 || true
log "Offline encryption flow complete. Rebooting to internal disk."
systemctl reboot
RUNNER_EOF
    chmod 0700 "$stage_mnt/$USB_OFFLINE_SCRIPT"

    cat > "$stage_mnt/etc/systemd/system/$USB_OFFLINE_SERVICE" <<EOF
[Unit]
Description=DGX Spark Offline USB Encryption Runner
After=local-fs.target
Wants=local-fs.target
ConditionPathExists=$USB_OFFLINE_SCRIPT

[Service]
Type=oneshot
ExecStart=$USB_OFFLINE_SCRIPT
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    mkdir -p "$stage_mnt/etc/systemd/system/multi-user.target.wants"
    ln -sf "../$USB_OFFLINE_SERVICE" "$stage_mnt/etc/systemd/system/multi-user.target.wants/$USB_OFFLINE_SERVICE"

    for d in run sys proc dev; do
        umount "$stage_mnt/$d" 2>/dev/null || true
    done
    sync

    root_mnt="$(mktemp -d /run/dgx_fde_usb_root.XXXXXX)"
    mount "$root_part" "$root_mnt"
    mkdir -p "$root_mnt/boot/efi"
    mount "$esp_part" "$root_mnt/boot/efi"

    echo "Copying staged rootfs to USB root partition..."
    retry_cmd "$USB_RETRY_ATTEMPTS" rsync -aHAX --numeric-ids --delete "${stage_mnt}/" "${root_mnt}/"
    sync

    for d in dev proc sys run; do
        mkdir -p "$root_mnt/$d"
        mount --bind "/$d" "$root_mnt/$d"
    done

    chroot "$root_mnt" grub-install --target="$grub_target" --efi-directory=/boot/efi --boot-directory=/boot --removable --recheck
    chroot "$root_mnt" update-initramfs -u -k all
    chroot "$root_mnt" update-grub || true

    for d in run sys proc dev; do
        umount "$root_mnt/$d" 2>/dev/null || true
    done
    umount "$root_mnt/boot/efi" 2>/dev/null || true
    umount "$root_mnt" 2>/dev/null || true
    rmdir "$root_mnt" 2>/dev/null || true
    rm -rf "$stage_mnt" 2>/dev/null || true

    echo "USB offline rootfs is bootable and configured for $USB_OFFLINE_SERVICE."
}

write_usb_unattended_config() {
    local mountpoint="$1"
    local config_path="$mountpoint/$USB_KEY_CONFIG_REL"

    mkdir -p "$(dirname "$config_path")"
    cat > "$config_path" <<EOF
# DGX Spark USB offline encryption control file
# This file is read by $USB_OFFLINE_SCRIPT from the booted USB environment.
ALLOW_UNATTENDED=false
FDE_DEVICE=/dev/nvme0n1p2
FDE_PASSPHRASE=
FDE_MAP_NAME=$FDE_MAP_NAME
FDE_REDUCE_SIZE=$FDE_REDUCE_SIZE
FDE_TPM_PCRS=$FDE_TPM_PCRS
ENROLL_TPM=true
NOTES=
UPDATED_BY=
UPDATED_AT_UTC=
EOF
    chmod 600 "$config_path"
    echo "USB unattended config written: $config_path"
}

load_unattended_config_from_usb() {
    local usb_source="$1"
    local expected_device="$2"
    local config_path
    local allow_unattended=false
    local cfg_device=""

    mount_usb_source "$usb_source" || return 1
    config_path="$USB_MOUNTPOINT/$USB_KEY_CONFIG_REL"
    [ -f "$config_path" ] || {
        echo "ERROR: Missing unattended config on USB key: $config_path"
        cleanup_usb_mount
        return 1
    }

    # shellcheck disable=SC1090
    . "$config_path"

    if is_true "${ALLOW_UNATTENDED:-false}"; then
        allow_unattended=true
    fi
    cfg_device="${FDE_DEVICE:-}"

    cleanup_usb_mount

    if [ "$allow_unattended" != "true" ]; then
        echo "ERROR: USB config does not permit unattended mode (ALLOW_UNATTENDED=true required)."
        return 1
    fi

    if [ -n "$cfg_device" ] && [ "$cfg_device" != "$expected_device" ]; then
        echo "ERROR: USB config FDE_DEVICE=$cfg_device does not match requested device $expected_device."
        return 1
    fi

    return 0
}

current_boot_order() {
    efibootmgr | awk -F'BootOrder: ' '/BootOrder:/{print $2}' | tr -d '\r'
}

create_usb_boot_entry_once() {
    local usb_source="$1"
    local ack="$2"
    local part part_num disk before_ids after_ids new_id old_order loader
    local id token filtered_order

    require_root
    require_command efibootmgr

    if ! risk_acknowledged "$ack"; then
        echo "ERROR: usb-key arm-once requires explicit acknowledgement."
        echo "Pass --i-accept-risks OR set I_ACCEPT_THE_RISKS=true."
        return 1
    fi

    resolve_usb_device_details "$usb_source" || return 1
    part="$USB_PARTITION"
    disk="$USB_DISK"

    [ -n "$part" ] || { echo "ERROR: Could not resolve USB partition from $usb_source"; return 1; }
    [ -n "$disk" ] || { echo "ERROR: Could not resolve USB disk from $usb_source"; return 1; }

    part_num="$(lsblk -ndo PARTN "$part" 2>/dev/null || true)"
    [ -n "$part_num" ] || { echo "ERROR: Could not determine partition number for $part"; return 1; }

    loader="\\EFI\\BOOT\\$(boot_fallback_filename)"
    old_order="$(current_boot_order)"
    before_ids="$(efibootmgr | awk '/^Boot[0-9A-Fa-f]{4}\\*/{print substr($1,5,4)}' | tr '\n' ' ')"

    efibootmgr -c -d "$disk" -p "$part_num" -L "$USB_KEY_BOOT_LABEL" -l "$loader" >/dev/null
    after_ids="$(efibootmgr | awk '/^Boot[0-9A-Fa-f]{4}\\*/{print substr($1,5,4)}' | tr '\n' ' ')"

    new_id=""
    for id in $after_ids; do
        case " $before_ids " in
            *" $id "*) ;;
            *) new_id="$id"; break ;;
        esac
    done

    [ -n "$new_id" ] || {
        echo "ERROR: Failed to identify newly created USB UEFI boot entry."
        return 1
    }

    if [ -n "$old_order" ]; then
        filtered_order=""
        for token in $(echo "$old_order" | tr ',' ' '); do
            for id in $after_ids; do
                if [ "$token" = "$id" ]; then
                    if [ -z "$filtered_order" ]; then
                        filtered_order="$token"
                    else
                        filtered_order="${filtered_order},${token}"
                    fi
                    break
                fi
            done
        done
        if [ -n "$filtered_order" ]; then
            efibootmgr -o "$filtered_order" >/dev/null || true
        fi
    fi
    efibootmgr -n "$new_id" >/dev/null

    echo "BootNext configured to temporary USB boot entry: Boot${new_id}"
    echo "Normal boot order preserved: ${old_order:-unknown}"
}

secure_delete_file() {
    local path="${1:-}"
    [ -n "$path" ] && [ -f "$path" ] && shred -vfz "$path" >/dev/null 2>&1 || true
    [ -n "$path" ] && [ -f "$path" ] && rm -f "$path" || true
}

tpm_is_present() {
    [ -e /dev/tpmrm0 ] || [ -e /dev/tpm0 ] || [ -e /sys/class/tpm/tpm0 ]
}

collect_firmware_attr_candidates() {
    local attr
    for attr in /sys/class/firmware-attributes/*/attributes/*; do
        [ -e "$attr/current_value" ] || continue
        case "$(basename "$attr" | tr '[:upper:]' '[:lower:]')" in
            *tpm*|*trusted*comput*|*security*device*)
                echo "$attr"
                ;;
        esac
    done
}

enable_tpm_via_firmware_attributes() {
    local apply="$1"
    local changed=false
    local seen=false
    local attr current possible chosen

    while IFS= read -r attr; do
        seen=true
        current="$(cat "$attr/current_value" 2>/dev/null || true)"
        possible="$(cat "$attr/possible_values" 2>/dev/null || true)"

        if echo "$current" | tr '[:upper:]' '[:lower:]' | grep -Eq '^(enable|enabled|on|true|1)$'; then
            echo "TPM-like attribute already enabled: $(basename "$attr")=${current}"
            continue
        fi

        chosen="$(echo "$possible" | tr ',[]' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -E '^(Enable|Enabled|On|True|1)$' | head -n1 || true)"
        [ -z "$chosen" ] && chosen="Enable"

        if [ "$apply" = "true" ]; then
            if echo "$chosen" > "$attr/current_value" 2>/dev/null; then
                echo "Set $(basename "$attr") to ${chosen}"
                changed=true
            else
                echo "WARN: Failed to set $(basename "$attr") via firmware-attributes"
            fi
        else
            echo "Would set $(basename "$attr") from '${current}' to '${chosen}'"
        fi
    done < <(collect_firmware_attr_candidates)

    if [ "$seen" = false ]; then
        echo "No TPM-related /sys/class/firmware-attributes entries detected."
        return 2
    fi
    if [ "$apply" = "true" ] && [ "$changed" = false ]; then
        return 1
    fi
    return 0
}

install_fde_dependencies() {
    local arch grub_pkg

    if ! command -v apt-get >/dev/null 2>&1; then
        echo "WARN: apt-get not found; skipping dependency installation."
        return 0
    fi

    arch="$(dpkg --print-architecture 2>/dev/null || echo arm64)"
    case "$arch" in
        arm64|aarch64) grub_pkg="grub-efi-arm64-bin" ;;
        amd64|x86_64) grub_pkg="grub-efi-amd64-bin" ;;
        *) grub_pkg="grub-efi-amd64-bin" ;;
    esac

    echo "Installing required packages (cryptsetup-initramfs, tpm2-tools, e2fsprogs, debootstrap, boot tools)..."
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        cryptsetup-initramfs cryptsetup-bin tpm2-tools e2fsprogs \
        debootstrap parted dosfstools rsync "$grub_pkg" grub-common efibootmgr
}

resolve_fde_device() {
    local device="${1:-}"
    if [ -n "$device" ]; then
        echo "$device"
        return 0
    fi

    if [ -f "$FDE_STATE_FILE" ]; then
        # shellcheck disable=SC1090
        . "$FDE_STATE_FILE"
        if [ -n "${FDE_DEVICE:-}" ]; then
            echo "$FDE_DEVICE"
            return 0
        fi
    fi

    return 1
}

save_fde_state() {
    local device="$1"
    local luks_uuid root_source

    mkdir -p "$FDE_STATE_ROOT"
    luks_uuid="$(blkid -s UUID -o value "$device" 2>/dev/null || true)"
    root_source="$(findmnt -no SOURCE / 2>/dev/null || true)"

    cat > "$FDE_STATE_FILE" <<EOF
FDE_DEVICE="$device"
FDE_MAP_NAME="$FDE_MAP_NAME"
FDE_REDUCE_SIZE="$FDE_REDUCE_SIZE"
FDE_TPM_PCRS="$FDE_TPM_PCRS"
FDE_ROOT_SOURCE="$root_source"
FDE_LUKS_UUID="$luks_uuid"
FDE_LAST_UPDATED_UTC="$(date -u +"%Y%m%dT%H%M%SZ")"
EOF
}

ensure_crypttab_entry() {
    local device="$1"
    local map_name="$2"
    local luks_uuid tmp backup

    luks_uuid="$(blkid -s UUID -o value "$device" 2>/dev/null || true)"
    if [ -z "$luks_uuid" ]; then
        echo "ERROR: Unable to determine UUID for $device."
        return 1
    fi

    tmp="$(mktemp)"
    if [ -f /etc/crypttab ]; then
        awk -v map="$map_name" '$1 != map { print }' /etc/crypttab > "$tmp"
        backup="/etc/crypttab.pre_fde.$(date -u +"%Y%m%dT%H%M%SZ")"
        cp /etc/crypttab "$backup"
    fi

    echo "${map_name} UUID=${luks_uuid} none luks,discard" >> "$tmp"
    mv "$tmp" /etc/crypttab
    echo "Updated /etc/crypttab with mapping '${map_name}' for UUID=${luks_uuid}."
}

update_root_fstab() {
    local device="$1"
    local map_name="$2"
    local map_path="/dev/mapper/${map_name}"
    local root_source device_uuid tmp backup
    local status=0

    [ -f /etc/fstab ] || {
        echo "WARN: /etc/fstab not found; skipping root entry update."
        return 0
    }

    root_source="$(findmnt -no SOURCE / 2>/dev/null || true)"
    device_uuid="$(blkid -s UUID -o value "$device" 2>/dev/null || true)"
    tmp="$(mktemp)"

    awk -v dev="$device" -v root_src="$root_source" -v uuid="$device_uuid" -v mapper="$map_path" '
        BEGIN { changed=0 }
        /^[[:space:]]*#/ { print; next }
        NF < 2 { print; next }
        {
            if ($2 == "/") {
                if ($1 == dev || $1 == root_src || (uuid != "" && $1 == "UUID=" uuid)) {
                    $1 = mapper
                    changed=1
                }
            }
            print
        }
        END { if (changed == 0) exit 42 }
    ' /etc/fstab > "$tmp" || status=$?

    if [ "$status" -eq 0 ]; then
        backup="/etc/fstab.pre_fde.$(date -u +"%Y%m%dT%H%M%SZ")"
        cp /etc/fstab "$backup"
        mv "$tmp" /etc/fstab
        echo "Updated /etc/fstab root entry to ${map_path}. Backup: ${backup}"
        return 0
    fi

    rm -f "$tmp"
    if [ "$status" -eq 42 ]; then
        echo "WARN: Could not automatically identify a '/' entry in /etc/fstab for ${device}."
        echo "WARN: Manually set root source to ${map_path} if your current boot source is ${device}."
        return 0
    fi

    echo "ERROR: Failed to update /etc/fstab."
    return 1
}

refresh_boot_artifacts() {
    echo "Refreshing boot artifacts..."

    if command -v update-initramfs >/dev/null 2>&1; then
        update-initramfs -u -k all
    else
        echo "WARN: update-initramfs not found."
    fi

    if command -v update-grub >/dev/null 2>&1; then
        update-grub
    elif command -v grub-mkconfig >/dev/null 2>&1 && [ -d /boot/grub ]; then
        grub-mkconfig -o /boot/grub/grub.cfg
    else
        echo "WARN: No GRUB refresh command found."
    fi
}

configure_boot_for_fde() {
    local device="$1"

    if ! cryptsetup isLuks "$device" 2>/dev/null; then
        echo "WARN: ${device} is not currently identified as LUKS. Skipping boot configuration update."
        return 1
    fi

    ensure_crypttab_entry "$device" "$FDE_MAP_NAME"
    update_root_fstab "$device" "$FDE_MAP_NAME"
    refresh_boot_artifacts
}

run_usb_key_create_mode() {
    local source="${1:-}"
    local ack=""
    local wipe=false
    local type=""
    local esp_part=""
    local root_part=""

    shift || true
    while [ $# -gt 0 ]; do
        case "$1" in
            --i-accept-risks)
                ack="--i-accept-risks"
                ;;
            --wipe)
                wipe=true
                ;;
            *)
                echo "ERROR: Unexpected argument for usb-key create: $1"
                exit 1
                ;;
        esac
        shift
    done

    require_root
    [ -n "$source" ] || {
        echo "ERROR: Missing USB source. Usage: $0 usb-key create <usb_device|partition|mountpoint> [--wipe] --i-accept-risks"
        exit 1
    }

    if ! risk_acknowledged "$ack"; then
        echo "ERROR: usb-key create requires explicit acknowledgement."
        echo "Pass --i-accept-risks OR set I_ACCEPT_THE_RISKS=true."
        exit 1
    fi

    install_fde_dependencies

    resolve_usb_device_details "$source" || exit 1

    if [ -b "$source" ]; then
        type="$(lsblk -ndo TYPE "$source" 2>/dev/null || true)"
        if [ "$type" = "disk" ]; then
            if [ "$wipe" != "true" ]; then
                echo "ERROR: USB disk provisioning is destructive. Re-run with --wipe and --i-accept-risks."
                exit 1
            fi
            partition_usb_disk "$source"
            esp_part="$USB_PARTITION"
            root_part="$USB_ROOT_PARTITION"
        elif [ "$type" = "part" ]; then
            resolve_usb_device_details "$source" || exit 1
            esp_part="$USB_PARTITION"
            root_part="$(lsblk -nrpo NAME,TYPE,PARTN "$USB_DISK" 2>/dev/null | awk '$2=="part" && $3=="2"{print $1; exit}')"
            [ -n "$root_part" ] || {
                echo "ERROR: USB root partition (part 2) not found on $USB_DISK. Re-run create with disk + --wipe."
                exit 1
            }
            format_usb_esp_if_needed "$esp_part"
            if [ -z "$(lsblk -ndo FSTYPE "$root_part" 2>/dev/null || true)" ]; then
                mkfs.ext4 -F -L "$USB_KEY_ROOT_LABEL" "$root_part"
            fi
        fi
    fi

    if [ -z "$esp_part" ] || [ -z "$root_part" ]; then
        echo "ERROR: Could not resolve USB ESP/root partitions."
        exit 1
    fi

    prepare_usb_offline_rootfs "$USB_DISK" "$esp_part" "$root_part"

    mount_usb_source "$esp_part"
    write_usb_unattended_config "$USB_MOUNTPOINT"
    sync
    cleanup_usb_mount

    cat <<EOF
USB temporary boot key prepared.
ESP: $esp_part
Root: $root_part
Config file:
  $USB_KEY_CONFIG_REL

Before unattended runs, an IT admin must edit the config on the USB key:
  ALLOW_UNATTENDED=true
  FDE_DEVICE=<target_device>
  FDE_PASSPHRASE=<passphrase>
EOF
}

run_usb_key_status_mode() {
    local source="${1:-}"
    local config_path allow_line

    [ -n "$source" ] || {
        echo "ERROR: Missing USB source. Usage: $0 usb-key status <usb_device|partition|mountpoint>"
        exit 1
    }

    mount_usb_source "$source"
    config_path="$USB_MOUNTPOINT/$USB_KEY_CONFIG_REL"

    echo "USB source: $source"
    [ -n "$USB_DISK" ] && echo "USB disk: $USB_DISK"
    [ -n "$USB_PARTITION" ] && echo "USB partition: $USB_PARTITION"
    echo "USB mountpoint: $USB_MOUNTPOINT"
    echo "Config path: $config_path"

    if [ -f "$config_path" ]; then
        allow_line="$(grep -E '^ALLOW_UNATTENDED=' "$config_path" 2>/dev/null || true)"
        echo "Config present: yes"
        echo "ALLOW_UNATTENDED: ${allow_line#ALLOW_UNATTENDED=}"
    else
        echo "Config present: no"
    fi

    cleanup_usb_mount
}

run_usb_key_arm_once_mode() {
    local source="${1:-}"
    local ack="${2:-}"

    [ -n "$source" ] || {
        echo "ERROR: Missing USB source. Usage: $0 usb-key arm-once <usb_device|partition|mountpoint> --i-accept-risks"
        exit 1
    }

    create_usb_boot_entry_once "$source" "$ack"
}

run_usb_key_mode() {
    local submode="${1:-}"
    shift || true

    case "$submode" in
        create)
            run_usb_key_create_mode "$@"
            ;;
        status)
            run_usb_key_status_mode "$@"
            ;;
        arm-once)
            run_usb_key_arm_once_mode "$@"
            ;;
        *)
            cat <<EOF
Usage:
  $0 usb-key create <usb_device|partition|mountpoint> [--wipe] --i-accept-risks
  $0 usb-key status <usb_device|partition|mountpoint>
  $0 usb-key arm-once <usb_device|partition|mountpoint> --i-accept-risks
EOF
            exit 1
            ;;
    esac
}

run_fscrypt_mode() {
    local target="${1:-}"
    [ -z "$target" ] && { echo "ERROR: Missing directory"; exit 1; }

    echo "=== fscrypt Directory Encryption ==="
    [ -d "$target" ] || { echo "ERROR: Target directory does not exist: $target"; exit 1; }
    command -v fscrypt >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq fscrypt

    if [ ! -f /etc/fscrypt.conf ]; then
        fscrypt setup --force --all-users
    fi

    local mountpoint
    mountpoint=$(df -P "$target" | tail -1 | awk '{print $6}')

    if [ -d "${mountpoint}/.fscrypt" ]; then
        echo "fscrypt already initialized on ${mountpoint}"
    else
        fscrypt setup "$mountpoint" --force --all-users
    fi

    if fscrypt status "$target" 2>/dev/null | grep -q "is encrypted with fscrypt"; then
        echo "Target is already encrypted: $target"
    elif [ "$FSCRYPT_AUTO_ENCRYPT" = "true" ]; then
        local keyfile=""
        local cleanup_keyfile=false

        if [ -n "$FSCRYPT_RAW_KEY_FILE" ]; then
            [ -f "$FSCRYPT_RAW_KEY_FILE" ] || { echo "ERROR: FSCRYPT_RAW_KEY_FILE does not exist: $FSCRYPT_RAW_KEY_FILE"; exit 1; }
            keyfile="$FSCRYPT_RAW_KEY_FILE"
        else
            [ -n "$FSCRYPT_PASSPHRASE" ] || {
                echo "ERROR: Set FSCRYPT_RAW_KEY_FILE (32-byte binary) or FSCRYPT_PASSPHRASE when FSCRYPT_AUTO_ENCRYPT=true."
                exit 1
            }
            keyfile=$(mktemp)
            cleanup_keyfile=true
            chmod 600 "$keyfile"
            printf '%s' "$FSCRYPT_PASSPHRASE" | openssl dgst -sha256 -binary > "$keyfile"
        fi

        fscrypt encrypt "$target" \
            --source=raw_key \
            --name="$FSCRYPT_PROTECTOR_NAME" \
            --key="$keyfile" \
            --quiet \
            --no-recovery

        if [ "$cleanup_keyfile" = true ]; then
            secure_delete_file "$keyfile"
        fi
    else
        echo "Ready: sudo fscrypt encrypt $target"
        echo "For unattended mode, set FSCRYPT_AUTO_ENCRYPT=true and FSCRYPT_RAW_KEY_FILE or FSCRYPT_PASSPHRASE."
    fi
}

run_reencrypt_mode() {
    local device="${1:-}"
    local passphrase="${2:-}"
    local ack="${3:-}"
    local mountpoints keyfile

    [ -z "$device" ] || [ -z "$passphrase" ] && { echo "ERROR: Missing device/passphrase"; exit 1; }
    require_root

    echo "WARNING: DANGEROUS OPERATION"
    mountpoints=$(findmnt -rn -S "$device" -o TARGET 2>/dev/null || true)
    if [ -n "$mountpoints" ]; then
        echo "ERROR: Target device is mounted and cannot be reencrypted offline: $device"
        echo "Mounted at: $mountpoints"
        echo "Run from an offline environment (live USB/recovery) to reencrypt this device."
        exit 1
    fi

    if ! risk_acknowledged "$ack"; then
        echo "ERROR: Reencrypt requires explicit non-interactive acknowledgement."
        echo "Pass --i-accept-risks as 3rd argument OR set I_ACCEPT_THE_RISKS=true."
        exit 1
    fi

    keyfile=$(mktemp)
    trap 'secure_delete_file "$keyfile"' EXIT
    chmod 600 "$keyfile"
    printf '%s' "$passphrase" > "$keyfile"

    cryptsetup reencrypt "$device" --new --reduce-device-size="$FDE_REDUCE_SIZE" --key-file "$keyfile" --batch-mode --verbose

    trap - EXIT
    secure_delete_file "$keyfile"
    echo "COMPLETE: Update /etc/crypttab and /etc/fstab before reboot"
}

run_encrypt_mode() {
    local device="${1:-}"
    local passphrase=""
    local ack=""
    local unattended=false
    local unattended_authorized=false
    local usb_key_source=""
    local use_usb_boot_once=false
    local mountpoints root_source keyfile

    [ -z "$device" ] && {
        echo "ERROR: Missing device. Usage: $0 encrypt <device> [passphrase] [--usb-key <path>] [--unattended] [--usb-boot-once] [--i-accept-risks]"
        exit 1
    }

    shift || true
    while [ $# -gt 0 ]; do
        case "$1" in
            --i-accept-risks)
                ack="--i-accept-risks"
                ;;
            --unattended)
                unattended=true
                ;;
            --usb-key=*)
                usb_key_source="${1#--usb-key=}"
                ;;
            --usb-key)
                shift
                [ -n "${1:-}" ] || { echo "ERROR: --usb-key requires a value."; exit 1; }
                usb_key_source="$1"
                ;;
            --usb-boot-once)
                use_usb_boot_once=true
                ;;
            *)
                if [ -z "$passphrase" ]; then
                    passphrase="$1"
                else
                    echo "ERROR: Unexpected argument: $1"
                    exit 1
                fi
                ;;
        esac
        shift
    done

    require_root
    [ -b "$device" ] || { echo "ERROR: Not a block device: $device"; exit 1; }

    root_source="$(findmnt -no SOURCE / 2>/dev/null || true)"

    if [ "$unattended" = "true" ]; then
        [ -n "$usb_key_source" ] || {
            echo "ERROR: --unattended requires --usb-key <path_to_usb_key>."
            exit 1
        }
        if load_unattended_config_from_usb "$usb_key_source" "$device"; then
            unattended_authorized=true
            if [ -z "$passphrase" ] && [ -n "${FDE_PASSPHRASE:-}" ]; then
                passphrase="$FDE_PASSPHRASE"
            fi
        else
            exit 1
        fi
    fi

    if ! risk_acknowledged "$ack"; then
        if [ "$unattended_authorized" != "true" ]; then
            echo "ERROR: encrypt requires explicit acknowledgement."
            echo "Pass --i-accept-risks OR set I_ACCEPT_THE_RISKS=true."
            echo "For unattended mode, provide --usb-key and set ALLOW_UNATTENDED=true in $USB_KEY_CONFIG_REL."
            exit 1
        fi
    fi

    if [ "$unattended" = "true" ] && [ -z "$passphrase" ]; then
        echo "ERROR: unattended mode requires FDE_PASSPHRASE in USB config or passphrase argument."
        exit 1
    fi

    if [ "$use_usb_boot_once" = "true" ]; then
        local boot_ack="$ack"
        [ -n "$usb_key_source" ] || {
            echo "ERROR: --usb-boot-once requires --usb-key <path_to_usb_key>."
            exit 1
        }
        if [ -z "$boot_ack" ] && [ "$unattended_authorized" = "true" ]; then
            boot_ack="--i-accept-risks"
        fi
        create_usb_boot_entry_once "$usb_key_source" "$boot_ack"
    fi

    if [ "$root_source" = "$device" ]; then
        echo "ERROR: Refusing online reencryption for mounted root device $device."
        echo "Use offline mode:"
        echo "  $0 usb-key create <usb-disk> --wipe --i-accept-risks"
        echo "  $0 encrypt-once $device --usb-key <usb-disk> --i-accept-risks"
        exit 1
    fi

    mountpoints=$(findmnt -rn -S "$device" -o TARGET 2>/dev/null || true)
    if [ -n "$mountpoints" ]; then
        echo "ERROR: Target device is mounted: $mountpoints"
        echo "Offline environment required. Unmount target and re-run."
        exit 1
    fi

    install_fde_dependencies

    if cryptsetup isLuks "$device" 2>/dev/null; then
        echo "Device already contains a LUKS header. Skipping encrypt command."
    else
        echo "Starting direct LUKS2 in-place reencryption on ${device}..."
        if [ -n "$passphrase" ]; then
            keyfile=$(mktemp)
            trap 'secure_delete_file "$keyfile"' EXIT
            chmod 600 "$keyfile"
            printf '%s' "$passphrase" > "$keyfile"

            cryptsetup reencrypt --encrypt --reduce-device-size "$FDE_REDUCE_SIZE" --key-file "$keyfile" --batch-mode --verbose "$device"

            trap - EXIT
            secure_delete_file "$keyfile"
        else
            echo "Interactive mode: cryptsetup will prompt for the new passphrase."
            cryptsetup reencrypt --encrypt --reduce-device-size "$FDE_REDUCE_SIZE" --verbose "$device"
        fi
    fi

    configure_boot_for_fde "$device"
    save_fde_state "$device"

    cat <<EOF
Encrypt phase complete.
Recommended next steps:
1) Reboot the system.
2) If reencryption was interrupted, resume:
   sudo bash "$SCRIPT_PATH" resume "$device" --i-accept-risks
3) Enroll TPM2 auto-unlock:
   sudo bash "$SCRIPT_PATH" tpm-enable "$device"
4) Verify state:
   sudo bash "$SCRIPT_PATH" verify "$device"
EOF
}

run_encrypt_once_mode() {
    local device="${1:-}"
    local usb_key_source=""
    local ack=""
    local no_reboot=false

    [ -n "$device" ] || {
        echo "ERROR: Missing device. Usage: $0 encrypt-once <device> --usb-key <path> --i-accept-risks [--no-reboot]"
        exit 1
    }
    shift || true

    while [ $# -gt 0 ]; do
        case "$1" in
            --usb-key=*)
                usb_key_source="${1#--usb-key=}"
                ;;
            --usb-key)
                shift
                [ -n "${1:-}" ] || { echo "ERROR: --usb-key requires a value."; exit 1; }
                usb_key_source="$1"
                ;;
            --i-accept-risks)
                ack="--i-accept-risks"
                ;;
            --no-reboot)
                no_reboot=true
                ;;
            *)
                echo "ERROR: Unexpected argument for encrypt-once: $1"
                exit 1
                ;;
        esac
        shift
    done

    require_root
    [ -b "$device" ] || { echo "ERROR: Not a block device: $device"; exit 1; }
    [ -n "$usb_key_source" ] || {
        echo "ERROR: encrypt-once requires --usb-key <path_to_usb_key>."
        exit 1
    }

    if ! risk_acknowledged "$ack"; then
        echo "ERROR: encrypt-once requires explicit acknowledgement."
        echo "Pass --i-accept-risks OR set I_ACCEPT_THE_RISKS=true."
        exit 1
    fi

    load_unattended_config_from_usb "$usb_key_source" "$device" || exit 1
    create_usb_boot_entry_once "$usb_key_source" "$ack" || exit 1

    cat <<EOF
One-time USB offline encryption run is armed.
- BootNext points to USB for the next boot only.
- USB booted environment will run $USB_OFFLINE_SERVICE using config at:
  /boot/efi/$USB_KEY_CONFIG_REL
- Normal boot order remains unchanged after that reboot.
EOF

    if [ "$no_reboot" = "true" ]; then
        echo "Reboot was skipped (--no-reboot). Reboot manually to start USB offline run."
    else
        echo "Rebooting now to start one-time USB offline encryption run..."
        systemctl reboot --message "DGX FDE one-time USB offline encryption run"
    fi
}

run_resume_mode() {
    local requested_device=""
    local ack=""
    local device

    while [ $# -gt 0 ]; do
        case "$1" in
            --i-accept-risks)
                ack="--i-accept-risks"
                ;;
            *)
                if [ -z "$requested_device" ]; then
                    requested_device="$1"
                else
                    echo "ERROR: Unexpected argument: $1"
                    exit 1
                fi
                ;;
        esac
        shift
    done

    require_root
    if ! risk_acknowledged "$ack"; then
        echo "ERROR: resume requires explicit acknowledgement."
        echo "Pass --i-accept-risks OR set I_ACCEPT_THE_RISKS=true."
        exit 1
    fi

    if ! device="$(resolve_fde_device "$requested_device")"; then
        echo "ERROR: Missing device and no saved workflow state."
        echo "Usage: $0 resume <device> --i-accept-risks"
        exit 1
    fi

    [ -b "$device" ] || { echo "ERROR: Not a block device: $device"; exit 1; }

    echo "Resuming in-place reencryption on ${device}..."
    cryptsetup reencrypt --resume-only --verbose "$device"

    configure_boot_for_fde "$device"
    save_fde_state "$device"

    echo "Resume phase complete."
}

run_verify_mode() {
    local requested_device="${1:-}"
    local device=""
    local root_source root_on_dmcrypt=false

    if device="$(resolve_fde_device "$requested_device" 2>/dev/null)"; then
        :
    else
        device=""
    fi

    root_source="$(findmnt -no SOURCE / 2>/dev/null || true)"
    if [[ "$root_source" =~ ^/dev/mapper/|^/dev/dm- ]]; then
        root_on_dmcrypt=true
    fi

    echo "=== FDE Verify ==="
    echo "Root source: ${root_source:-unknown}"
    echo "Root on dm-crypt: ${root_on_dmcrypt}"
    echo ""
    lsblk -f
    echo ""

    if [ -n "$device" ]; then
        echo "Target device: $device"
        if cryptsetup isLuks "$device" 2>/dev/null; then
            echo "LUKS header: present"
        else
            echo "LUKS header: not detected"
        fi

        if command -v systemd-cryptenroll >/dev/null 2>&1; then
            echo ""
            echo "TPM/LUKS token summary:"
            systemd-cryptenroll --dump "$device" 2>/dev/null | grep -Ei 'token|tpm2|slot' || true
        fi
    else
        echo "No target device provided and no workflow state found."
    fi

    echo ""
    if [ -e "/dev/mapper/${FDE_MAP_NAME}" ]; then
        cryptsetup status "$FDE_MAP_NAME" || true
    else
        echo "Mapping /dev/mapper/${FDE_MAP_NAME} not currently active."
    fi

    echo ""
    echo "Recommended journal check: journalctl -b | grep -Ei 'crypt|tpm'"
}

run_tpm_status_mode() {
    local requested_device="${1:-}"
    local device=""
    local tpm=false
    local fw_if=false
    local cryptenroll=false
    local token_state="null"

    if tpm_is_present; then
        tpm=true
    fi

    if collect_firmware_attr_candidates >/dev/null 2>&1 && [ -n "$(collect_firmware_attr_candidates | head -n1)" ]; then
        fw_if=true
    fi

    if command -v systemd-cryptenroll >/dev/null 2>&1; then
        cryptenroll=true
    fi

    if [ -n "$requested_device" ]; then
        device="$requested_device"
    elif device="$(resolve_fde_device "" 2>/dev/null)"; then
        :
    fi

    if [ -n "$device" ] && [ "$cryptenroll" = true ] && [ -b "$device" ] && cryptsetup isLuks "$device" 2>/dev/null; then
        if systemd-cryptenroll --dump "$device" 2>/dev/null | grep -qi 'tpm2'; then
            token_state=true
        else
            token_state=false
        fi
    fi

    echo "{\"tpm_present\":${tpm},\"firmware_attributes_interface\":${fw_if},\"systemd_cryptenroll_present\":${cryptenroll},\"device\":\"${device}\",\"tpm2_token_found\":${token_state}}"
}

run_tpm_enable_mode() {
    local device=""
    local pcrs="$FDE_TPM_PCRS"

    while [ $# -gt 0 ]; do
        case "$1" in
            --pcrs=*)
                pcrs="${1#--pcrs=}"
                ;;
            --pcrs)
                shift
                [ -n "${1:-}" ] || { echo "ERROR: --pcrs requires a value."; exit 1; }
                pcrs="$1"
                ;;
            *)
                if [ -z "$device" ]; then
                    device="$1"
                else
                    echo "ERROR: Unexpected argument: $1"
                    exit 1
                fi
                ;;
        esac
        shift
    done

    require_root

    if ! tpm_is_present; then
        echo "TPM is not visible. Attempting Linux firmware-attributes enablement..."
        if enable_tpm_via_firmware_attributes true; then
            echo "Attempted TPM enablement via firmware-attributes. Reboot required."
            return 0
        fi

        cat <<EOF
Could not enable TPM from Linux firmware interfaces.
Manual firmware step required:
1) sudo systemctl reboot --firmware-setup
2) UEFI -> Advanced -> Trusted Computing
3) Set Security Device Support = Enable
4) Save & Exit, reboot
EOF
        return 1
    fi

    if [ -z "$device" ]; then
        device="$(resolve_fde_device "" 2>/dev/null || true)"
    fi

    if [ -z "$device" ]; then
        echo "TPM is present. Provide a LUKS device to enroll (e.g. $0 tpm-enable /dev/nvme0n1p2)."
        return 0
    fi

    [ -b "$device" ] || { echo "ERROR: Not a block device: $device"; exit 1; }
    cryptsetup isLuks "$device" 2>/dev/null || { echo "ERROR: Device is not LUKS: $device"; exit 1; }

    if ! command -v systemd-cryptenroll >/dev/null 2>&1; then
        echo "ERROR: systemd-cryptenroll is not installed."
        exit 1
    fi

    echo "Enrolling TPM2 auto-unlock on ${device} (PCRs: ${pcrs})..."
    systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs="$pcrs" "$device"

    refresh_boot_artifacts
    save_fde_state "$device"

    echo "TPM enrollment complete."
}

run_luks_guide_mode() {
    cat <<EOF
=== LUKS2 + TPM2 Root Encryption Guide (Direct Reencrypt) ===
1) Probe current state:
   sudo bash "$SCRIPT_PATH" report

2) Prepare temporary USB boot key (for one-time boot path):
   sudo bash "$SCRIPT_PATH" usb-key create /dev/sdX --wipe --i-accept-risks
   Then edit USB config: $USB_KEY_CONFIG_REL

3) Start one-time USB boot + unattended encryption:
   sudo bash "$SCRIPT_PATH" encrypt-once /dev/nvme0n1p2 --usb-key /dev/sdX --i-accept-risks
   (System reboots once via USB path, runs offline encrypt on unmounted NVMe root, then returns to normal boot path)

4) Alternative interactive in-place encryption (no one-time USB boot):
   sudo bash "$SCRIPT_PATH" encrypt /dev/nvme0n1p2 --i-accept-risks
   Optional non-interactive passphrase:
   sudo bash "$SCRIPT_PATH" encrypt /dev/nvme0n1p2 '<passphrase>' --i-accept-risks

5) If interrupted, resume:
   sudo bash "$SCRIPT_PATH" resume /dev/nvme0n1p2 --i-accept-risks

6) Enroll TPM2 auto-unlock:
   sudo bash "$SCRIPT_PATH" tpm-enable /dev/nvme0n1p2

7) Verify final state:
   sudo bash "$SCRIPT_PATH" verify /dev/nvme0n1p2
EOF
}

run_fde_root_mode() {
    local submode="${1:-}"
    shift || true

    case "$submode" in
        encrypt)
            run_encrypt_mode "$@"
            ;;
        encrypt-once)
            run_encrypt_once_mode "$@"
            ;;
        resume)
            run_resume_mode "$@"
            ;;
        verify)
            run_verify_mode "$@"
            ;;
        usb-key)
            run_usb_key_mode "$@"
            ;;
        tpm-status)
            run_tpm_status_mode "$@"
            ;;
        tpm-enable)
            run_tpm_enable_mode "$@"
            ;;
        prepare|initramfs|finalize)
            cat <<EOF
ERROR: The legacy initramfs-based workflow is removed.
Use the direct workflow instead:
  $0 encrypt <device> [passphrase] --i-accept-risks
  $0 resume <device> --i-accept-risks
  $0 verify <device>
  $0 tpm-enable <device>
EOF
            exit 1
            ;;
        *)
            cat <<EOF
Usage:
  $0 fde-root encrypt <device> [passphrase] --i-accept-risks
  $0 fde-root encrypt-once <device> --usb-key <source> --i-accept-risks
  $0 fde-root resume <device> --i-accept-risks
  $0 fde-root verify <device>
  $0 fde-root usb-key <create|status|arm-once> ...
  $0 fde-root tpm-status [device]
  $0 fde-root tpm-enable [device] [--pcrs=0+7]
EOF
            exit 1
            ;;
    esac
}

case "$MODE" in
    report)
        exec bash "${SCRIPT_DIR}/encryption_at_rest.sh" --json
        ;;
    fscrypt)
        run_fscrypt_mode "${@:2}"
        ;;
    reencrypt)
        run_reencrypt_mode "${@:2}"
        ;;
    encrypt)
        run_encrypt_mode "${@:2}"
        ;;
    encrypt-once)
        run_encrypt_once_mode "${@:2}"
        ;;
    resume)
        run_resume_mode "${@:2}"
        ;;
    verify)
        run_verify_mode "${@:2}"
        ;;
    tpm-status)
        run_tpm_status_mode "${@:2}"
        ;;
    tpm-enable)
        run_tpm_enable_mode "${@:2}"
        ;;
    usb-key)
        run_usb_key_mode "${@:2}"
        ;;
    luks-guide)
        run_luks_guide_mode
        ;;
    fde-root)
        run_fde_root_mode "${@:2}"
        ;;
    *)
        cat <<EOF
Usage: $0 <mode> [...]
Modes:
  report
  fscrypt <directory>
  reencrypt <device> <passphrase> [--i-accept-risks]
  encrypt <device> [passphrase] [--usb-key <source>] [--unattended] [--usb-boot-once] [--i-accept-risks]
  encrypt-once <device> --usb-key <source> --i-accept-risks [--no-reboot]
  resume [device] [--i-accept-risks]
  verify [device]
  tpm-status [device]
  tpm-enable [device] [--pcrs=0+7]
  usb-key <create|status|arm-once> ...
  luks-guide
  fde-root <encrypt|encrypt-once|resume|verify|usb-key|tpm-status|tpm-enable>
EOF
        exit 1
        ;;
esac
