class RouteManager:

    def __init__(self, routing_protocol):
        self.routing = routing_protocol

    def assign_roles(self, destination):

        path = self.routing.get_route(destination)

        if path is None:
            return None

        roles = {}

        for i, node_name in enumerate(path):

            node = self.routing.get_node(node_name)

            if i == 0:
                node.role = "SOURCE"

            elif i == len(path) - 1:
                node.role = "DESTINATION"

            else:
                node.role = "RELAY"

            roles[node_name] = node.role
    

        return roles
    def get_links(self, destination):

        path = self.routing.get_route(destination)

        if path is None:
            return None

        links = []

        for i in range(len(path) - 1):
            links.append(
                (path[i], path[i + 1])
            )

        return links