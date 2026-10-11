#!/usr/bin/env zsh
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
# TermiMind Zsh Hook
# Utilizes preexec and precmd hooks to capture terminal command failures
# ==============================================================================

autoload -Uz add-zsh-hook

_TERMIMIND_LAST_CMD=""

termimind_preexec() {
    _TERMIMIND_LAST_CMD="$1"
}

termimind_precmd() {
    local last_status=$?
    
    if [ $last_status -eq 0 ]; then
        _TERMIMIND_LAST_CMD=""
        return 0
    fi

    local cmd="$_TERMIMIND_LAST_CMD"
    _TERMIMIND_LAST_CMD=""

    if [ -z "$cmd" ]; then
        cmd=$(fc -ln -1 | sed 's/^[ ]*//')
    fi

    # Ignore empty commands or termimind itself
    if [ -z "$cmd" ] || [[ "$cmd" =~ ^(tm|termimind) ]]; then
        return 0
    fi

    if (( $+commands[termimind] )); then
        termimind record -c "$cmd" -x "$last_status" --cwd "$PWD" --shell "zsh" >/dev/null 2>&1
        
        if [ "${TERMIMIND_AUTO_TRIGGER:-0}" = "1" ]; then
            termimind fix --from-hook
        fi
    fi
}

add-zsh-hook preexec termimind_preexec
add-zsh-hook precmd termimind_precmd

if ! (( $+commands[tm] )); then
    alias tm="termimind"
fi
