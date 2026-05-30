from __future__ import annotations

import unittest

from rich.console import Console

from burstwatch.cli import build_parser
from burstwatch.ui import render_header, render_menu_screen


class UiTests(unittest.TestCase):
    def test_parser_includes_menu_command(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()
        self.assertIn("menu", help_text)
        self.assertIn("capture", help_text)
        self.assertIn("dashboard", help_text)
        self.assertIn("tools", help_text)

    def test_render_header_wide_console(self) -> None:
        console = Console(width=100, record=True)
        console.print(render_header(console, subtitle="Passive RF workflow menu"))
        output = console.export_text()
        self.assertIn("Passive RF workflow menu", output)
        self.assertIn("______", output)

    def test_render_menu_screen_narrow_console(self) -> None:
        console = Console(width=60, record=True)
        actions = []
        screen = render_menu_screen(console, actions)
        console.print(screen)
        output = console.export_text()
        self.assertIn("Passive RF workflow menu", output)
        self.assertIn("New users: choose 1", output)
