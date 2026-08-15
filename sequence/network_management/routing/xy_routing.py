from .routing_base import RoutingProtocol, ROUTING_XY
from collections import deque


@RoutingProtocol.register(ROUTING_XY)
class XYRoutingProtocol(RoutingProtocol):

    def __init__(self, owner, name):
        super().__init__(
            owner,
            name,
            protocol_type=ROUTING_XY
        )

    def init(self):
        print("\n===== XY ROUTING INIT =====")
        print("Current Node :", self.owner.name)
        print("===========================\n")

    def received_message(self, src, msg):
        print("\n===== XY ROUTING RECEIVED =====")
        print("Current Node :", self.owner.name)
        print("Source       :", src)
        print("Destination  :", msg.destination)
        print("===============================\n")

    def get_node(self, name):
        """Return router/node with the given name."""

        for entity in self.owner.timeline.entities.values():
            if hasattr(entity, "name") and entity.name == name:
                return entity

        return None

    def get_neighbors(self, node):
        """
        Return neighboring QuantumRouter names.

        map_to_middle_node stores:

            router_name -> BSM_name

        Therefore the keys are the actual neighboring routers.
        """

        mapping = getattr(
            node,
            "map_to_middle_node",
            {}
        )

        neighbors = []

        for neighbor_name in mapping:

            if neighbor_name not in neighbors:
                neighbors.append(neighbor_name)

        return neighbors

    def next_hop(self, destination):
        """
        Find the next hop from the current router to destination
        using the quantum network topology.

        No x/y/z coordinates are required.
        """

        source = self.owner.name

        if source == destination:
            return destination

        # Check that destination exists
        destination_node = self.get_node(destination)

        if destination_node is None:
            print(
                f"Destination {destination} not found."
            )
            return None

        # BFS queue
        queue = deque([source])

        # Previous node used to reconstruct path
        previous = {
            source: None
        }

        while queue:

            current_name = queue.popleft()

            current_node = self.get_node(current_name)

            if current_node is None:
                continue

            neighbors = self.get_neighbors(
                current_node
            )

            print(
                f"[ROUTING] {current_name} neighbors: "
                f"{neighbors}"
            )

            for neighbor_name in neighbors:

                if neighbor_name in previous:
                    continue

                previous[neighbor_name] = current_name

                if neighbor_name == destination:

                    queue.clear()
                    break

                queue.append(neighbor_name)

        # Destination cannot be reached
        if destination not in previous:

            print(
                f"[ROUTING] No path from "
                f"{source} to {destination}"
            )

            return None

        # Reconstruct path
        path = []

        current = destination

        while current is not None:

            path.append(current)

            current = previous[current]

        path.reverse()

        print(
            f"[ROUTING] Path: {' -> '.join(path)}"
        )

        # Path example:
        #
        # alice -> relay -> bob
        #
        # Current node = alice
        # Next hop = relay

        if len(path) >= 2:
            return path[1]

        return None

    def get_node_name(self, name):
        """
        Kept for compatibility with existing code.
        """

        node = self.get_node(name)

        if node is not None:
            return node.name

        return None
    def test_route(self, destination):
        print("\n========== ROUTING TEST ==========")
        print("Source      :", self.owner.name)
        print("Destination :", destination)

        current = self.owner.name
        visited = set()

        while current != destination:

            if current in visited:
                print("ERROR: Routing loop detected!")
                return

            visited.add(current)

            node = self.get_node(current)

            if node is None:
                print("ERROR: Node not found:", current)
                return

            # Create routing calculation from current node
            old_owner = self.owner
            self.owner = node

            next_node = self.next_hop(destination)

            self.owner = old_owner

            if next_node is None:
                print("ERROR: No next hop from", current)
                return

            print(f"{current} -> {next_node}")

            current = next_node

        print(f"{current}: DESTINATION REACHED")
        print("=================================\n")

    def get_route(self, destination):
        """Return the complete route from current node to destination."""

        source = self.owner.name

        if source == destination:
            return [source]

        queue = deque([source])
        previous = {source: None}

        while queue:

            current = queue.popleft()
            current_node = self.get_node(current)

            if current_node is None:
                continue

            for neighbor in self.get_neighbors(current_node):

                if neighbor in previous:
                    continue

                previous[neighbor] = current

                if neighbor == destination:
                    queue.clear()
                    break

                queue.append(neighbor)

        if destination not in previous:
            return None

        path = []
        current = destination

        while current is not None:
            path.append(current)
            current = previous[current]

        path.reverse()

        return path