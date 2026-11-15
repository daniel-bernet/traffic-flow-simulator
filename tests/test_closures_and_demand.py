"""Regression tests for the road-closure, demand-accounting and lane-assignment fixes.

Each test here pins down a behaviour that was previously wrong; see the docstrings for what the
old behaviour was.
"""
import unittest

from src.data_loader import LucerneDataLoader
from src.engine import TrafficSimulationEngine
from src.vehicle import Vehicle, TrafficClass


class TestClosuresAndDemand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_loader = LucerneDataLoader()
        cls.data_loader.load_data(use_cache=True)

    def setUp(self):
        self.engine = TrafficSimulationEngine(self.data_loader)
        self.engine.reset(clear_closures=True)

    # ---------- road closures ----------

    def test_new_vehicles_do_not_route_through_a_closed_edge(self):
        """Previously get_route_edges() was called without the blocked set (and hit a stale
        cache), so vehicles spawned after a closure planned straight through it."""
        self.engine.set_parameters({"spawn_rate": 8.0})
        for _ in range(40):
            self.engine.tick(dt=1.0)

        busiest = max(self.engine.edge_stats.items(), key=lambda kv: kv[1]["vehicle_count"])[0]
        self.engine.toggle_blocked_edge(busiest)

        # Clear the field so only vehicles created after the closure remain.
        self.engine.active_vehicles.clear()
        for _ in range(40):
            self.engine.tick(dt=1.0)

        planning_through = [
            v.id for v in self.engine.active_vehicles.values()
            if busiest in v.route_edges[v.current_edge_idx:]
        ]
        self.assertEqual(planning_through, [],
                         f"{len(planning_through)} vehicles planned through closed edge {busiest}")

    def test_vehicles_never_occupy_a_closed_edge_they_did_not_start_on(self):
        """Previously a vehicle whose current edge was blocked was advanced straight to the next
        edge in its route, i.e. it teleported across the closure."""
        self.engine.set_parameters({"spawn_rate": 8.0})
        for _ in range(40):
            self.engine.tick(dt=1.0)

        busiest = max(self.engine.edge_stats.items(), key=lambda kv: kv[1]["vehicle_count"])[0]
        self.engine.toggle_blocked_edge(busiest)
        self.engine.active_vehicles.clear()

        for _ in range(60):
            self.engine.tick(dt=1.0)
            on_closed = [v for v in self.engine.active_vehicles.values()
                         if v.current_edge_id == busiest]
            self.assertEqual(on_closed, [], "a vehicle entered a closed edge")

    def test_rerouting_does_not_send_a_vehicle_back_to_its_origin(self):
        """_reroute_affected_vehicles() used to replan from veh.origin_id and reset
        current_edge_idx to 0, teleporting the vehicle back to the start of its trip."""
        self.engine.set_parameters({"spawn_rate": 8.0})
        for _ in range(60):
            self.engine.tick(dt=1.0)

        # Pick a vehicle that is some way into a multi-edge route.
        veh = next((v for v in self.engine.active_vehicles.values()
                    if v.current_edge_idx >= 2 and len(v.route_edges) > v.current_edge_idx + 2), None)
        if veh is None:
            self.skipTest("no vehicle far enough into a route in this run")

        edge_ahead = veh.route_edges[veh.current_edge_idx + 1]
        edge_now = veh.current_edge_id
        dist_now = veh.distance_on_edge

        self.engine.toggle_blocked_edge(edge_ahead)

        if veh.id not in self.engine.active_vehicles:
            self.skipTest("vehicle was stranded by the closure")
        # It must still be on the same physical edge, at the same position.
        self.assertEqual(veh.current_edge_id, edge_now)
        self.assertAlmostEqual(veh.distance_on_edge, dist_now, places=6)

    def test_reset_preserves_closures_unless_asked(self):
        """reset() used to clear blocked_edges, silently discarding the user's scenario."""
        edge_id = next(iter(self.engine.edges_dict))
        self.engine.toggle_blocked_edge(edge_id)

        self.engine.reset()
        self.assertIn(edge_id, self.engine.blocked_edges)

        self.engine.reset(clear_closures=True)
        self.assertNotIn(edge_id, self.engine.blocked_edges)

    # ---------- demand accounting ----------

    def test_every_generated_vehicle_is_accounted_for(self):
        """generate_vehicle() returns None for unroutable O-D pairs. Those used to vanish with no
        counter, so ~23% of requested demand disappeared silently."""
        self.engine.set_parameters({"spawn_rate": 5.0})
        for _ in range(120):
            self.engine.tick(dt=1.0)

        state = self.engine.get_simulation_state()
        accounted = (state["active_vehicles_count"]
                     + state["completed_trips_count"]
                     + state["dropped_spawns"]
                     + state["stranded_count"])
        # Transit buses are dispatched by the timetable, not the spawner, so they are extra.
        transit = sum(1 for v in self.engine.active_vehicles.values() if v.bus_line_id)
        self.assertEqual(accounted - transit, self.engine.vehicle_id_counter)
        self.assertGreater(state["dropped_spawns"], 0, "expected some unroutable O-D pairs")

    # ---------- lanes ----------

    def test_vehicles_are_distributed_across_lanes(self):
        """lane_index was never assigned (the assignment was unreachable and referenced an
        unimported `random`), so every vehicle sat in lane 0."""
        multilane = [e for e in self.engine.edges_dict.values() if e["lanes"] >= 2]
        self.assertTrue(multilane, "fixture network has no multi-lane edges")
        edge = multilane[0]

        lanes_seen = set()
        for i in range(60):
            v = Vehicle(f"v{i}", TrafficClass.PERSONAL, "a", "b", [edge["edge_id"]])
            v.assign_lane(edge)
            lanes_seen.add(v.lane_index)
        self.assertGreater(len(lanes_seen), 1, "all vehicles were assigned the same lane")
        self.assertTrue(all(0 <= l < edge["lanes"] for l in lanes_seen))

    def test_car_following_is_per_lane(self):
        """Vehicles on a multi-lane edge used to share one car-following file, so a 3-lane road
        carried no more traffic than a 1-lane one."""
        self.engine.set_parameters({"spawn_rate": 10.0})
        for _ in range(60):
            self.engine.tick(dt=1.0)

        by_edge = {}
        for v in self.engine.active_vehicles.values():
            if v.current_edge_id:
                by_edge.setdefault(v.current_edge_id, []).append(v)

        shared = [(e, vs) for e, vs in by_edge.items()
                  if len(vs) >= 3 and self.engine.edges_dict[e]["lanes"] >= 2]
        if not shared:
            self.skipTest("no multi-lane edge carried 3+ vehicles in this run")
        # Lanes are drawn at random, so a single edge with 3 vehicles on 2 lanes lands them all in
        # one lane 25% of the time (this assertion used to check shared[0] only and was flaky).
        # Before the fix every vehicle was in lane 0, so one mixed edge anywhere proves the point.
        mixed = [e for e, vs in shared if len({v.lane_index for v in vs}) > 1]
        self.assertTrue(mixed, f"all {len(shared)} busy multi-lane edges had a single lane in use")


class TestVehicleKinematics(unittest.TestCase):
    def _edge(self, **kw):
        base = {"edge_id": "e_test", "length": 400.0, "maxspeed": 50.0, "lanes": 1,
                "geometry": [[47.05, 8.31], [47.06, 8.32]]}
        base.update(kw)
        return base

    def test_follower_does_not_brake_for_a_leader_moving_at_its_own_speed(self):
        """IDM was called with v_lead hardcoded to 0, so every follower in a moving platoon
        treated its leader as a stationary obstacle and braked far too hard."""
        edge = self._edge()
        gap = 30.0

        moving = Vehicle("moving", TrafficClass.PERSONAL, "a", "b", ["e_test"])
        moving.speed_ms = 13.0
        moving.update_position(edge, dt=0.2, lead_vehicle_dist_m=gap, lead_vehicle_speed_ms=13.0)

        stopped = Vehicle("stopped", TrafficClass.PERSONAL, "a", "b", ["e_test"])
        stopped.speed_ms = 13.0
        stopped.update_position(edge, dt=0.2, lead_vehicle_dist_m=gap, lead_vehicle_speed_ms=0.0)

        self.assertGreater(moving.accel_ms2, stopped.accel_ms2,
                           "following a moving leader should be gentler than following a stopped one")

    def test_vehicle_cannot_cross_the_stop_line_on_red(self):
        """IDM deceleration is clamped at -6 m/s^2, so from ~50 km/h a single coarse dt step
        could still carry a vehicle past a red signal."""
        edge = self._edge(length=100.0)
        v = Vehicle("v", TrafficClass.PERSONAL, "a", "b", ["e_test"])
        v.speed_ms = 14.0
        v.distance_on_edge = 96.0

        finished = v.update_position(edge, dt=1.0, is_red_light=True)
        self.assertFalse(finished, "vehicle ran a red light")
        self.assertLess(v.distance_on_edge, edge["length"])
        self.assertEqual(v.speed_ms, 0.0)


class TestLaneResolution(unittest.TestCase):
    """A bare OSM `lanes` tag on a two-way road counts both directions."""

    def setUp(self):
        self.loader = LucerneDataLoader()

    def test_two_way_bare_lane_count_is_halved(self):
        self.assertEqual(self.loader._resolve_directional_lanes({"lanes": 2, "oneway": False}), 1)
        self.assertEqual(self.loader._resolve_directional_lanes({"lanes": 4, "oneway": False}), 2)

    def test_oneway_lane_count_is_kept(self):
        self.assertEqual(self.loader._resolve_directional_lanes({"lanes": 2, "oneway": True}), 2)
        self.assertEqual(self.loader._resolve_directional_lanes({"lanes": 3, "oneway": "yes"}), 3)

    def test_explicit_directional_tags_win(self):
        data = {"lanes": 5, "lanes:forward": 3, "lanes:backward": 2, "oneway": False}
        self.assertEqual(self.loader._resolve_directional_lanes(data), 3)
        self.assertEqual(
            self.loader._resolve_directional_lanes({**data, "reversed": True}), 2)

    def test_malformed_tags_fall_back_to_one_lane(self):
        self.assertEqual(self.loader._resolve_directional_lanes({"lanes": "unknown"}), 1)
        self.assertEqual(self.loader._resolve_directional_lanes({}), 1)
        self.assertEqual(self.loader._resolve_directional_lanes({"lanes": ["2"], "oneway": False}), 1)


if __name__ == "__main__":
    unittest.main()


class TestDeterministicTagResolution(unittest.TestCase):
    """OSMnx merges several OSM ways into one simplified edge and turns their tags into lists.

    The list order follows traversal order and varies between processes, so picking element [0]
    made the network unreproducible: two rebuilds from identical OSM data differed on 187 edges'
    speed limits, changing the >30 km/h gateway count between runs.
    """

    def setUp(self):
        self.loader = LucerneDataLoader()

    def test_merged_maxspeed_is_order_independent(self):
        self.assertEqual(self.loader._merged_maxspeed(["80", "50", "60"]), 50.0)
        self.assertEqual(self.loader._merged_maxspeed(["50", "80", "60"]), 50.0)
        self.assertEqual(self.loader._merged_maxspeed(["60", "50", "80"]), 50.0)

    def test_merged_maxspeed_parses_units_and_falls_back(self):
        self.assertEqual(self.loader._merged_maxspeed("50 km/h"), 50.0)
        self.assertEqual(self.loader._merged_maxspeed(None), 50.0)
        self.assertEqual(self.loader._merged_maxspeed(["walk", "garbage"]), 50.0)
        self.assertEqual(self.loader._merged_maxspeed(["garbage", "30"]), 30.0)

    def test_merged_highway_takes_the_highest_class_regardless_of_order(self):
        self.assertEqual(self.loader._merged_highway(["residential", "primary"]), "primary")
        self.assertEqual(self.loader._merged_highway(["primary", "residential"]), "primary")
        self.assertEqual(self.loader._merged_highway(["tertiary", "motorway", "secondary"]), "motorway")
        self.assertEqual(self.loader._merged_highway([]), "unclassified")

    def test_first_is_order_independent(self):
        self.assertEqual(self.loader._first(["Bahnhofstrasse", "Alpenstrasse"]),
                         self.loader._first(["Alpenstrasse", "Bahnhofstrasse"]))
