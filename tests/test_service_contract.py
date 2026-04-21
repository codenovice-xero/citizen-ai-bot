import unittest

from citizen_ai_bot.services import StarCitizenService


class DummyClient:
    async def ping(self):
        return True

    async def close(self):
        return None


class ServiceContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = StarCitizenService(client=DummyClient())

    async def asyncTearDown(self):
        await self.service.close()

    async def test_health_status_shape(self):
        status = await self.service.health_status()
        self.assertIn("uex", status)
        self.assertIn("wiki", status)

    def test_advice_plan(self):
        plan = self.service.advice_for_player(500000, "Arrow", "medium")
        self.assertTrue(plan.title)
        self.assertTrue(plan.bullets)

    def test_mission_plan(self):
        plan = self.service.mission_plan("bounty")
        self.assertTrue(plan.summary)
