from __future__ import annotations

import unittest

from burstwatch.tools import ToolDefinition, tool_statuses


class ToolTests(unittest.TestCase):
    def test_tool_statuses_report_missing_and_present_tools(self) -> None:
        statuses = tool_statuses(
            (
                ToolDefinition(
                    key="python",
                    label="Python",
                    command=("python3",),
                    purpose="test",
                    install_hint="install python",
                ),
                ToolDefinition(
                    key="missing",
                    label="Missing",
                    command=("burstwatch-definitely-missing-tool",),
                    purpose="test",
                    install_hint="install missing",
                ),
            )
        )

        by_key = {status.key: status for status in statuses}
        self.assertTrue(by_key["python"].available)
        self.assertFalse(by_key["missing"].available)
        self.assertEqual(by_key["missing"].install_hint, "install missing")
