import unittest
from src.data_loader import LucerneDataLoader
from src.od_generator import ODGenerator
from src.traffic_signals import TrafficSignalManager, TrafficSignal
from src.engine import TrafficSimulationEngine

class TestTrafficSignals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_loader = LucerneDataLoader()
        cls.data_loader.load_data(use_cache=True)
        cls.engine = TrafficSimulationEngine(cls.data_loader)

    def test_traffic_signal_initialization(self):
        sig_mgr = self.engine.signal_manager
        signals = sig_mgr.get_signals_state()
        self.assertGreater(len(signals), 0)
        
        # Verify major Lucerne signals exist
        pilatus_sig = next((s for s in signals if "Pilatusplatz" in s["name"]), None)
        self.assertIsNotNone(pilatus_sig)

        # Cycle length follows the number of approaches (90 s for 4+, 75 s for 3, else 60 s).
        # The approach count depends on the OSM snapshot, so assert the rule, not a fixed value.
        approaches = len(pilatus_sig["phase_a_edges"]) + len(pilatus_sig["phase_b_edges"])
        expected = 90.0 if approaches >= 4 else 75.0 if approaches >= 3 else 60.0
        self.assertEqual(pilatus_sig["cycle_time_sec"], expected)

    def test_signal_phase_tick_and_red_check(self):
        # Own manager: this test mutates signal timings and must not leak into sibling tests.
        sig_mgr = TrafficSignalManager(self.data_loader)
        signals = sig_mgr.get_signals_state()
        test_sig = signals[0]
        
        # Test split update
        updated = sig_mgr.update_signal_split(test_sig["id"], 0.60, 80.0)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["green_split"], 0.60)
        self.assertEqual(updated["cycle_time_sec"], 80.0)

        # Tick 20 seconds
        sig_mgr.tick(20.0)
        self.assertIn(sig_mgr.signals[test_sig["id"]].phase, ["PHASE_A_GREEN", "PHASE_A_YELLOW", "PHASE_B_GREEN", "PHASE_B_YELLOW"])

    def test_gravity_model_od_sampling(self):
        od_gen = self.engine.od_generator
        orig_node = list(self.data_loader.nodes_dict.keys())[0]
        cand_nodes = list(self.data_loader.nodes_dict.keys())[1:10]
        sampled_dest = od_gen._sample_gravity_destination(orig_node, cand_nodes)
        self.assertIn(sampled_dest, cand_nodes)

if __name__ == "__main__":
    unittest.main()
