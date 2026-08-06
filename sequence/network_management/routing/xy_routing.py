from .routing_base import RoutingProtocol, ROUTING_XY

@RoutingProtocol.register(ROUTING_XY)
class XYRoutingProtocol(RoutingProtocol):
    def init(self):
        
            print("\n===== XY ROUTING INIT =====")
            print("Current Node :", self.owner.name)
            print("Coordinate   :", self.owner.x, self.owner.y, self.owner.z)
            print("===========================\n")
    def __init__(self, owner, name):
        super().__init__(owner, name, protocol_type=ROUTING_XY)

    

    def received_message(self, src, msg):
        print("\n===== XY ROUTING Received Message =====")

        if self.owner.name == msg.destination:
            print("Message Delivered")
            return

        next_node = self.next_hop(...)

        self.owner.send_message(next_node, msg)
        # print("XY Routing Protocol")
        # dst_name = msg.reservation.responder

        # dst_node = self.get_node(dst_name)

        # current = (
        #     self.owner.x,
        #     self.owner.y,
        #     self.owner.z
        # )

        # destination = (
        #     dst_node.x,
        #     dst_node.y,
        #     dst_node.z
        # )

        # next_coord = self.next_hop(current, destination)

        # print("Current      :", current)
        # print("Destination  :", destination)
        # print("Next Coord   :", next_coord)
        # next_node = self.get_node_name(next_coord)

        # print("Next Node =", next_node)
    def next_hop(self,current, destination):
        x, y, z = current
        dx, dy, dz = destination

        # Move in X dimension
        if x < dx:
            return (x + 1, y, z)

        elif x > dx:
            return (x - 1, y, z)

        # Move in Y dimension
        elif y < dy:
            return (x, y + 1, z)

        elif y > dy:
            return (x, y - 1, z)

        # Move in Z dimension
        elif z < dz:
            return (x, y, z + 1)

        elif z > dz:
            return (x, y, z - 1)

        return current
    def get_node(self, name):
        for node in self.owner.timeline.entities:
            if hasattr(node, "name") and node.name == name:
                return node
        return None
    def get_node_name(self, coord):

        for node in self.owner.timeline.entities:

            if (
                hasattr(node, "x") and
                (node.x, node.y, node.z) == coord
            ):
                return node.name

        return None
