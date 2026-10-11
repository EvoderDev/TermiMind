#!/usr/bin/env bash
# Copyright 2026 EvoderDev
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ==============================================================================
# TermiMind Bash Hook
# Intercepts non-zero command return codes and registers execution failure context
# ==============================================================================

termimind_bash_hook() {
    local last_status=$?
    
    # Do nothing if previous command succeeded
    if [ $last_status -eq 0 ]; then
        return 0
    fi

    # Extract last executed command from bash history
    local last_cmd
    last_cmd=$(HISTTIMEFORMAT= history 1 | sed -e 's/^[ ]*[0-9]*[ ]*//')
    last_cmd="${last_cmd#"${last_cmd%%[![:space:]]*}"}" # trim leading whitespace

    # Ignore empty commands or calls to termimind itself
    if [ -z "$last_cmd" ] || [[ "$last_cmd" =~ ^(tm|termimind) ]]; then
        return 0
    fi

    # Record the failure asynchronously or silently
    if command -v termimind >/dev/null 2>&1; then
        termimind record -c "$last_cmd" -x "$last_status" --cwd "$PWD" --shell "bash" >/dev/null 2>&1
        
        # If auto-trigger is enabled, launch interactive fix
        if [ "${TERMIMIND_AUTO_TRIGGER:-0}" = "1" ]; then
            termimind fix --from-hook
        fi
    fi
}

# Chain with existing PROMPT_COMMAND
if [[ "$PROMPT_COMMAND" != *"termimind_bash_hook"* ]]; then
    if [ -n "$PROMPT_COMMAND" ]; then
        PROMPT_COMMAND="termimind_bash_hook; $PROMPT_COMMAND"
    else
        PROMPT_COMMAND="termimind_bash_hook"
    fi
fi

# Ensure alias tm exists
if ! command -v tm >/dev/null 2>&1; then
    alias tm="termimind"
fi
