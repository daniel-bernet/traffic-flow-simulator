import unittest
from src.data_loader import LucerneDataLoader
from src.engine import TrafficSimulationEngine

class TestSimulationEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_loader = LucerneDataLoader()
        cls.data_loader.load_data(use_cache=True)
        cls.engine = TrafficSimulationEngine(cls.data_loader)

    def test_engine_initialization(self):
        self.assertGreater(len(self.engine.edges_dict), 100)
        self.assertEqual(len(self.engine.active_vehicles), 0)

    def test_simulation_ticks(self):
        self.engine.reset()
        self.engine.set_parameters({"spawn_rate": 5.0, "sim_speed_multiplier": 1.0})
        
        # Run 50 simulation ticks
        for _ in range(50):
            state = self.engine.tick(dt=1.0)
            self.assertIn("active_vehicles_count", state)
            self.assertIn("sim_time", state)
            self.assertIn("vehicles", state)
            self.assertIn("top_chokepoints", state)

        self.assertGreater(self.engine.vehicle_id_counter, 0)
        self.assertGreater(len(self.engine.active_vehicles), 0)
        print(f"Simulation test passed! Active vehicles: {len(self.engine.active_vehicles)}, Sim Time: {self.engine.sim_time}s")

    def test_road_blocking_and_rerouting(self):
        self.engine.reset()
        sample_edge_id = list(self.engine.edges_dict.keys())[0]
        
        # Toggle block
        self.engine.toggle_blocked_edge(sample_edge_id)
        self.assertIn(sample_edge_id, self.engine.blocked_edges)
        
        # Toggle unblock
        self.engine.toggle_blocked_edge(sample_edge_id)
        self.assertNotIn(sample_edge_id, self.engine.blocked_edges)
        print(f"Road blocking test passed for edge {sample_edge_id}!")

if __name__ == "__main__":
    unittest.main()
