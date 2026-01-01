# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for ChandlerScript rules format migration from list to dict format."""

from kaithem.src.chandler import rules_migration


class TestFormatDetection:
    """Test is_old_format() detection logic."""

    def test_detect_old_format_simple(self):
        """Test detection of simple old format."""
        old = [["cue.enter", [["goto", "=GROUP", "cue2"]]]]
        assert rules_migration.is_old_format(old) is True

    def test_detect_new_format(self):
        """Test detection of new dict format."""
        new = [
            {
                "event": "cue.enter",
                "actions": [
                    {"command": "goto", "group": "=GROUP", "cue": "cue2"}
                ],
            }
        ]
        assert rules_migration.is_old_format(new) is False

    def test_detect_empty_list(self):
        """Test that empty list returns False."""
        assert rules_migration.is_old_format([]) is False

    def test_detect_non_list(self):
        """Test that non-list returns False."""
        assert rules_migration.is_old_format("not a list") is False
        assert rules_migration.is_old_format(None) is False
        assert rules_migration.is_old_format({}) is False

    def test_detect_malformed_old(self):
        """Test malformed old format returns False (treat as new)."""
        # Wrong structure - should return False to treat as new
        malformed = [["cue.enter", {"bad": "structure"}]]
        assert rules_migration.is_old_format(malformed) is False


class TestMigration:
    """Test migrate_rules_to_new_format() function."""

    def test_migrate_simple_rule(self):
        """Test basic migration of single rule with single action."""
        old = [["cue.enter", [["goto", "=GROUP", "cue2"]]]]
        new = rules_migration.migrate_rules_to_new_format(old)

        assert len(new) == 1
        assert new[0]["event"] == "cue.enter"
        assert len(new[0]["actions"]) == 1
        assert new[0]["actions"][0]["command"] == "goto"

    def test_migrate_multiple_actions(self):
        """Test migration of rule with multiple actions (pipeline)."""
        old = [
            [
                "cue.enter",
                [["goto", "=GROUP", "cue2"], ["set_alpha", "=GROUP", "0.5"]],
            ]
        ]
        new = rules_migration.migrate_rules_to_new_format(old)

        assert len(new) == 1
        assert len(new[0]["actions"]) == 2
        assert new[0]["actions"][0]["command"] == "goto"
        assert new[0]["actions"][1]["command"] == "set_alpha"

    def test_migrate_multiple_rules(self):
        """Test migration of multiple rules on same event."""
        old = [
            ["cue.enter", [["goto", "group1", "cue2"]]],
            ["cue.enter", [["set_alpha", "=GROUP", "0.76"]]],
        ]
        new = rules_migration.migrate_rules_to_new_format(old)

        assert len(new) == 2
        assert new[0]["event"] == "cue.enter"
        assert new[1]["event"] == "cue.enter"
        assert new[0]["actions"][0]["command"] == "goto"
        assert new[1]["actions"][0]["command"] == "set_alpha"

    def test_migrate_midi_event(self):
        """Test migration of MIDI event (from actual test case)."""
        old = [["midi.note:1.C5", [["goto", "=GROUP", "cue2"]]]]
        new = rules_migration.migrate_rules_to_new_format(old)

        assert new[0]["event"] == "midi.note:1.C5"
        assert new[0]["actions"][0]["command"] == "goto"

    def test_migrate_expression_event(self):
        """Test migration of expression-based event."""
        old = [["=tv('/logic_test_tag')", [["goto", "recv_group", "cue2"]]]]
        new = rules_migration.migrate_rules_to_new_format(old)

        assert new[0]["event"] == "=tv('/logic_test_tag')"

    def test_migrate_pass_command(self):
        """Test migration of pass command with no args."""
        old = [["cue.enter", [["pass"]]]]
        new = rules_migration.migrate_rules_to_new_format(old)

        assert new[0]["actions"][0]["command"] == "pass"
        # pass should have no other keys except command

    def test_migrate_set_command(self):
        """Test migration of set command."""
        old = [["cue.enter", [["set", "var_name", "value"]]]]
        new = rules_migration.migrate_rules_to_new_format(old)

        action = new[0]["actions"][0]
        assert action["command"] == "set"
        # Args should be mapped to parameter names
        assert action.get("variable") == "var_name"
        assert action.get("value") == "value"

    def test_migrate_empty_rules(self):
        """Test migration of empty rules list."""
        old = []
        new = rules_migration.migrate_rules_to_new_format(old)
        assert new == []

    def test_migrate_preserves_special_values(self):
        """Test that special values like =expressions are preserved."""
        old = [["cue.enter", [["goto", "=GROUP", "=var_name"]]]]
        new = rules_migration.migrate_rules_to_new_format(old)

        action = new[0]["actions"][0]
        assert action.get("group") == "=GROUP"
        assert action.get("cue") == "=var_name"


class TestArgNameExtraction:
    """Test get_arg_names_for_command() function."""

    def test_special_commands(self):
        """Test that special commands return hardcoded arg names."""
        assert rules_migration.get_arg_names_for_command("set") == [
            "variable",
            "value",
        ]
        assert rules_migration.get_arg_names_for_command("pass") == []
        assert rules_migration.get_arg_names_for_command("maybe") == ["chance"]

    def test_unknown_command(self):
        """Test that unknown command returns empty list."""
        result = rules_migration.get_arg_names_for_command(
            "nonexistent_command_xyz"
        )
        assert result == []


class TestRoundTrip:
    """Test round-trip compatibility."""

    def test_old_format_becomes_dict_format(self):
        """Test that old format input results in dict format output."""
        old = [["cue.enter", [["pass"]]]]
        new = rules_migration.migrate_rules_to_new_format(old)

        # Check it's a dict format
        assert isinstance(new[0], dict)
        assert "event" in new[0]
        assert "actions" in new[0]
        assert isinstance(new[0]["actions"], list)
        assert isinstance(new[0]["actions"][0], dict)
        assert "command" in new[0]["actions"][0]
