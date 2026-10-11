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
# TermiMind PowerShell Hook
# Hooks into the PowerShell prompt lifecycle to capture errors and failed commands
# ==============================================================================

if (-not (Get-Command termimind -ErrorAction SilentlyContinue)) {
    # If termimind is not directly in PATH as an exe/script, look for python entry
    function global:termimind {
        python -m termimind.cli @args
    }
}

if (-not (Get-Alias tm -ErrorAction SilentlyContinue)) {
    Set-Alias -Name tm -Value termimind -Scope Global
}

# Preserve original prompt implementation
if (Test-Path Function:\prompt) {
    $script:OriginalPrompt = $Function:prompt
} else {
    $script:OriginalPrompt = { "PS $($executionContext.SessionState.Path.CurrentLocation)$('>' * ($nestedPromptLevel + 1)) " }
}

function global:prompt {
    $lastExit = $global:LASTEXITCODE
    $lastSuccess = $global:?

    # Only process if a failure actually occurred
    if (-not $lastSuccess -or ($null -ne $lastExit -and $lastExit -ne 0)) {
        try {
            $lastCmd = ""
            $history = Get-History -Count 1 -ErrorAction SilentlyContinue
            if ($history) {
                $lastCmd = $history.CommandLine.Trim()
            }

            # Filter out calls to termimind itself or empty commands
            if ($lastCmd -and -not ($lastCmd -match '^(tm|termimind)')) {
                $errMsg = ""
                if ($global:Error -and $global:Error.Count -gt 0) {
                    $errMsg = $global:Error[0].ToString()
                }

                $exitCode = if ($null -ne $lastExit -and $lastExit -ne 0) { $lastExit } else { 1 }
                $currentPwd = (Get-Location).Path

                # Record failure quietly
                & termimind record -c "$lastCmd" -x $exitCode -e "$errMsg" --cwd "$currentPwd" --shell "powershell" 2>$null

                # If auto-trigger environment or setting is active, trigger fix
                if ($env:TERMIMIND_AUTO_TRIGGER -eq "1") {
                    & termimind fix --from-hook
                }
            }
        } catch {
            # Silently handle any hook failure to avoid breaking user prompt
        }
    }

    # Execute original prompt
    & $script:OriginalPrompt
}
