from .router_net_topo import RouterNetTopo
from .topology import Topology as Topo


class GridTopo(RouterNetTopo):

    def __init__(
        self,
        rows: int,
        cols: int,
        memo_size: int = 2,
        distance: int = 1000,
        attenuation: float = 0.0,
    ):
        self.rows = rows
        self.cols = cols

        config = self._build_grid_config(
            memo_size=memo_size,
            distance=distance,
            attenuation=attenuation,
        )

        super().__init__(config)

    def _build_grid_config(
        self,
        memo_size: int,
        distance: int,
        attenuation: float,
    ) -> dict:

        nodes = []
        q_connections = []
        c_connections = []

        # Create routers
        for row in range(self.rows):
            for col in range(self.cols):

                node_id = row * self.cols + col
                name = f"R{node_id}"

                nodes.append({
                    Topo.NAME: name,
                    Topo.TYPE: self.QUANTUM_ROUTER,
                    Topo.SEED: node_id,
                    self.MEMO_ARRAY_SIZE: memo_size,
                })

        # Create links between neighboring routers
        for row in range(self.rows):
            for col in range(self.cols):

                current = f"R{row * self.cols + col}"

                # Horizontal link: current -> right
                if col + 1 < self.cols:

                    right = f"R{row * self.cols + col + 1}"

                    self._add_link(
                        current,
                        right,
                        q_connections,
                        c_connections,
                        distance,
                        attenuation,
                    )

                # Vertical link: current -> down
                if row + 1 < self.rows:

                    down = f"R{(row + 1) * self.cols + col}"

                    self._add_link(
                        current,
                        down,
                        q_connections,
                        c_connections,
                        distance,
                        attenuation,
                    )

        return {
            Topo.ALL_NODE: nodes,
            Topo.ALL_Q_CONNECT: q_connections,
            Topo.ALL_C_CONNECT: c_connections,
        }

    def _add_link(
        self,
        node1: str,
        node2: str,
        q_connections: list,
        c_connections: list,
        distance: int,
        attenuation: float,
    ):

        # Quantum connection
        q_connections.append({
            Topo.CONNECT_NODE_1: node1,
            Topo.CONNECT_NODE_2: node2,
            Topo.TYPE: self.MEET_IN_THE_MID,
            Topo.DISTANCE: distance,
            Topo.ATTENUATION: attenuation,
            Topo.SEED: 0,
        })

        # Classical connection
        c_connections.append({
            Topo.CONNECT_NODE_1: node1,
            Topo.CONNECT_NODE_2: node2,
            Topo.DISTANCE: distance,
        })