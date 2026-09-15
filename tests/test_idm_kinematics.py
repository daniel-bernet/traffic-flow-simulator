import unittest
import math
from src.vehicle import Vehicle, TrafficClass
from src.data_loader import LucerneDataLoader
from src.engine import TrafficSimulationEngine

class TestIDMKinematics(unittest.TestCase):
    def test_idm_acceleration_and_deceleration(self):
        v = Vehicle("test_1", TrafficClass.PERSONAL, "n1", "n2", ["edge_1"])
        edge_dict = {"length": 500.0, "maxspeed": 50.0, "geometry": [[47.0, 8.3], [47.01, 8.31]]}

        # Standstill initial state
        self.assertEqual(v.speed_ms, 0.0)

        # Free-flow update: should accelerate smoothly
        v.update_position(edge_dict, dt=1.0)
        self.assertGreater(v.speed_ms, 0.0)
        self.assertGreater(v.accel_ms2, 0.0)

        # High speed approaching red light or lead vehicle: should decelerate
        v.speed_ms = 14.0 # ~50 km/h
        v.update_position(edge_dict, dt=1.0, is_red_light=True)
        self.assertLess(v.accel_ms2, 0.0)

    def test_queue_offset_positioning(self):
        v1 = Vehicle("veh_1", TrafficClass.PERSONAL, "n1", "n2", ["edge_1"])
        v2 = Vehicle("veh_2", TrafficClass.PERSONAL, "n1", "n2", ["edge_1"])
        edge_dict = {"length": 100.0, "maxspeed": 50.0, "geometry": [[47.05, 8.31], [47.06, 8.32]]}

        v1.distance_on_edge = 50.0
        v2.distance_on_edge = 50.0

        v1.update_position(edge_dict, dt=0.0, queue_offset_m=0.0)
        v2.update_position(edge_dict, dt=0.0, queue_offset_m=12.0)

        # Visual lat/lon of v2 with queue offset should differ from v1
        self.assertNotEqual((v1.lat, v1.lon), (v2.lat, v2.lon))

    def test_engine_pause_controls(self):
        data_loader = LucerneDataLoader()
        data_loader.load_data(use_cache=True)
        engine = TrafficSimulationEngine(data_loader)

        engine.reset()
        engine.set_paused(True)
        t_before = engine.sim_time

        state = engine.tick(dt=1.0)
        self.assertTrue(state["is_paused"])
        self.assertEqual(engine.sim_time, t_before)

        engine.set_paused(False)
        state_2 = engine.tick(dt=1.0)
        self.assertFalse(state_2["is_paused"])
        self.assertGreater(engine.sim_time, t_before)

if __name__ == "__main__":
    unittest.main()
