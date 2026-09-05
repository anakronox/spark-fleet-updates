#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
################################################################################
# Root install.sh - Install all DGX Spark Management tools
#
# Usage: bash install.sh   (or ./install.sh from repo root)
# Runs reinstall_all.sh to install common module and all production tools.
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/reinstall_all.sh"
