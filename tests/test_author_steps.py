"""Confirm the guided PowerShell wrapper preserves the original step mapping."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OriginalProStageTests(unittest.TestCase):
    def test_original_stage_numbers_and_offer_ids(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        for step, plan, offer in (
            (2, "pro12", "12months-eft"),
            (3, "pro6", "6months-eft"),
            (4, "pro6b", "6months-eft-2"),
            (5, "pro6c", "6months-eft-ss-2026"),
        ):
            self.assertIn('Number = %d;' % step, ps)
            self.assertIn('Plan = "%s"; Offer = "%s"' % (plan, offer), ps)

    def test_single_step_five_requires_explicit_cli_approval(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        self.assertNotIn('("RUN {0}" -f $stage.Number)', ps)
        self.assertIn('if ($stage.Number -eq 5 -and ($AllStages -or $env:EPLUS_TUI -ne "1"))', ps)
        self.assertIn('if ($AllStages) {\n            if (-not (Confirm-Exact "Only if you verified', ps)
        self.assertIn('Read-Host "     Choose 1/2/0"', ps)
        self.assertIn('Write-Host "     [1] Continue"', ps)
        self.assertIn('Write-Host "     [2] Skip / End run"', ps)
        self.assertIn('if ($AllStages) {\n                if (-not (Confirm-Exact "Confirm Google Play shows NO ACTIVE', ps)

    def test_original_author_and_maintainer_attribution(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        credits = (ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8")
        self.assertIn("(CONTRIBUTORS.md)", readme)
        self.assertIn("github.com/gylive/google-ultra", credits)
        self.assertIn("David Nguyen (@hoangsvit)", credits)
        self.assertIn("Original: @gylive", ps)
        self.assertIn("Maintained: @hoangsvit", ps)
        self.assertIn("Copyright (c) 2026 gylive", notice)
        self.assertIn("MIT License", notice)

    def test_compact_terminal_defaults_and_detailed_mode(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('$PSBoundParameters.ContainsKey("Debug")', ps)
        self.assertIn('if ($ShowDebug)', ps)
        self.assertNotIn('[switch]$Debug', ps)
        self.assertNotIn('[switch]$Detailed', ps)
        self.assertIn('if ($script:RunLog)', ps)
        self.assertIn('Show-Status "Checkout" "Submitted; check Google Play"', ps)
        helper = (ROOT / "scripts/user-errors.ps1").read_text(encoding="utf-8")
        self.assertIn("payment_security_blocked", helper)
        self.assertIn('if ($ShowDebug -or ($Step -eq 1 -and -not $AllStages))', ps)
        self.assertIn("Run-Command $Python $args", ps)
        # Advanced CLI examples live in the full usage guide, not the short overview.
        usage = (ROOT / "docs/USAGE.md").read_text(encoding="utf-8")
        self.assertIn("-Debug", usage)
        self.assertIn("(docs/USAGE.md)", readme)
        self.assertIn("https://eplus.dev", ps)
        credits = (ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8")
        self.assertIn("(CONTRIBUTORS.md)", readme)
        self.assertIn("https://eplus.dev", credits)

    def test_friendly_user_error_mapping_preserves_checkout_safety(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        self.assertIn('scripts/user-errors.ps1', ps)
        self.assertIn('Show-UserIssue -Code $issueCode', ps)
        self.assertIn('Show-UserIssue -Code "offer_not_available"', ps)
        self.assertIn('Get-FailureCode -ErrorMessage $rawError', ps)
        self.assertIn('if ($report.status -eq "checkout_requested")', ps)
        self.assertIn('break', ps)

    def test_mumu_recovery_filter_accepts_configuration_hint(self):
        import re
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        pattern = re.search(r"-match '([^']*MUMU_RECOVERY:[^']*)'", ps).group(1)
        self.assertIsNotNone(re.fullmatch(pattern, "MUMU_RECOVERY:MuMu Manager not found. Install MuMu or configure MUMU_DIR."))
        self.assertIsNone(re.fullmatch(pattern, "MUMU_RECOVERY:private@example.com"))
        self.assertIsNone(re.fullmatch(pattern, "MUMU_RECOVERY:127.0.0.1:16384"))
        self.assertIsNone(re.fullmatch(pattern, "Untrusted MUMU_DIR message"))

    def test_reconnect_keeps_exact_selected_transport(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        self.assertIn('$Serial -and $online -cnotcontains $Serial -and $Serial -match', ps)
        self.assertIn('$null = & $Adb connect $Serial 2>$null', ps)
        self.assertIn('if ($online -cnotcontains $Serial)', ps)
        self.assertIn('if ($online.Count -eq 0 -and -not $Serial)', ps)

    def test_no_checkout_by_default(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        self.assertIn("[int]$Step = 1", ps)
        self.assertIn('[switch]$Cli', ps)
        self.assertIn('$useTui = $Tui -or', ps)
        self.assertIn('$PSBoundParameters.ContainsKey("Step")', ps)
        self.assertIn('if ($ListOnly -or ($Step -eq 1 -and -not $AllStages))', ps)

    def test_uses_verified_account_from_step_one_if_preflight_misses_it(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        ultra = (ROOT / "ultra0.py").read_text(encoding="utf-8")
        self.assertIn('rec["detected_play_account"] = cur or ""', ultra)
        self.assertIn('Read-PythonReport "current"', ps)
        self.assertIn('if (-not $playAccount -and $listedAccount)', ps)
        self.assertIn('$playAccount = $listedAccount', ps)
        self.assertIn('if ($playAccount -and $listedAccount -and $playAccount -cne $listedAccount)', ps)

    def test_diagnostic_does_not_assign_to_powershell_automatic_pid(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        self.assertIn("$googleOnePid =", ps)
        self.assertIn("if ($googleOnePid -match", ps)
        import re
        self.assertIsNone(re.search(r"\$pid\s*=", ps, flags=re.IGNORECASE))

    def test_all_stages_includes_optional_step_five_and_rejects_force(self):
        ps = (ROOT / "run-all.ps1").read_text(encoding="utf-8")
        self.assertIn('$_.Number -ge $StartStep -and $_.Number -le 5', ps)
        self.assertIn('[switch]$Force', ps)
        self.assertIn('[int]$StartStep = 2', ps)
        self.assertIn('"-StartStep requires -AllStages."', ps)
        self.assertIn('Confirm-Exact "Confirm Google Play shows NO ACTIVE Google One subscription', ps)
        self.assertIn('if ($AllStages)', ps)
        self.assertIn('Confirm-Exact "Confirm Google Play shows an ACTIVE Google AI Pro subscription', ps)
        self.assertNotIn('$args += "--force"', ps)
        self.assertNotIn('$Email = "current@device"', ps)
        self.assertIn('Stop-Workflow "-Force is not supported for paid stages.', ps)
        self.assertLess(ps.index('if (-not $playAccount) {', ps.index('# Reuse the selected Play account')), ps.index('if ($Force) {'))
        self.assertLess(ps.index('if ($playAccount -cne $Email)'), ps.index('if ($Force) {'))
        self.assertLess(ps.index('if ($Force) {'), ps.index('Run-Command $Python $args'))
        self.assertIn('if (-not $Email -and $playAccount)', ps)
        self.assertIn('if ($report.status -eq "checkout_requested")', ps)
        self.assertNotIn('"launched", "subscribed"', ps)
        self.assertIn('Confirm-Exact "Only if you verified the active plan', ps)
        self.assertIn('original stages starting at Step {0}, including optional Step 5?', ps)
        self.assertIn('if ($stage.Number -eq 5 -and ($AllStages -or $env:EPLUS_TUI -ne "1"))', ps)
        self.assertIn('if (-not $AllStages) {', ps)
        self.assertIn('if ($AllStages) {', ps)
        self.assertIn('Single-step mode: the selected step may open Google Play checkout', ps)
        self.assertIn('Single step finished. Review the actual subscription', ps)
        self.assertIn('Cannot identify the active Google Play account.', ps)
        self.assertIn('Cannot select a single Android device automatically.', ps)
        self.assertNotIn('"I ACCEPT {0}"', ps)


if __name__ == "__main__":
    unittest.main()
