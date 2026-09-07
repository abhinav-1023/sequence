from .routing_base import RoutingProtocol, ROUTING_XY
from collections import deque
from ...utils import log


@RoutingProtocol.register(ROUTING_XY)
class XYRoutingProtocol(RoutingProtocol):

    def __init__(self, owner, name):
        super().__init__(
            owner,
            name,
            protocol_type=ROUTING_XY
        )
        # Active quantum requests using each link
        if not hasattr(self.owner.timeline, "congestion_table"):
            self.owner.timeline.congestion_table = {}

    def init(self):
        print("\n===== XY ROUTING INIT =====")
        print("Current Node :", self.owner.name)
        print("===========================\n")

        log.logger.debug(
            f"{self.owner.name}: XY routing initialized"
        )

    def received_message(self, src, msg):
        print("\n===== XY ROUTING RECEIVED =====")
        print("Current Node :", self.owner.name)
        print("Source       :", src)
        print("Destination  :", msg.destination)
        print("===============================\n")

        log.logger.debug(
            f"{self.owner.name}: received routing message "
            f"from {src} -> {msg.destination}"
        )

    def get_node(self, name):
        """Return router/node with the given name."""

        for entity in self.owner.timeline.entities.values():

            if hasattr(entity, "name") and entity.name == name:
                return entity

        return None

    def get_neighbors(self, node):
        """
        Return neighboring router names.

        map_to_middle_node:
            router_name -> BSM_name
        """

        mapping = getattr(
            node,
            "map_to_middle_node",
            {}
        )

        neighbors = list(mapping.keys())

        log.logger.debug(
            f"{node.name}: neighbors = {neighbors}"
        )

        return neighbors

    def get_route(self, destination):
        """
        Return a complete congestion-aware route from
        current node to destination.
        """

        source = self.owner.name

        if source == destination:
            return [source]

        candidates = self.get_candidate_routes(destination)

        if not candidates:
            return None

        # Select the least congested shortest path
        best_path = None
        best_load = float("inf")

        for path in candidates:

            path_load = 0

            for i in range(len(path) - 1):

                load = self.get_link_load(
                    path[i],
                    path[i + 1]
                )

                path_load += load

            if path_load < best_load:
                best_load = path_load
                best_path = path

        print(
            f"[ROUTING] Selected path: "
            f"{best_path}, load={best_load}"
        )

        log.logger.info(
            f"{source}: congestion-aware route to {destination}: "
            f"{' -> '.join(best_path)}, load={best_load}"
        )

        return best_path
    def get_candidate_routes(self, destination):
        """
        Find all shortest paths from current node to destination.
        These paths are used for congestion-aware routing.
        """

        source = self.owner.name

        if source == destination:
            return [[source]]

        # First find shortest-path distance
        queue = deque([source])
        distance = {source: 0}

        while queue:
            current = queue.popleft()
            current_node = self.get_node(current)

            if current_node is None:
                continue

            for neighbor in self.get_neighbors(current_node):

                if neighbor not in distance:
                    distance[neighbor] = distance[current] + 1
                    queue.append(neighbor)

        if destination not in distance:
            return []

        shortest_distance = distance[destination]

        # Build all shortest paths
        candidates = []

        def build_paths(current, path):

            if len(path) - 1 > shortest_distance:
                return

            if current == destination:
                if len(path) - 1 == shortest_distance:
                    candidates.append(path.copy())
                return

            current_node = self.get_node(current)

            if current_node is None:
                return

            for neighbor in self.get_neighbors(current_node):

                if neighbor in path:
                    continue

                # Only follow edges that remain on a shortest path
                if (
                    neighbor in distance
                    and distance[neighbor] == distance[current] + 1
                ):
                    path.append(neighbor)
                    build_paths(neighbor, path)
                    path.pop()

        build_paths(source, [source])

        print(
    f"[CANDIDATES] {source} -> {destination}: {candidates}"
)

        return candidates

    def get_link_load(self, node_a, node_b):
        key = tuple(sorted((node_a, node_b)))

        return self.owner.timeline.congestion_table.get(key, 0)

    def update_link_load(self, node_a, node_b, delta):
        key = tuple(sorted((node_a, node_b)))

        table = self.owner.timeline.congestion_table

        current = table.get(key, 0)

        table[key] = max(0, current + delta)
    def reserve_path(self, path, load=1):
        """Increase congestion load for every link in an accepted path."""

        table = self.owner.timeline.congestion_table

        for i in range(len(path) - 1):
            key = tuple(sorted((path[i], path[i + 1])))
            table[key] = table.get(key, 0) + load


    def release_path(self, path, load=1):
        """Release congestion load for every link in a completed path."""

        table = self.owner.timeline.congestion_table

        for i in range(len(path) - 1):
            key = tuple(sorted((path[i], path[i + 1])))

            current = table.get(key, 0)
            table[key] = max(0, current - load)

    def next_hop(self, destination):

        candidates = self.get_candidate_routes(destination)

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0][1]

        best_path = None
        best_load = float("inf")

        for path in candidates:

            path_load = 0

            for i in range(len(path) - 1):

                load = self.get_link_load(
                    path[i],
                    path[i + 1]
                )

                print(
                    f"[LOAD] {path[i]} -> {path[i + 1]} = {load}"
                )

                path_load += load

            print(
                f"[PATH LOAD] {path} = {path_load}"
            )

            if path_load < best_load:
                best_load = path_load
                best_path = path

        print(
            f"[SELECTED] {best_path}, load={best_load}"
        )

        return best_path[1]
    def get_node_name(self, name):
        """
        Compatibility helper.
        """

        node = self.get_node(name)

        if node is not None:
            return node.name

        return None

    def test_route(self, destination):

        print("\n========== ROUTING TEST ==========")
        print("Source      :", self.owner.name)
        print("Destination :", destination)

        log.logger.info(
            f"ROUTING TEST: "
            f"{self.owner.name} -> {destination}"
        )

        current = self.owner.name
        visited = set()

        while current != destination:

            if current in visited:

                print("ERROR: Routing loop detected!")

                log.logger.error(
                    f"Routing loop detected at {current}"
                )

                return

            visited.add(current)

            node = self.get_node(current)

            if node is None:

                print(
                    "ERROR: Node not found:",
                    current
                )

                log.logger.error(
                    f"Node not found: {current}"
                )

                return

            old_owner = self.owner
            self.owner = node

            next_node = self.next_hop(destination)

            self.owner = old_owner

            if next_node is None:

                print(
                    "ERROR: No next hop from",
                    current
                )

                log.logger.error(
                    f"No next hop from {current} "
                    f"to {destination}"
                )

                return

            print(
                f"{current} -> {next_node}"
            )

            log.logger.info(
                f"HOP: {current} -> {next_node}"
            )

            current = next_node

        print(
            f"{current}: DESTINATION REACHED"
        )

        print("=================================\n")

        log.logger.info(
            f"ROUTING TEST COMPLETE: "
            f"{self.owner.name} -> {destination}"
        )


# =============================================================
# HOP-BY-HOP XY ROUTING
# =============================================================

class HopByHopXYRoutingProtocol(XYRoutingProtocol):

    def __init__(self, owner, name):

        super().__init__(owner, name)

        self.routing_type = "HOP_BY_HOP"

        log.logger.debug(
            f"{self.owner.name}: "
            f"HopByHopXYRoutingProtocol initialized"
        )

    def get_next_hop(self, destination):
        """
        Calculate only the next hop.

        Example:
            R0 -> R1 -> R2 -> R5 -> R8

        At R0 this returns R1.
        At R1 this returns R2.
        """

        next_node = self.next_hop(destination)

        print(
            f"[HOP-BY-HOP] "
            f"{self.owner.name} -> {next_node}"
        )

        log.logger.info(
            f"[HOP-BY-HOP] "
            f"{self.owner.name} -> {next_node} "
            f"towards {destination}"
        )

        return next_node


# =============================================================
# TWO-WAY HOP-BY-HOP XY ROUTING
# =============================================================

class TwoWayHopByHopXYRoutingProtocol(XYRoutingProtocol):

    def __init__(self, owner, name):

        super().__init__(owner, name)

        self.routing_type = "TWO_WAY_HOP_BY_HOP"

        self.forward_path = []
        self.reverse_path = []

        log.logger.debug(
            f"{self.owner.name}: "
            f"TwoWayHopByHopXYRoutingProtocol initialized"
        )

    def build_two_way_route(self, destination):
        """
        Build both forward and reverse paths.

        Forward:
            R0 -> R1 -> R2 -> R5 -> R8

        Reverse:
            R8 -> R5 -> R2 -> R1 -> R0
        """

        self.forward_path = self.get_route(destination)

        if self.forward_path is None:
            return None

        self.reverse_path = list(
            reversed(self.forward_path)
        )

        print("\n===== TWO-WAY ROUTE =====")

        print(
            "Forward :",
            " -> ".join(self.forward_path)
        )

        print(
            "Reverse :",
            " -> ".join(self.reverse_path)
        )

        print("=========================\n")

        log.logger.info(
            f"[TWO-WAY] Forward: "
            f"{' -> '.join(self.forward_path)}"
        )

        log.logger.info(
            f"[TWO-WAY] Reverse: "
            f"{' -> '.join(self.reverse_path)}"
        )

        return {
            "forward": self.forward_path,
            "reverse": self.reverse_path
        }

    def get_forward_next_hop(self, destination):
        """
        Return next hop in forward direction.
        """

        if not self.forward_path:

            self.build_two_way_route(destination)

        if not self.forward_path:
            return None

        current = self.owner.name

        if current not in self.forward_path:
            return None

        index = self.forward_path.index(current)

        if index + 1 >= len(self.forward_path):
            return current

        next_node = self.forward_path[index + 1]

        print(
            f"[TWO-WAY FORWARD] "
            f"{current} -> {next_node}"
        )

        log.logger.info(
            f"[TWO-WAY FORWARD] "
            f"{current} -> {next_node}"
        )

        return next_node

    def get_reverse_next_hop(self):
        """
        Return next hop in reverse direction.
        """

        if not self.reverse_path:
            return None

        current = self.owner.name

        if current not in self.reverse_path:
            return None

        index = self.reverse_path.index(current)

        if index + 1 >= len(self.reverse_path):
            return current

        next_node = self.reverse_path[index + 1]

        print(
            f"[TWO-WAY REVERSE] "
            f"{current} -> {next_node}"
        )

        log.logger.info(
            f"[TWO-WAY REVERSE] "
            f"{current} -> {next_node}"
        )

        return next_node