#!/bin/bash

# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

export LOGFILE=/var/log/dgx-dashboard-reboot.log
echo "Starting dgx-dashboard-reboot.sh..."|/usr/bin/tee -a ${LOGFILE}

# Sleep 10s to allow for reboot request to be communicated to any event subscribers
sleep 10

echo "Rebooting..."|/usr/bin/tee -a ${LOGFILE}
/usr/bin/systemctl reboot
