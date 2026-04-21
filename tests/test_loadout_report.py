import unittest

from citizen_ai_bot.wiki_client import WikiClient


class WikiLoadoutParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = WikiClient()

    def tearDown(self) -> None:
        try:
            import asyncio

            asyncio.run(self.client.close())
        except RuntimeError:
            pass

    def test_builds_component_summary_from_vehicle_payload(self) -> None:
        vehicle = {
            "name": "Arrow",
            "type": "light_fighter",
            "manufacturer": {"name": "Anvil Aerospace"},
            "speed": {"scm": 229, "max": 1215},
            "health": 8580,
            "shield_hp": 3960,
            "crew": {"max": 1},
            "components": [
                {
                    "name": "CF-337 Panther",
                    "type": "weapon",
                    "component_size": 3,
                    "item_class": "military",
                    "component_class": "A",
                    "dps": 420,
                },
                {
                    "name": "CF-337 Panther",
                    "type": "weapon",
                    "component_size": 3,
                    "item_class": "military",
                    "component_class": "A",
                    "dps": 420,
                },
                {
                    "name": "MSD-322 Missile Rack",
                    "type": "missile_rack",
                    "component_size": 2,
                },
                {
                    "name": "FR-66",
                    "type": "shield_generator",
                    "component_size": 1,
                    "item_class": "military",
                    "component_class": "A",
                },
                {
                    "name": "JS-300",
                    "type": "power_plant",
                    "component_size": 1,
                    "item_class": "military",
                    "component_class": "A",
                },
                {
                    "name": "Snowpack",
                    "type": "cooler",
                    "component_size": 1,
                    "item_class": "competition",
                    "component_class": "A",
                },
            ],
            "ports": [
                {"type": "weapon", "size": 3},
                {"type": "weapon", "size": 3},
                {"type": "missile_rack", "size": 2},
                {"type": "shield_generator", "size": 1},
                {"type": "power_plant", "size": 1},
                {"type": "cooler", "size": 1},
            ],
        }

        report = self.client._extract_installed_components(vehicle)
        self.assertEqual(len(report["weapons"]), 2)
        total_dps, total_alpha = self.client._weapon_totals(report["weapons"])
        self.assertEqual(total_dps, 840)
        self.assertIsNone(total_alpha)

        summary = self.client._extract_hardpoint_summary(vehicle, report)
        joined = " ".join(summary)
        self.assertIn("Weapons", joined)
        self.assertIn("S3", joined)

    def test_role_extraction_prefers_readable_label(self) -> None:
        role = self.client._extract_role({"type": "light_fighter"})
        self.assertEqual(role, "Fighter")


if __name__ == "__main__":
    unittest.main()
