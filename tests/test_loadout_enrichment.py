import unittest

from citizen_ai_bot.models import LoadoutSuggestion
from citizen_ai_bot.static_data import _clean_component_name, _enrich_loadout


class LoadoutEnrichmentTests(unittest.TestCase):
    def test_clean_component_name_omits_internal_placeholders(self) -> None:
        hp = {
            "component_name": "Weapons",
            "component_class": "RSIWeapon",
            "component_type": "weapons",
            "size": "4",
            "manufacturer": "TBD",
        }
        self.assertEqual(_clean_component_name(hp), "Size 4")

    def test_enrich_loadout_preserves_curated_role(self) -> None:
        base = LoadoutSuggestion(
            ship_name="Shiv",
            role="Light Fighter / Hit-and-Run",
            weapons=["x"],
            shields=["y"],
            power=["z"],
            coolers=["w"],
            notes=["n"],
        )
        wiki_data = {
            "ship_name": "Shiv",
            "hardpoints": {
                "weapons": [{"size": "4", "component_name": "Weapons", "component_class": "RSIWeapon", "manufacturer": "TBD"}],
                "missiles": [{"size": "3", "component_name": "Missiles", "component_class": "RSIWeapon", "manufacturer": "TBD"}],
                "shields": [{"size": "M", "component_name": "Shield Generators", "component_class": "RSIModular", "manufacturer": "TBD"}],
                "power": [{"size": "M", "component_name": "Power Plants", "component_class": "RSIModular", "manufacturer": "TBD"}],
                "coolers": [{"size": "M", "component_name": "Coolers", "component_class": "RSIModular", "manufacturer": "TBD"}],
            },
            "performance": {"scm_speed": 219, "max_speed": 1175, "hull_hp": 34300, "cargo_scu": 32, "max_crew": 2, "shield_hp": 9000},
        }
        enriched = _enrich_loadout(base, wiki_data, preserve_role=True)
        self.assertEqual(enriched.role, "Light Fighter / Hit-and-Run")
        joined = " ".join(enriched.weapons + enriched.shields + enriched.power + enriched.coolers + enriched.notes)
        self.assertNotIn("RSIWeapon", joined)
        self.assertNotIn("RSIModular", joined)
        self.assertNotIn("TBD", joined)


if __name__ == "__main__":
    unittest.main()
