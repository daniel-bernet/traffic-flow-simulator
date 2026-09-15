import unittest
from src.parking import ParkingManager
from src.vehicle import Vehicle, TrafficClass
from src.data_loader import LucerneDataLoader

class TestParkingAndMultilane(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_loader = LucerneDataLoader()
        cls.data_loader.load_data(use_cache=True)
        cls.parking_mgr = ParkingManager(cls.data_loader)

    def test_parking_garages_initialization(self):
        self.assertGreater(len(self.parking_mgr.garages), 5)
        bahnhof_g = self.parking_mgr.garages.get("park_bahnhof")
        self.assertIsNotNone(bahnhof_g)
        self.assertEqual(bahnhof_g.capacity, 1100)
        self.assertGreater(bahnhof_g.occupied, 0)

    def test_parking_arrival_and_dwell(self):
        bahnhof_g = self.parking_mgr.garages.get("park_bahnhof")
        node_id = bahnhof_g.node_id
        
        # Vehicle arrives at parking garage node
        handled = self.parking_mgr.handle_vehicle_arrival("test_car_101", node_id)
        self.assertTrue(handled)
        self.assertIn("test_car_101", bahnhof_g.entry_queue)

        # Advance parking manager tick
        self.parking_mgr.tick(3.0)
        self.assertNotIn("test_car_101", bahnhof_g.entry_queue)
        self.assertIn("test_car_101", bahnhof_g.parked_vehicles)

    def test_multilane_offset_rendering(self):
        v0 = Vehicle("veh_lane_0", TrafficClass.PERSONAL, "n1", "n2", ["edge_m"])
        v1 = Vehicle("veh_lane_1", TrafficClass.PERSONAL, "n1", "n2", ["edge_m"])

        v0.lane_index = 0
        v1.lane_index = 1

        multilane_edge = {
            "length": 100.0,
            "maxspeed": 50.0,
            "lanes": 2,
            "geometry": [[47.050, 8.310], [47.051, 8.311]]
        }

        v0.update_position(multilane_edge, dt=0.0)
        v1.update_position(multilane_edge, dt=0.0)

        # Visual lat/lon of v0 and v1 across 2 lanes should differ due to lateral offset
        self.assertNotEqual((v0.lat, v0.lon), (v1.lat, v1.lon))

if __name__ == "__main__":
    unittest.main()
