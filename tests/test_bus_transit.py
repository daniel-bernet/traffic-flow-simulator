import unittest
from src.data_loader import LucerneDataLoader
from src.od_generator import ODGenerator
from src.engine import TrafficSimulationEngine
from src.bus_transit import BusTransitManager

class TestBusTransit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_loader = LucerneDataLoader()
        cls.data_loader.load_data(use_cache=True)
        cls.engine = TrafficSimulationEngine(cls.data_loader)

    def test_bus_transit_lines_initialization(self):
        transit_mgr = self.engine.bus_transit_manager
        lines = transit_mgr.get_transit_state()
        self.assertGreater(len(lines), 0)
        line_1 = next((l for l in lines if l["id"] == "vbl_line_1"), None)
        self.assertIsNotNone(line_1)
        self.assertEqual(line_1["headway_min"], 6.0)

    def test_simulation_tick_emissions_and_bus_delays(self):
        # Run 20 ticks
        for _ in range(20):
            state = self.engine.tick(dt=1.0)

        state = self.engine.get_simulation_state()
        self.assertIn("co2_kg_hr", state)
        self.assertIn("fuel_l_hr", state)
        self.assertIn("bus_lines", state)
        self.assertGreaterEqual(len(state["bus_lines"]), 5)

if __name__ == "__main__":
    unittest.main()
