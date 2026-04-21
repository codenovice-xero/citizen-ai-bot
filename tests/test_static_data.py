import unittest

from citizen_ai_bot.static_data import build_advice_plan


class StaticDataTests(unittest.TestCase):
    def test_build_advice_plan_uses_risk_tolerance(self) -> None:
        plan = build_advice_plan(money=100000, ship="Gladius", risk_tolerance="low")
        joined = " ".join(plan.bullets).lower()
        self.assertIn("risk profile", joined)
        self.assertIn("reserve credits", joined)


if __name__ == "__main__":
    unittest.main()
